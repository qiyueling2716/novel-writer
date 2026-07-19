"""
全局配置模块
"""
import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent

# 数据存储目录
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 默认导出目录
DEFAULT_EXPORT_DIR = BASE_DIR / "exports"
DEFAULT_EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# 封面图片存储目录（生成的封面会下载到这里，避免远程 URL 过期）
COVERS_DIR = BASE_DIR / "static" / "covers"
COVERS_DIR.mkdir(parents=True, exist_ok=True)

# 数据库路径
DB_PATH = DATA_DIR / "novels.db"

# —————— LLM 默认配置 ——————
LLM_CONFIG = {
    "api_base": os.environ.get("LLM_API_BASE", "https://api.openai.com/v1"),
    "api_key": os.environ.get("LLM_API_KEY", ""),
    "model": os.environ.get("LLM_MODEL", "gpt-4o"),
    "temperature": 0.8,
    "max_tokens": 4096,
    "chat_path": os.environ.get("LLM_CHAT_PATH", "/chat/completions"),
}

# —————— 向量模型默认配置 ——————
VECTOR_CONFIG = {
    "backend": os.environ.get("VECTOR_BACKEND", "sklearn"),
    "model_name": os.environ.get("VECTOR_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"),
    "similarity_threshold": 0.75,
    "device": os.environ.get("VECTOR_DEVICE", "cpu"),
    # 自定义 Embedding API — 是否使用独立配置 vs 复用 LLM
    "use_independent_embedding": os.environ.get("USE_INDEPENDENT_EMBEDDING", "false").lower() == "true",
    "embedding_api_base": os.environ.get("EMBEDDING_API_BASE", ""),
    "embedding_api_key": os.environ.get("EMBEDDING_API_KEY", ""),
    "embedding_model": os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
    "embedding_path": os.environ.get("EMBEDDING_PATH", "/embeddings"),
}

# —————— Reranker 默认配置 ——————
RERANKER_CONFIG = {
    "enabled": False,
    "use_independent": False,  # False=复用LLM配置, True=独立配置
    "api_base": "",
    "api_key": "",
    "model": "",
    "rerank_path": "/rerank",  # rerank endpoint path
    "top_n": 3,  # 返回 top_n 条重复
}

# —————— 小说生成默认配置 ——————
NOVEL_CONFIG = {
    "default_words_per_chapter": 3000,
    "duplicate_check_interval": 3,
    "title_generation": "auto",
}