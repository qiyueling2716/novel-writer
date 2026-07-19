"""
向量服务 — 剧情重复检测 + 前文摘要
默认使用 sklearn TF-IDF（轻量，无需 PyTorch）
可选升级: sentence-transformers 或自定义 Embedding API
配置持久化到 JSON 文件，重启不丢失
"""
import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from config import VECTOR_CONFIG, DATA_DIR

logger = logging.getLogger(__name__)

_vector_model = None
_vector_available = None  # None=未检测, True=可用, False=不可用
_thread_pool = ThreadPoolExecutor(max_workers=2)
_runtime_vector_config: dict = {}

# 配置持久化文件
VECTOR_CONFIG_FILE = DATA_DIR / "vector_config.json"


def _save_config():
    """持久化当前运行时配置到文件（embedding_api_key 加密存储）"""
    try:
        from services.secret_service import encrypt_value
        # 复制一份，加密 api_key 后保存（不修改运行时内存中的明文）
        to_save = {**_runtime_vector_config}
        if to_save.get("embedding_api_key"):
            to_save["embedding_api_key"] = encrypt_value(to_save["embedding_api_key"])
        VECTOR_CONFIG_FILE.write_text(
            json.dumps(to_save, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("向量配置保存失败: %s", e)


def _load_config():
    """从文件加载持久化配置（embedding_api_key 自动解密）"""
    global _runtime_vector_config
    if not VECTOR_CONFIG_FILE.exists():
        return
    try:
        cfg = json.loads(VECTOR_CONFIG_FILE.read_text(encoding="utf-8"))
        # 透明解密 embedding_api_key
        from services.secret_service import decrypt_value
        if cfg.get("embedding_api_key"):
            cfg["embedding_api_key"] = decrypt_value(cfg["embedding_api_key"])
        _runtime_vector_config = cfg
        logger.info("已加载向量配置: backend=%s", _runtime_vector_config.get("backend", "sklearn"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("向量配置加载失败: %s", e)


# 启动时自动加载
_load_config()


def update_vector_config(backend: str = "", model_name: str = "",
                         similarity_threshold: float = 0.75, device: str = "cpu",
                         use_independent_embedding: bool = False,
                         embedding_api_base: str = "", embedding_api_key: str = "",
                         embedding_model: str = "", embedding_path: str = ""):
    """更新向量模型运行时配置并持久化"""
    global _vector_model, _vector_available
    # 直接覆盖所有字段（不再用 if v 过滤，允许清空）
    _runtime_vector_config["backend"] = backend or "sklearn"
    _runtime_vector_config["model_name"] = model_name
    _runtime_vector_config["similarity_threshold"] = similarity_threshold
    _runtime_vector_config["device"] = device
    _runtime_vector_config["use_independent_embedding"] = use_independent_embedding
    _runtime_vector_config["embedding_api_base"] = embedding_api_base
    _runtime_vector_config["embedding_api_key"] = embedding_api_key
    _runtime_vector_config["embedding_model"] = embedding_model
    _runtime_vector_config["embedding_path"] = embedding_path
    _vector_model = None
    _vector_available = None
    _save_config()


def get_vector_config() -> dict:
    return {**VECTOR_CONFIG, **_runtime_vector_config}


def is_vector_available() -> bool:
    """检查向量模型是否可用"""
    global _vector_available
    if _vector_available is not None:
        return _vector_available
    cfg = get_vector_config()
    backend = cfg.get("backend", "sklearn")
    if backend == "sklearn":
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            TfidfVectorizer()
            _vector_available = True
        except Exception:
            _vector_available = False
    elif backend == "sentence_transformers":
        try:
            from sentence_transformers import SentenceTransformer
            _vector_available = True
        except ImportError:
            _vector_available = False
    elif backend == "openai":
        _vector_available = True  # 依赖网络，先假设可用
    else:
        _vector_available = False
    return _vector_available


# ========== 后端 1: sklearn TF-IDF ==========

def _get_sklearn_vectorizer():
    global _vector_model
    if _vector_model is None:
        from sklearn.feature_extraction.text import TfidfVectorizer
        _vector_model = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(2, 4), max_features=5000, lowercase=False,
        )
    return _vector_model


def _sklearn_encode(texts: list[str]):
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    # 每次创建新实例，避免并发 fit_transform 修改共享状态
    vec = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(2, 4), max_features=5000, lowercase=False,
    )
    return vec.fit_transform(texts).toarray()


# ========== 后端 2: sentence-transformers ==========

def _get_st_model():
    global _vector_model
    if _vector_model is None:
        cfg = get_vector_config()
        from sentence_transformers import SentenceTransformer
        logger.info("正在加载 sentence-transformers 模型: %s", cfg["model_name"])
        _vector_model = SentenceTransformer(cfg["model_name"], device=cfg["device"])
    return _vector_model


def _st_encode(texts: list[str]):
    import numpy as np
    model = _get_st_model()
    return model.encode(texts, show_progress_bar=False)


# ========== 后端 3: 自定义 Embedding API ==========

async def _api_encode(texts: list[str]):
    import httpx
    import numpy as np

    cfg = get_vector_config()
    if cfg.get("use_independent_embedding"):
        api_base = cfg.get("embedding_api_base", "")
        api_key = cfg.get("embedding_api_key", "")
        model = cfg.get("embedding_model", "text-embedding-3-small")
        emb_path = cfg.get("embedding_path", "/embeddings")
    else:
        from config import LLM_CONFIG
        from services.llm_service import _runtime_llm_config
        llm_cfg = {**LLM_CONFIG, **_runtime_llm_config}
        api_base = llm_cfg.get("api_base", "https://api.openai.com/v1")
        api_key = llm_cfg.get("api_key", "")
        model = cfg.get("embedding_model", "text-embedding-3-small")
        emb_path = "/embeddings"

    base = api_base.rstrip("/")
    if base.endswith(emb_path) or "/embeddings" in base:
        url = base
    else:
        url = f"{base}{emb_path}"

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        resp = await client.post(
            url,
            json={"model": model, "input": texts},
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        if resp.status_code >= 400:
            logger.warning("Embedding API 错误 (%d): %s", resp.status_code, resp.text[:300])
            return None
        data = resp.json()
        # 安全实践：校验响应结构
        if not isinstance(data, dict) or "data" not in data:
            logger.warning("Embedding API 返回异常结构: %s", str(data)[:300])
            return None
        embeddings = []
        for item in data["data"]:
            if not isinstance(item, dict) or "embedding" not in item:
                logger.warning("Embedding API 返回项缺少 embedding 字段")
                return None
            embeddings.append(item["embedding"])
        return np.array(embeddings)


# ========== 统一编码入口 ==========

async def encode_texts(texts: list[str]):
    """对文本列表进行编码，失败时返回 None"""
    try:
        cfg = get_vector_config()
        backend = cfg.get("backend", "sklearn")
        if backend == "openai":
            return await _api_encode(texts)
        elif backend == "sentence_transformers":
            if not is_vector_available():
                return None
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(_thread_pool, _st_encode, texts)
        else:
            if not is_vector_available():
                return None
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(_thread_pool, _sklearn_encode, texts)
    except Exception as e:
        logger.warning("向量编码失败: %s", e)
        return None


# ========== 相似度计算 ==========

def cosine_similarity(a, b) -> float:
    import numpy as np
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.ndim == 1:
        a = a.reshape(1, -1)
    if b.ndim == 1:
        b = b.reshape(1, -1)
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-10)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-10)
    return float(np.dot(a_norm, b_norm.T)[0][0])


async def check_duplicate(text: str, existing_texts: list[str]) -> list[dict]:
    if not existing_texts:
        return []
    cfg = get_vector_config()
    threshold = cfg["similarity_threshold"]
    all_texts = [text] + existing_texts
    embeddings = await encode_texts(all_texts)
    if embeddings is None:
        return []
    target_emb = embeddings[0]
    results = []
    for i in range(len(existing_texts)):
        sim = cosine_similarity(target_emb, embeddings[i + 1])
        if sim >= threshold:
            results.append({"index": i, "similarity": round(sim, 4), "text_preview": existing_texts[i][:100]})
    return results


async def pairwise_check(texts: list[str]) -> list[dict]:
    if len(texts) < 2:
        return []
    cfg = get_vector_config()
    threshold = cfg["similarity_threshold"]
    embeddings = await encode_texts(texts)
    if embeddings is None:
        return []
    results = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            sim = cosine_similarity(embeddings[i], embeddings[j])
            if sim >= threshold:
                results.append({
                    "pair": (i, j), "similarity": round(sim, 4),
                    "text_a_preview": texts[i][:80], "text_b_preview": texts[j][:80],
                })
    return results


# ========== 前文摘要（LLM 驱动） ==========

async def summarize_chapters(
    chapters: list[dict],
    novel: dict,
    summary_count: int = 3,
) -> str:
    """
    使用 LLM 将最近 N 章内容总结为摘要，供下一章生成时作为上下文
    """
    if not chapters:
        return ""

    from services.llm_service import chat_completion

    recent = chapters[-summary_count:]
    summaries = []
    for i, ch in enumerate(recent):
        content = ch["content"]
        if not content:
            continue
        # 取每章前 800 字 + 后 200 字作为摘要素材
        snippet = content[:800]
        if len(content) > 1200:
            snippet += f"\n...\n{content[-200:]}"
        summaries.append(f"第{ch['number']}章《{ch['title']}》: {snippet}")

    if not summaries:
        return ""

    joined_summaries = '\n'.join(summaries)
    prompt = f"""将以下章节内容总结为前情提要（300字以内），供下一章创作时参考。

保留：关键情节转折、人物关系变化、未回收的伏笔和悬念。
省略：细节描写、对话原文、重复信息、环境铺垫。

{joined_summaries}

前情提要："""

    try:
        resp = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.5,
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning("章节摘要生成失败: %s", e)
        # 降级：直接拼接前 200 字
        return "\n".join(
            f"第{ch['number']}章: {ch['content'][:200]}" for ch in recent if ch["content"]
        )