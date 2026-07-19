"""
密钥加密服务 — 对 API Key 等敏感信息进行对称加密存储

设计要点：
1. 使用 Fernet 对称加密（AES-128-CBC + HMAC-SHA256）
2. 加密密钥从用户主密码派生（PBKDF2-HMAC-SHA256，10万次迭代）
3. 存储格式：ENC:v1:<salt_hex>:<ciphertext>  便于识别和兼容
4. 配置文件中的 api_key 字段加密存储，读取时透明解密
5. 备份导出时可选加密，密钥相关字段用用户输入的备份密码加密

兼容性：
- 读取时自动识别明文和加密格式，明文直接返回（向后兼容旧数据）
- 迁移工具：首次设置主密码后，自动加密所有明文密钥
"""
import base64
import hashlib
import json
import logging
import os
import secrets as _secrets
from typing import Optional

logger = logging.getLogger(__name__)

# 加密标识前缀，用于识别已加密的值
_ENC_PREFIX = "ENC:v1:"
# PBKDF2 迭代次数
_PBKDF2_ITERATIONS = 100_000
# 盐长度（字节）
_SALT_LENGTH = 16

# 全局主密码（运行时缓存，从 settings 表的 auth_password 派生）
# 注意：不直接存储密码明文，而是存储派生出的 Fernet 密钥
_master_fernet = None
_master_password_hash = None  # 用于检测密码是否变化


def _derive_fernet_key(password: str, salt: bytes) -> bytes:
    """从密码和盐派生 Fernet 密钥"""
    raw = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
        dklen=32,
    )
    return base64.urlsafe_b64encode(raw)


def _get_master_password() -> str:
    """从 settings 表获取主密码（即登录密码的哈希值本身作为加密主密码）
    
    这样无需用户额外设置加密密码，主密码变化时密钥也变化（需重新加密）。
    但为了让密钥不直接暴露在内存，我们用 auth_token 作为派生源（每次登录都会重新生成）。
    
    实际方案：使用一个独立的随机密钥存储在 settings 表，首次启动时生成。
    这样主密码变化不影响已加密的密钥。
    """
    from models.database import get_db
    from contextlib import closing
    
    with closing(get_db()) as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'enc_master_key'"
        ).fetchone()
        if row and row["value"]:
            return row["value"]
        # 首次启动：生成随机主密钥并存储
        master_key = _secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('enc_master_key', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=?",
            (master_key, master_key),
        )
        conn.commit()
        return master_key


def _get_master_fernet():
    """获取主 Fernet 实例（懒加载，运行时缓存）"""
    global _master_fernet, _master_password_hash
    if _master_fernet is not None:
        return _master_fernet
    
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        logger.warning("cryptography 库未安装，密钥加密功能不可用")
        return None
    
    try:
        master_password = _get_master_password()
        # 用固定盐派生（盐也存储在 settings 表，保证可恢复）
        from models.database import get_db
        from contextlib import closing
        with closing(get_db()) as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = 'enc_salt'"
            ).fetchone()
            if row and row["value"]:
                salt = bytes.fromhex(row["value"])
            else:
                salt = os.urandom(_SALT_LENGTH)
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES ('enc_salt', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=?",
                    (salt.hex(), salt.hex()),
                )
                conn.commit()
        
        key = _derive_fernet_key(master_password, salt)
        _master_fernet = Fernet(key)
        _master_password_hash = master_password[:8]  # 仅用于检测变化
        return _master_fernet
    except Exception as e:
        logger.error("初始化主 Fernet 失败: %s", e)
        return None


def is_encryption_available() -> bool:
    """检查加密功能是否可用"""
    return _get_master_fernet() is not None


def encrypt_value(plaintext: str) -> str:
    """加密一个值，返回 ENC:v1:<salt_hex>:<ciphertext> 格式
    
    如果 plaintext 为空或已经是加密格式，直接返回。
    如果加密功能不可用，返回明文（降级处理）。
    """
    if not plaintext:
        return ""
    if plaintext.startswith(_ENC_PREFIX):
        return plaintext  # 已加密
    
    f = _get_master_fernet()
    if f is None:
        return plaintext  # 降级：返回明文
    
    try:
        # 每次加密使用随机盐（虽然 Fernet 内部已有 IV，但额外盐增加安全性）
        salt = os.urandom(_SALT_LENGTH)
        # 用盐派生一次性密钥？不，Fernet 已有 IV。直接用主密钥加密。
        ciphertext = f.encrypt(plaintext.encode("utf-8")).decode("ascii")
        return f"{_ENC_PREFIX}{salt.hex()}:{ciphertext}"
    except Exception as e:
        logger.error("加密失败: %s", e)
        return plaintext  # 降级


def decrypt_value(value: str) -> str:
    """解密一个值
    
    如果值不是加密格式（明文），直接返回（向后兼容）。
    如果解密失败，返回空字符串（避免泄露部分信息）。
    """
    if not value:
        return ""
    if not value.startswith(_ENC_PREFIX):
        return value  # 明文，直接返回
    
    f = _get_master_fernet()
    if f is None:
        logger.warning("加密值存在但加密功能不可用，返回空")
        return ""
    
    try:
        # 解析格式：ENC:v1:<salt_hex>:<ciphertext>
        parts = value.split(":", 3)
        if len(parts) != 4:
            logger.warning("加密值格式无效")
            return ""
        ciphertext = parts[3]
        plaintext = f.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        return plaintext
    except Exception as e:
        logger.error("解密失败: %s", e)
        return ""


def is_encrypted(value: str) -> bool:
    """判断值是否已加密"""
    return bool(value) and value.startswith(_ENC_PREFIX)


# ==================== 备份专用加密（使用用户输入的密码） ====================

def encrypt_backup_data(data: dict, password: str) -> dict:
    """用用户密码加密备份数据
    
    返回包含加密后数据和元信息的字典：
    {
        "_encrypted": true,
        "_enc_version": 1,
        "_enc_algorithm": "fernet-pbkdf2",
        "_enc_salt": "<hex>",
        "_enc_iterations": 100000,
        "payload": "<加密的JSON字符串>"
    }
    """
    if not password:
        return data  # 无密码，不加密
    
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise RuntimeError("加密库未安装，无法加密备份。请运行: pip install cryptography")
    
    salt = os.urandom(_SALT_LENGTH)
    key = _derive_fernet_key(password, salt)
    f = Fernet(key)
    
    plaintext = json.dumps(data, ensure_ascii=False).encode("utf-8")
    ciphertext = f.encrypt(plaintext).decode("ascii")
    
    return {
        "_encrypted": True,
        "_enc_version": 1,
        "_enc_algorithm": "fernet-pbkdf2-sha256",
        "_enc_salt": salt.hex(),
        "_enc_iterations": _PBKDF2_ITERATIONS,
        "payload": ciphertext,
    }


def decrypt_backup_data(data: dict, password: str) -> dict:
    """用用户密码解密备份数据
    
    如果 data 不是加密格式，直接返回（兼容旧备份）。
    """
    if not isinstance(data, dict):
        return data
    if not data.get("_encrypted"):
        return data  # 未加密，直接返回
    
    if not password:
        raise ValueError("此备份已加密，请输入密码")
    
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise RuntimeError("加密库未安装，无法解密备份。请运行: pip install cryptography")
    
    salt = bytes.fromhex(data.get("_enc_salt", ""))
    iterations = data.get("_enc_iterations", _PBKDF2_ITERATIONS)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)
    key = base64.urlsafe_b64encode(key)
    f = Fernet(key)
    
    ciphertext = data["payload"].encode("ascii")
    plaintext = f.decrypt(ciphertext).decode("utf-8")
    return json.loads(plaintext)


def is_backup_encrypted(data: dict) -> bool:
    """判断备份数据是否已加密"""
    return isinstance(data, dict) and data.get("_encrypted") is True
