"""
多供应商管理 — JSON 文件持久化，支持增删改查、切换活跃供应商
api_key 字段加密存储（使用 secret_service），读取时透明解密
"""
import json
import logging
import uuid
from typing import Optional

from config import DATA_DIR
from services.secret_service import encrypt_value, decrypt_value, is_encrypted

logger = logging.getLogger(__name__)

PROVIDERS_FILE = DATA_DIR / "providers.json"


def _load() -> list[dict]:
    """加载所有供应商（api_key 自动解密）"""
    if not PROVIDERS_FILE.exists():
        return []
    try:
        providers = json.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))
        # 透明解密 api_key
        for p in providers:
            if "api_key" in p:
                p["api_key"] = decrypt_value(p["api_key"])
        return providers
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def _save(providers: list[dict]):
    """保存所有供应商（原子写入，api_key 加密存储）"""
    PROVIDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    # 加密 api_key 后再保存（不修改内存中的明文副本）
    to_save = []
    for p in providers:
        p_copy = {**p}
        if p_copy.get("api_key"):
            p_copy["api_key"] = encrypt_value(p_copy["api_key"])
        to_save.append(p_copy)
    # 安全实践：写入临时文件后原子 rename，防止中途崩溃损坏数据
    tmp = PROVIDERS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(to_save, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(PROVIDERS_FILE)


def _mask_key(key: str) -> str:
    """掩码 api_key，只保留前4位"""
    if not key:
        return ""
    return key[:4] + "***" if len(key) > 4 else "***"


def list_providers(mask_keys: bool = True) -> list[dict]:
    """列出所有供应商（默认掩码 api_key）"""
    providers = _load()
    if mask_keys:
        for p in providers:
            p["api_key"] = _mask_key(p.get("api_key", ""))
    return providers


def get_provider(provider_id: str) -> Optional[dict]:
    """获取单个供应商"""
    for p in _load():
        if p["id"] == provider_id:
            return p
    return None


def get_active_provider() -> Optional[dict]:
    """获取当前活跃供应商"""
    for p in _load():
        if p.get("is_active"):
            return p
    return None


def _mask_provider(p: dict) -> dict:
    """返回供应商副本，api_key 已掩码"""
    masked = {**p}
    masked["api_key"] = _mask_key(p.get("api_key", ""))
    return masked


def create_provider(name: str, api_base: str = "", api_key: str = "",
                    model: str = "", chat_path: str = "/chat/completions",
                    temperature: float = 0.8, max_tokens: int = 4096) -> dict:
    """创建新供应商"""
    providers = _load()
    new_p = {
        "id": str(uuid.uuid4()),
        "name": name or f"供应商 {len(providers) + 1}",
        "api_base": api_base,
        "api_key": api_key,
        "model": model,
        "chat_path": chat_path or "/chat/completions",
        "temperature": temperature,
        "max_tokens": max_tokens,
        "is_active": len(providers) == 0,  # 第一个默认激活
    }
    providers.append(new_p)
    _save(providers)
    return _mask_provider(new_p)


def update_provider(provider_id: str, **kwargs) -> Optional[dict]:
    """更新供应商；api_key 为空字符串时不覆盖"""
    providers = _load()
    allowed = ["name", "api_base", "api_key", "model", "chat_path",
               "temperature", "max_tokens", "is_active"]
    for p in providers:
        if p["id"] == provider_id:
            for k in allowed:
                if k in kwargs:
                    val = kwargs[k]
                    # api_key 空字符串 → 不覆盖
                    if k == "api_key" and val == "":
                        continue
                    p[k] = val
            _save(providers)
            return _mask_provider(p)
    return None


def set_active_provider(provider_id: str) -> Optional[dict]:
    """设置活跃供应商"""
    providers = _load()
    found = None
    for p in providers:
        p["is_active"] = (p["id"] == provider_id)
        if p["is_active"]:
            found = p
    _save(providers)
    return _mask_provider(found) if found else None


def delete_provider(provider_id: str) -> bool:
    """删除供应商；不能删除最后一个"""
    providers = _load()
    if len(providers) <= 1:
        return False
    new_list = [p for p in providers if p["id"] != provider_id]
    if len(new_list) == len(providers):
        return False
    # 如果删除的是活跃供应商，让第一个活跃
    was_active = any(p["id"] == provider_id and p.get("is_active") for p in providers)
    if was_active and new_list:
        new_list[0]["is_active"] = True
    _save(new_list)
    return True


def duplicate_provider(provider_id: str) -> Optional[dict]:
    """复制供应商"""
    src = get_provider(provider_id)
    if not src:
        return None
    new_p = {
        **src,
        "id": str(uuid.uuid4()),
        "name": f"{src.get('name', '')} (副本)",
        "is_active": False,
        "api_key": "",  # 安全实践：副本不复制密钥，需重新输入
    }
    providers = _load()
    providers.append(new_p)
    _save(providers)
    return new_p


def apply_active_provider():
    """将活跃供应商的配置应用到 llm_service 运行时"""
    active = get_active_provider()
    if not active:
        import logging
        logging.warning("apply_active_provider: 未找到活跃供应商，LLM 将使用默认配置")
        return
    import logging
    logging.info("apply_active_provider: 加载供应商 '%s' (model=%s, api_base=%s)",
                 active.get("name", "?"), active.get("model", "?"), active.get("api_base", "?"))
    from services.llm_service import set_active_provider
    # 直接设入 _active_provider，绕过 update_llm_config 的空值过滤问题
    set_active_provider(active)