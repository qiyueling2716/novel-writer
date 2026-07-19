"""
Reranker 服务 — 对重复检测结果进行精排
兼容 Cohere/Jina 风格的 rerank API
配置持久化到 JSON 文件，重启不丢失
"""
import json
import logging

import httpx

from config import RERANKER_CONFIG, DATA_DIR

logger = logging.getLogger(__name__)

_runtime_reranker_config: dict = {}

# 配置持久化文件
RERANKER_CONFIG_FILE = DATA_DIR / "reranker_config.json"


def _save_config():
    """持久化当前运行时配置到文件（api_key 加密存储）"""
    try:
        from services.secret_service import encrypt_value
        to_save = {**_runtime_reranker_config}
        if to_save.get("api_key"):
            to_save["api_key"] = encrypt_value(to_save["api_key"])
        RERANKER_CONFIG_FILE.write_text(
            json.dumps(to_save, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("Reranker 配置保存失败: %s", e)


def _load_config():
    """从文件加载持久化配置（api_key 自动解密）"""
    global _runtime_reranker_config
    if not RERANKER_CONFIG_FILE.exists():
        return
    try:
        cfg = json.loads(RERANKER_CONFIG_FILE.read_text(encoding="utf-8"))
        from services.secret_service import decrypt_value
        if cfg.get("api_key"):
            cfg["api_key"] = decrypt_value(cfg["api_key"])
        _runtime_reranker_config = cfg
        logger.info("已加载 Reranker 配置: enabled=%s", _runtime_reranker_config.get("enabled", False))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Reranker 配置加载失败: %s", e)


# 启动时自动加载
_load_config()


def update_reranker_config(
    enabled: bool = False,
    use_independent: bool = False,
    api_base: str = "",
    api_key: str = "",
    model: str = "",
    rerank_path: str = "",
    top_n: int = 3,
):
    """更新 reranker 运行时配置并持久化"""
    global _runtime_reranker_config
    # None = 未修改，保留原值；其他值直接覆盖
    fields = {
        "enabled": enabled,
        "use_independent": use_independent,
        "api_base": api_base,
        "api_key": api_key,
        "model": model,
        "rerank_path": rerank_path,
        "top_n": top_n,
    }
    for k, v in fields.items():
        if v is not None:
            _runtime_reranker_config[k] = v
    _save_config()


def get_reranker_config() -> dict:
    """获取当前 reranker 配置"""
    return {**RERANKER_CONFIG, **_runtime_reranker_config}


def is_reranker_available() -> bool:
    """检查 reranker 是否可用（enabled 且配置了 api_base）"""
    cfg = get_reranker_config()
    if not cfg.get("enabled", False):
        return False
    # 独立配置：需要 api_base
    if cfg.get("use_independent", False):
        return bool(cfg.get("api_base", ""))
    # 复用 LLM 配置：检查 LLM 是否有 api_base
    from services.llm_service import get_llm_config
    llm_cfg = get_llm_config()
    return bool(llm_cfg.get("api_base", ""))


async def rerank(query: str, documents: list[dict]) -> list[dict]:
    """
    调用 reranker API 对 documents 重新排序，返回按 relevance_score 降序排列的列表。

    :param query: 查询文本
    :param documents: 待排序的文档列表，每个文档为 dict，需包含 "text" 键
    :return: 按 relevance_score 降序排列的文档列表，每个文档附带 relevance_score 字段
    """
    if not query or not documents:
        return documents

    cfg = get_reranker_config()

    # 确定连接参数
    if cfg.get("use_independent", False):
        api_base = cfg.get("api_base", "")
        api_key = cfg.get("api_key", "")
    else:
        from services.llm_service import get_llm_config
        llm_cfg = get_llm_config()
        api_base = llm_cfg.get("api_base", "")
        api_key = llm_cfg.get("api_key", "")

    model = cfg.get("model", "")
    rerank_path = cfg.get("rerank_path", "/rerank")
    top_n = cfg.get("top_n", len(documents))

    base = api_base.rstrip("/")
    if base.endswith(rerank_path):
        url = base
    else:
        url = f"{base}{rerank_path}"

    # 提取文档纯文本列表
    doc_texts = [doc.get("text", "") for doc in documents]

    body = {
        "model": model,
        "query": query,
        "documents": doc_texts,
        "top_n": top_n,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        # 解析返回结果 — 兼容 Cohere/Jina 格式
        # Cohere 格式: data["results"] = [{"index": 0, "relevance_score": 0.95}, ...]
        # Jina 格式:  data["results"] = [{"index": 0, "relevance_score": 0.95}, ...]
        results = data.get("results", [])

        # 构建按 score 降序排列的文档列表
        scored_docs = []
        for item in results:
            idx = item.get("index", 0)
            score = item.get("relevance_score", 0.0)
            if 0 <= idx < len(documents):
                doc = {**documents[idx], "relevance_score": round(score, 4)}
                scored_docs.append(doc)

        # 按 relevance_score 降序排序
        scored_docs.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return scored_docs

    except Exception as e:
        logger.warning("Reranker 调用失败: %s", e)
        # 降级返回原始顺序，补充 relevance_score 保持结构一致
        return [{**d, "relevance_score": d.get("similarity", 0.0)} for d in documents]
