"""
AI 小说写作助手 — FastAPI 主入口
"""
import asyncio
import bcrypt
import json
import secrets
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

# 修复 multiprocessing spawn 模式找不到 main.py 的问题
# sentence-transformers / torch 等库内部会使用 multiprocessing，在 spawn 模式下
# 子进程会重新 import 主模块，如果 __main__ 路径不在 sys.path 中就会报错
# Linux 默认用 fork，但某些环境（如 AstrBot 宿主）可能强制 spawn，这里做兜底
import multiprocessing
if multiprocessing.get_start_method(allow_none=True) not in ("fork", None):
    try:
        multiprocessing.set_start_method("fork", force=True)
    except RuntimeError:
        pass  # 已经设置过，忽略
# 确保 main.py 所在目录在 sys.path 中（spawn 子进程 import 时能找到）
try:
    _main_dir = str(Path(__file__).resolve().parent)
    if _main_dir not in sys.path:
        sys.path.insert(0, _main_dir)
except Exception:
    pass

from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, Depends, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ==================== 应用版本 ====================
# 修改这里后，前端会通过 /api/version 接口获取并显示
APP_VERSION = "2026.07.20n"
APP_VERSION_NOTES = [
    "新增密钥加密存储（API Key 加密落盘）",
    "新增备份加密功能（密码保护备份文件）",
    "新增统一 Modal 对话框（替代原生弹窗）",
    "新增自定义 Checkbox 样式",
    "新增侧边栏版本号显示（点击查看详情）",
    "新增连续创作的 SSE 流恢复功能（离开页面后可返回继续看进度）",
    "新增 /api/novels/{id}/batch-stream 恢复接口（广播模式）",
    "新增章节编辑器「清理空行」功能（4 种模式：合并连续/删除全部/删首尾/合并+删首尾）",
    "新增连续创作独立配置页面（支持整体走向 + 每章具体走向配置，留空则 AI 自由发挥）",
    "新增 batch-generate 页面路由，单章创作仍用原创作页面",
    "新增每章独立创作走向参数 chapter_suggestions（JSON 数组，后端按索引分发）",
    "优化连续创作开始后立即触发任务轮询（侧边栏 0.5 秒内显示进度）",
    "优化删除人物画像/章节后局部刷新（不整页刷新，保留滚动位置和 tab 状态）",
    "优化批量选择章节时的点击行为（批量模式下点击行内任意位置只切换选中，不误触进入章节）",
    "修复点击侧边栏版本号/重启按钮时弹出 Modal 会误触发侧边栏关闭（全局 click 监听排除 Modal）",
    '修复连续创作 Modal 输入任何数字都提示「请输入 1-50」的问题（DOM 生命周期）',
    '修复创作任务面板 spinner 转动抽搐（改用纯 CSS spinner + 指纹比对）',
    "修复 multiprocessing spawn 找不到 main.py",
    "修复章节重排 400 错误（两步更新避免 UNIQUE 冲突）",
    "修复 AI 工具参数 JSON 截断问题（自动修复不完整 JSON）",
    '修复批量任务恢复时误报「已结束或不存在」（subscribers/finished 字段初始化时机）',
    '修复 /api/active-batch-tasks 接口 500 错误（过滤不可序列化的 subscribers/finished 字段）',
    "优化恢复创作任务时重放历史事件（用户离开页面期间错过的 AI 思考、工具调用、章节完成等记录）",
    "优化图片生成 API URL 自动修正（Base URL/chat/completions 自动转换为 /images/generations）",
    "优化导出格式：章节标题包含序号（第一章 测试 / 第二章 第二个），支持中文数字（1-99）",
    "新增封面保存功能：生成封面后自动保存到小说记录，详情页持久显示",
    "新增导出包含封面：HTML/Markdown 导出嵌入封面图片，TXT 导出包含封面 URL",
    "优化封面持久化：生成封面后自动下载到本地 static/covers/ 目录，避免远程 URL 过期",
    "优化导出封面：导出时复制封面图片到导出目录，HTML/MD 引用相对路径，移动文件夹后仍可显示",
    "优化封面存储：删除数据库 cover_url 字段，封面文件名固定为 novel_{id}.png，通过文件名规则查找",
    "新增侧边栏个人署名（by qiyueling2716，链接到 GitHub）",
    "新增 MIT 开源协议（LICENSE 文件）",
]
from pydantic import BaseModel

from config import BASE_DIR
from models.database import init_db, get_db
from services.llm_service import update_llm_config, get_llm_config, chat_completion, chat_completion_stream, set_active_provider
from services.vector_service import update_vector_config, get_vector_config, is_vector_available
from services.reranker_service import update_reranker_config, get_reranker_config, is_reranker_available
from services.novel_service import (
    create_novel, update_novel, get_novel, list_novels, delete_novel,
    get_chapters, get_chapter, update_chapter, delete_chapter,
    generate_chapter, check_novel_duplicates, generate_chapter_title,
    get_relationships, create_relationship, update_relationship, delete_relationship,
    sync_relationships_from_profile, generate_suggestions,
    get_characters, get_character, create_character, update_character, delete_character,
    ai_optimize_character, ai_optimize_world_building, ai_refine_relationships,
    ai_generate_outline, ai_generate_characters, extract_characters_from_chapters,
    create_chapter_manual,
    analyze_style_from_chapters_stream, analyze_style_from_text_stream,
    export_backup, import_backup,
    get_wiki_entries, create_wiki_entry, update_wiki_entry, delete_wiki_entry,
    ai_generate_wiki_entries, apply_generated_wiki_entries, WIKI_CATEGORIES,
    web_search_for_reference, generate_image, analyze_document,
    get_settings as get_image_settings, update_settings as update_image_settings,
    get_tavily_config, update_tavily_config, tavily_search,
    generate_outline,
    get_server_config, update_server_config,
    get_pending_changes, update_pending_change_status, delete_pending_change,
    update_novel,
)
from services.export_service import export_novel, EXPORTERS

# ---------- 初始化 ----------
init_db()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时加载活跃供应商配置到 LLM 运行时"""
    import logging
    # 延迟导入，避免依赖尚未初始化的模块
    try:
        from services.provider_service import apply_active_provider
        apply_active_provider()
    except Exception as e:
        logging.exception("启动时加载活跃供应商失败: %s", e)
    yield


app = FastAPI(
    title="AI Novel Writer",
    description="AI 小说写作助手，支持自定义模型、大纲/世界观/人物画像导入、剧情重复检测、导出",
    version="1.0.0",
    lifespan=lifespan,
)

# 保存后台任务引用，防止被垃圾回收（asyncio.create_task 不保存引用会被 GC 回收）
_background_tasks: set = set()
_batch_abort_flags: dict = {}  # novel_id -> asyncio.Event

# 批量创作任务状态跟踪器：novel_id -> task_status dict
# task_status 包含：novel_id, novel_title, total, completed, current_chapter, started_at, status
_active_batch_tasks: dict = {}  # novel_id -> status dict


def _register_batch_task(novel_id: str, novel_title: str, total: int):
    """注册一个批量创作任务（同时初始化 SSE 广播所需的 subscribers、finished 和 history_events）"""
    now = time.monotonic()
    _active_batch_tasks[novel_id] = {
        "novel_id": novel_id,
        "novel_title": novel_title,
        "total": total,
        "completed": 0,
        "current_chapter": 0,
        "current_chapter_number": 0,
        "started_at": now,
        "status": "running",
        "last_update": now,
        # SSE 广播相关：在注册时就初始化，确保恢复接口随时可用
        "subscribers": [],           # 订阅者 queue 列表
        "finished": asyncio.Event(),  # 完成事件
        # 历史事件缓存：用于恢复连接时重放（用户离开页面期间错过的事件）
        # 限制最大数量，超出时丢弃最早的 chunk 事件（内容片段），保留关键事件
        "history_events": [],
        "history_max": 800,  # 最大缓存事件数
    }


def _get_batch_subscribers(novel_id: str) -> list:
    """获取批量任务的订阅者列表（不存在则返回 None）"""
    t = _active_batch_tasks.get(novel_id)
    if not t:
        return None
    subs = t.get("subscribers")
    if not isinstance(subs, list):
        subs = []
        t["subscribers"] = subs
    return subs


def _get_batch_finished(novel_id: str):
    """获取批量任务的完成事件（不存在则创建并注入）"""
    t = _active_batch_tasks.get(novel_id)
    if not t:
        return None
    finished = t.get("finished")
    if finished is None:
        finished = asyncio.Event()
        t["finished"] = finished
    return finished


def _get_batch_history(novel_id: str) -> list:
    """获取批量任务的历史事件列表（用于恢复连接时重放）"""
    t = _active_batch_tasks.get(novel_id)
    if not t:
        return []
    history = t.get("history_events")
    if not isinstance(history, list):
        history = []
        t["history_events"] = history
    return history


def _trim_batch_history(novel_id: str):
    """修剪历史事件缓存，超出上限时丢弃最早的 chunk 事件"""
    t = _active_batch_tasks.get(novel_id)
    if not t:
        return
    history = t.get("history_events")
    if not isinstance(history, list):
        return
    max_size = t.get("history_max", 800)
    # 超出上限时，优先丢弃 chunk 事件（内容片段），保留关键事件
    while len(history) > max_size:
        # 找到第一个 chunk 事件并删除
        chunk_idx = next((i for i, e in enumerate(history) if isinstance(e, dict) and e.get("type") == "chunk"), None)
        if chunk_idx is not None:
            history.pop(chunk_idx)
        else:
            # 没有 chunk 事件了，丢弃最早的
            history.pop(0)


def _broadcast_batch_event(novel_id: str, msg: dict):
    """广播事件到指定小说的所有 SSE 订阅者，并缓存到历史事件列表"""
    # 1. 缓存事件到历史列表（用于恢复连接时重放）
    history = _get_batch_history(novel_id)
    if isinstance(history, list):
        history.append(msg)
        # 定期修剪（每 50 个事件检查一次，避免频繁修剪影响性能）
        if len(history) % 50 == 0:
            _trim_batch_history(novel_id)
        elif len(history) > 1000:  # 硬上限保护
            _trim_batch_history(novel_id)

    # 2. 广播到所有活跃订阅者
    subs = _get_batch_subscribers(novel_id)
    if not subs:
        return
    for sub in list(subs):
        try:
            sub.put_nowait(msg)
        except Exception:
            pass  # 队列已满或关闭，忽略


def _update_batch_task(novel_id: str, **kwargs):
    """更新批量任务状态"""
    if novel_id in _active_batch_tasks:
        _active_batch_tasks[novel_id].update(kwargs)
        _active_batch_tasks[novel_id]["last_update"] = time.monotonic()


def _unregister_batch_task(novel_id: str, status: str = "completed"):
    """标记批量任务结束"""
    if novel_id in _active_batch_tasks:
        _active_batch_tasks[novel_id]["status"] = status
        _active_batch_tasks[novel_id]["last_update"] = time.monotonic()
        # 保留 10 分钟供前端查询，之后清理
        # (实际清理由查询时检查 last_update 完成)


def _cleanup_stale_tasks():
    """清理超过 10 分钟的已完成任务"""
    now = time.monotonic()
    stale = []
    for nid, t in _active_batch_tasks.items():
        if t.get("status") in ("completed", "aborted", "failed") and now - t.get("last_update", 0) > 600:
            stale.append(nid)
    for nid in stale:
        _active_batch_tasks.pop(nid, None)


# Security: CORS restricted to localhost origins (local single-user app)
# If remote access is needed, use a reverse proxy with proper TLS
import os as _os
_cors_origins = _os.environ.get("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# ---------- 请求/响应模型 ----------

class NovelCreate(BaseModel):
    title: str = ""
    title_mode: str = "auto"
    outline: str = ""
    world_building: str = ""
    character_profiles: str = ""
    words_per_chapter: int = 3000
    duplicate_check_interval: int = 3
    summary_chapters_count: int = 3
    expected_chapters: int = 0


class NovelUpdate(BaseModel):
    title: Optional[str] = None
    title_mode: Optional[str] = None
    outline: Optional[str] = None
    world_building: Optional[str] = None
    character_profiles: Optional[str] = None
    words_per_chapter: Optional[int] = None
    duplicate_check_interval: Optional[int] = None
    summary_chapters_count: Optional[int] = None
    style_reference: Optional[str] = None
    expected_chapters: Optional[int] = None


class ChapterUpdate(BaseModel):
    content: Optional[str] = None
    title: Optional[str] = None
    status: Optional[str] = None


class LLMConfigUpdate(BaseModel):
    api_base: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.8
    max_tokens: int = 4096
    chat_path: str = ""


class VectorConfigUpdate(BaseModel):
    backend: str = "sklearn"
    model_name: str = ""
    similarity_threshold: float = 0.75
    device: str = "cpu"
    use_independent_embedding: bool = False
    embedding_api_base: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    embedding_path: str = ""


class RerankerConfigUpdate(BaseModel):
    enabled: bool = False
    use_independent: bool = False
    api_base: str = ""
    api_key: str = ""
    model: str = ""
    rerank_path: str = ""
    top_n: int = 3


class ExportRequest(BaseModel):
    format: str = "txt"
    path: str = ""
    include_meta: bool = True


class AuthSetupRequest(BaseModel):
    password: str = ""


class AuthLoginRequest(BaseModel):
    password: str = ""


class AuthVerifyRequest(BaseModel):
    token: str = ""


class BackupImportRequest(BaseModel):
    data: dict = {}
    password: str = ""  # 解密密码（如果备份已加密）
    include_config: bool = False  # 是否导入配置


class BackupExportRequest(BaseModel):
    password: str = ""  # 加密密码（空则不加密）
    include_config: bool = False  # 是否包含配置


# ---------- 认证依赖 ----------

def get_current_token(request: Request) -> str:
    """从 settings 表读取当前有效的 token，与请求头中的 token 对比。
    如果未设置密码，则放行。"""
    conn = get_db()
    try:
        row = conn.execute("SELECT auth_password, auth_token FROM settings WHERE key = 'auth'").fetchone()
    finally:
        conn.close()

    # 如果未设置密码，直接放行
    if not row or not row["auth_password"]:
        return ""

    # 需要认证
    auth_token = row["auth_token"] or ""
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    # 安全实践：使用常量时间比较防止时序攻击
    import secrets
    if not token or not secrets.compare_digest(token, auth_token):
        raise HTTPException(401, "未认证，请先登录")
    return token


# ==================== 小说 API ====================

@app.get("/api/novels", dependencies=[Depends(get_current_token)])
def api_list_novels():
    return {"novels": list_novels()}


@app.post("/api/novels", dependencies=[Depends(get_current_token)])
def api_create_novel(data: NovelCreate):
    novel = create_novel(
        title=data.title,
        title_mode=data.title_mode,
        outline=data.outline,
        world_building=data.world_building,
        character_profiles=data.character_profiles,
        words_per_chapter=data.words_per_chapter,
        duplicate_check_interval=data.duplicate_check_interval,
        summary_chapters_count=data.summary_chapters_count,
        expected_chapters=data.expected_chapters,
    )
    return {"novel": novel}


@app.get("/api/novels/{novel_id}", dependencies=[Depends(get_current_token)])
def api_get_novel(novel_id: str):
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")
    return {"novel": novel}


@app.put("/api/novels/{novel_id}", dependencies=[Depends(get_current_token)])
def api_update_novel(novel_id: str, data: NovelUpdate):
    kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
    novel = update_novel(novel_id, **kwargs)
    if not novel:
        raise HTTPException(404, "小说不存在")
    return {"novel": novel}


@app.delete("/api/novels/{novel_id}", dependencies=[Depends(get_current_token)])
def api_delete_novel(novel_id: str):
    delete_novel(novel_id)
    return {"ok": True}


# ==================== 小说导入 ====================

@app.post("/api/novels/{novel_id}/import", dependencies=[Depends(get_current_token)])
async def api_import_files(
    novel_id: str,
    outline_file: Optional[UploadFile] = File(None),
    world_file: Optional[UploadFile] = File(None),
    character_file: Optional[UploadFile] = File(None),
):
    """导入大纲、世界观、人物画像文件"""
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")

    updates = {}
    if outline_file:
        updates["outline"] = (await outline_file.read()).decode("utf-8")
    if world_file:
        updates["world_building"] = (await world_file.read()).decode("utf-8")
    if character_file:
        updates["character_profiles"] = (await character_file.read()).decode("utf-8")

    if updates:
        novel = update_novel(novel_id, **updates)
    return {"novel": novel}


# ==================== 章节 API ====================

@app.get("/api/novels/{novel_id}/chapters", dependencies=[Depends(get_current_token)])
def api_get_chapters(novel_id: str):
    return {"chapters": get_chapters(novel_id)}


@app.get("/api/chapters/{chapter_id}", dependencies=[Depends(get_current_token)])
def api_get_chapter(chapter_id: str):
    ch = get_chapter(chapter_id)
    if not ch:
        raise HTTPException(404, "章节不存在")
    return {"chapter": ch}


@app.put("/api/chapters/{chapter_id}", dependencies=[Depends(get_current_token)])
def api_update_chapter(chapter_id: str, data: ChapterUpdate):
    kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
    if "content" in kwargs:
        kwargs["words_count"] = len(kwargs["content"])
    ch = update_chapter(chapter_id, **kwargs)
    if not ch:
        raise HTTPException(404, "章节不存在")
    return {"chapter": ch}


@app.delete("/api/chapters/{chapter_id}", dependencies=[Depends(get_current_token)])
def api_delete_chapter(chapter_id: str):
    delete_chapter(chapter_id)
    return {"ok": True}


@app.put("/api/novels/{novel_id}/chapters/reorder", dependencies=[Depends(get_current_token)])
def api_reorder_chapters(novel_id: str, data: dict = Body(...)):
    """重排章节顺序。data: {"chapter_ids": ["id1", "id2", ...]}
    使用两步更新（先设为负数避免 UNIQUE 约束冲突）"""
    chapter_ids = data.get("chapter_ids", [])
    if not chapter_ids:
        raise HTTPException(400, "章节列表不能为空")
    from contextlib import closing
    from models.database import get_db
    # 校验所有章节 ID 都属于该小说
    with closing(get_db()) as conn:
        valid_ids = {row["id"] for row in conn.execute(
            "SELECT id FROM chapters WHERE novel_id=?", (novel_id,)
        ).fetchall()}
        for cid in chapter_ids:
            if cid not in valid_ids:
                raise HTTPException(400, f"章节 {cid} 不属于该小说")
        try:
            # 两步更新：先把所有章节号设为负数（避免 UNIQUE 约束冲突），再设为新序号
            # 使用临时负数偏移：-1, -2, -3...（不会与正数冲突）
            for i, cid in enumerate(chapter_ids, 1):
                conn.execute(
                    "UPDATE chapters SET number=? WHERE id=? AND novel_id=?",
                    (-i, cid, novel_id),
                )
            for i, cid in enumerate(chapter_ids, 1):
                conn.execute(
                    "UPDATE chapters SET number=? WHERE id=? AND novel_id=?",
                    (i, cid, novel_id),
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise HTTPException(400, f"重排失败: {e}")
    return {"ok": True}


@app.post("/api/novels/{novel_id}/chapters/generate", dependencies=[Depends(get_current_token)])
async def api_generate_chapter(
    novel_id: str,
    chapter_title: str = Form(""),
    chapter_number: Optional[int] = Form(None),
    provider_id: str = Form(""),
    max_tokens: Optional[int] = Form(None),
):
    """生成新章节（流式）；可指定 provider_id 选择供应商，max_tokens 覆盖 token 预算"""
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")

    # 如果指定了 provider_id，临时切换供应商
    prev_provider = None
    if provider_id:
        from services.provider_service import get_provider as get_prov
        provider = get_prov(provider_id)
        if provider:
            from services.llm_service import _active_provider
            prev_provider = _active_provider
            set_active_provider(provider)

    chapters = get_chapters(novel_id)
    if chapter_number is None:
        # 使用最大章节号 + 1，而非 len + 1，避免删除章节后产生号冲突
        chapter_number = max((ch["number"] for ch in chapters), default=0) + 1

    # 流式返回（使用 asyncio.Queue 避免阻塞事件循环）
    stream_queue: asyncio.Queue = asyncio.Queue()
    finished = asyncio.Event()

    async def stream_callback(msg):
        # 兼容两种格式：纯字符串 chunk 或 dict 事件
        if isinstance(msg, str):
            stream_queue.put_nowait({"type": "chunk", "data": msg})
        elif isinstance(msg, dict):
            stream_queue.put_nowait(msg)

    async def generate_task():
        try:
            chapter = await generate_chapter(
                novel_id, chapter_number, chapter_title,
                stream_callback=stream_callback,
                max_tokens_override=max_tokens,
            )
            stream_queue.put_nowait({"type": "done", "chapter": chapter})
        except Exception as e:
            stream_queue.put_nowait({"type": "error", "message": str(e)})
        finally:
            # 恢复之前的供应商
            if prev_provider is not None:
                set_active_provider(prev_provider)
            finished.set()

    # 保存后台任务引用，防止被垃圾回收
    task = asyncio.create_task(generate_task())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    async def event_stream():
        while not finished.is_set() or not stream_queue.empty():
            try:
                msg = await asyncio.wait_for(stream_queue.get(), timeout=15.0)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                # SSE 心跳，防止代理超时断开
                yield ": heartbeat\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/novels/{novel_id}/chapters/generate-title", dependencies=[Depends(get_current_token)])
async def api_generate_chapter_title_endpoint(novel_id: str):
    """为已生成内容自动取标题（用于手动模式）"""
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")

    chapters = get_chapters(novel_id)
    if not chapters:
        raise HTTPException(400, "暂无章节")

    last_chapter = chapters[-1]
    title = await generate_chapter_title(novel, last_chapter["content"], last_chapter["number"])
    update_chapter(last_chapter["id"], title=title)
    return {"title": title}


@app.get("/api/novels/{novel_id}/chapter-status", dependencies=[Depends(get_current_token)])
def api_chapter_status(novel_id: str):
    """获取章节状态，包括是否达到预期章节数"""
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")
    chapters = get_chapters(novel_id)
    expected = novel.get("expected_chapters", 0)
    current = len(chapters)
    return {
        "current_chapters": current,
        "expected_chapters": expected,
        "reached_expected": expected > 0 and current >= expected,
        "is_extras": expected > 0 and current > expected,
        "message": f"已写 {current} 章" + (f" / 预期 {expected} 章" if expected > 0 else ""),
    }


# ==================== AI 润色 & 扩写 ====================

class PolishRequest(BaseModel):
    content: str
    chapter_id: str = ""


@app.post("/api/novels/ai-polish", dependencies=[Depends(get_current_token)])
async def api_ai_polish(data: PolishRequest):
    """AI 润色章节内容"""
    try:
        # 获取该章节所属小说的上下文
        chapter = get_chapter(data.chapter_id) if data.chapter_id else None
        system_prompt = "你是一位专业的小说编辑。请润色以下小说段落，保持原有风格和情节不变，提升文笔质量。只输出润色后的内容。"
        if chapter:
            novel = get_novel(chapter["novel_id"])
            if novel and novel.get("world_building"):
                system_prompt += f"\n\n世界观背景：{novel['world_building'][:500]}"

        resp = await chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请润色以下小说内容：\n\n{data.content}"},
            ],
            temperature=0.6,
        )
        polished = resp["choices"][0]["message"]["content"].strip()
        return {"polished": polished}
    except Exception as e:
        raise HTTPException(500, f"润色失败: {str(e)}")


class ExpandRequest(BaseModel):
    content: str
    chapter_id: str = ""


@app.post("/api/novels/ai-expand", dependencies=[Depends(get_current_token)])
async def api_ai_expand(data: ExpandRequest):
    """AI 扩写章节内容"""
    try:
        chapter = get_chapter(data.chapter_id) if data.chapter_id else None
        system_prompt = "你是一位专业的小说作家。请扩写以下小说段落，增加细节描写、心理活动和场景渲染，保持原有风格和情节不变。扩写后内容约为原文的1.5倍长。只输出扩写后的内容。"
        if chapter:
            novel = get_novel(chapter["novel_id"])
            if novel and novel.get("world_building"):
                system_prompt += f"\n\n世界观背景：{novel['world_building'][:500]}"

        resp = await chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请扩写以下小说内容：\n\n{data.content}"},
            ],
            temperature=0.7,
            max_tokens=8192,
        )
        expanded = resp["choices"][0]["message"]["content"].strip()
        return {"expanded": expanded}
    except Exception as e:
        raise HTTPException(500, f"扩写失败: {str(e)}")


# ==================== 剧情重复检测 ====================

@app.post("/api/novels/{novel_id}/check-duplicates", dependencies=[Depends(get_current_token)])
async def api_check_duplicates(novel_id: str):
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")
    vector_available = is_vector_available()
    if not vector_available:
        return {"duplicates": [], "vector_available": False}
    duplicates = await check_novel_duplicates(novel_id)
    return {"duplicates": duplicates, "vector_available": True}


# ==================== 导出 API ====================

@app.post("/api/novels/{novel_id}/export", dependencies=[Depends(get_current_token)])
def api_export_novel(novel_id: str, data: ExportRequest):
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")
    chapters = get_chapters(novel_id)
    if not chapters:
        raise HTTPException(400, "没有章节可导出")

    try:
        filepath = export_novel(novel, chapters, data.format, data.path, include_meta=data.include_meta)
        return {"filepath": filepath, "format": data.format}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/novels/{novel_id}/download/{fmt}", dependencies=[Depends(get_current_token)])
def api_download_novel(novel_id: str, fmt: str, include_meta: bool = True):
    """直接下载导出文件"""
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")
    chapters = get_chapters(novel_id)
    if not chapters:
        raise HTTPException(400, "没有章节可导出")

    try:
        filepath = export_novel(novel, chapters, fmt, include_meta=include_meta)
    except ValueError as e:
        raise HTTPException(400, str(e))
    filename = Path(filepath).name
    media_types = {"txt": "text/plain", "html": "text/html", "md": "text/markdown"}
    return FileResponse(
        filepath,
        media_type=media_types.get(fmt, "application/octet-stream"),
        filename=filename,
    )


# ==================== 配置 API ====================

@app.get("/api/config/llm", dependencies=[Depends(get_current_token)])
def api_get_llm_config():
    cfg = get_llm_config()
    return {
        "api_base": cfg.get("api_base", ""),
        "api_key": cfg.get("api_key", "")[:8] + "***" if cfg.get("api_key") else "",
        "model": cfg.get("model", ""),
        "temperature": cfg.get("temperature", 0.8),
        "max_tokens": cfg.get("max_tokens", 4096),
        "chat_path": cfg.get("chat_path", "/chat/completions"),
    }


@app.put("/api/config/llm", dependencies=[Depends(get_current_token)])
def api_update_llm_config(data: LLMConfigUpdate):
    # api_key 以 "***" 结尾说明未修改，不覆盖
    api_key = data.api_key
    if api_key.endswith("***"):
        api_key = ""
    update_llm_config(
        api_base=data.api_base,
        api_key=api_key,
        model=data.model,
        temperature=data.temperature,
        max_tokens=data.max_tokens,
        chat_path=data.chat_path,
    )
    return {"ok": True, "config": api_get_llm_config()}


@app.get("/api/config/vector", dependencies=[Depends(get_current_token)])
def api_get_vector_config():
    cfg = get_vector_config()
    return {
        **cfg,
        "embedding_api_key": cfg.get("embedding_api_key", "")[:8] + "***" if cfg.get("embedding_api_key") else "",
    }


@app.put("/api/config/vector", dependencies=[Depends(get_current_token)])
def api_update_vector_config(data: VectorConfigUpdate):
    # embedding_api_key 以 "***" 结尾说明未修改，不覆盖
    emb_key = data.embedding_api_key
    if emb_key.endswith("***"):
        emb_key = ""
    update_vector_config(
        backend=data.backend,
        model_name=data.model_name,
        similarity_threshold=data.similarity_threshold,
        device=data.device,
        use_independent_embedding=data.use_independent_embedding,
        embedding_api_base=data.embedding_api_base,
        embedding_api_key=emb_key,
        embedding_model=data.embedding_model,
        embedding_path=data.embedding_path,
    )
    return {"ok": True, "config": api_get_vector_config()}


# ==================== Reranker 配置 API ====================

@app.get("/api/config/reranker", dependencies=[Depends(get_current_token)])
def api_get_reranker_config():
    cfg = get_reranker_config()
    return {
        "enabled": cfg.get("enabled", False),
        "use_independent": cfg.get("use_independent", False),
        "api_base": cfg.get("api_base", ""),
        "api_key": cfg.get("api_key", "")[:8] + "***" if cfg.get("api_key") else "",
        "model": cfg.get("model", ""),
        "rerank_path": cfg.get("rerank_path", "/rerank"),
        "top_n": cfg.get("top_n", 3),
    }


@app.put("/api/config/reranker", dependencies=[Depends(get_current_token)])
def api_update_reranker_config(data: RerankerConfigUpdate):
    # api_key 以 "***" 结尾说明未修改，传 None 表示不更新
    api_key = data.api_key
    if api_key and api_key.endswith("***"):
        api_key = None  # None = 未修改
    update_reranker_config(
        enabled=data.enabled,
        use_independent=data.use_independent,
        api_base=data.api_base,
        api_key=api_key,
        model=data.model,
        rerank_path=data.rerank_path,
        top_n=data.top_n,
    )
    return {"ok": True, "config": api_get_reranker_config()}


@app.get("/api/config/reranker/status", dependencies=[Depends(get_current_token)])
def api_reranker_status():
    cfg = get_reranker_config()
    available = is_reranker_available()
    return {
        "enabled": cfg.get("enabled", False),
        "available": available,
    }


# ==================== 供应商管理 API ====================

from services.provider_service import (
    list_providers, get_provider, create_provider, update_provider,
    delete_provider, set_active_provider as svc_set_active, duplicate_provider,
    apply_active_provider,
)


class ProviderCreate(BaseModel):
    name: str = ""
    api_base: str = ""
    api_key: str = ""
    model: str = ""
    chat_path: str = "/chat/completions"
    temperature: float = 0.8
    max_tokens: int = 4096


class ProviderUpdate(BaseModel):
    name: Optional[str] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    chat_path: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@app.get("/api/providers", dependencies=[Depends(get_current_token)])
def api_list_providers():
    return {"providers": list_providers(mask_keys=True)}


@app.post("/api/providers", dependencies=[Depends(get_current_token)])
def api_create_provider(data: ProviderCreate):
    p = create_provider(
        name=data.name, api_base=data.api_base, api_key=data.api_key,
        model=data.model, chat_path=data.chat_path,
        temperature=data.temperature, max_tokens=data.max_tokens,
    )
    return {"provider": p}


@app.put("/api/providers/{provider_id}", dependencies=[Depends(get_current_token)])
def api_update_provider(provider_id: str, data: ProviderUpdate):
    kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
    # api_key 以 "***" 结尾说明未修改，不覆盖
    if "api_key" in kwargs and kwargs["api_key"].endswith("***"):
        del kwargs["api_key"]
    p = update_provider(provider_id, **kwargs)
    if not p:
        raise HTTPException(404, "供应商不存在")
    return {"provider": p}


@app.delete("/api/providers/{provider_id}", dependencies=[Depends(get_current_token)])
def api_delete_provider(provider_id: str):
    if not delete_provider(provider_id):
        raise HTTPException(400, "无法删除最后一个供应商")
    # 如果删除的是活跃供应商，重新应用运行时配置
    from services.llm_service import apply_active_provider
    apply_active_provider()
    return {"ok": True}


@app.post("/api/providers/{provider_id}/activate", dependencies=[Depends(get_current_token)])
def api_set_active_provider(provider_id: str):
    p = svc_set_active(provider_id)
    if not p:
        raise HTTPException(404, "供应商不存在")
    # 同步到 llm_service 运行时
    set_active_provider(p)
    return {"provider": p, "ok": True}


@app.get("/api/config/llm/debug", dependencies=[Depends(get_current_token)])
def api_debug_llm_config():
    """调试端点：查看当前 LLM 运行时配置（key 掩码）"""
    cfg = get_llm_config()
    masked = {**cfg}
    if masked.get("api_key"):
        k = masked["api_key"]
        masked["api_key"] = k[:8] + "***" if len(k) > 8 else "***"
    # 显示构建出的完整 URL
    from services.llm_service import _build_url
    masked["full_url"] = _build_url(cfg)
    masked["_active_provider_set"] = "_active_provider is set" if cfg else "none"
    return masked


@app.post("/api/providers/{provider_id}/duplicate", dependencies=[Depends(get_current_token)])
def api_duplicate_provider(provider_id: str):
    p = duplicate_provider(provider_id)
    if not p:
        raise HTTPException(404, "供应商不存在")
    return {"provider": p}


# ==================== 人物关系 API ====================

class RelationshipCreate(BaseModel):
    character_a: str = ""
    character_b: str = ""
    relation_type: str = ""
    description: str = ""


class RelationshipUpdate(BaseModel):
    character_a: Optional[str] = None
    character_b: Optional[str] = None
    relation_type: Optional[str] = None
    description: Optional[str] = None


@app.get("/api/novels/{novel_id}/relationships", dependencies=[Depends(get_current_token)])
def api_get_relationships(novel_id: str):
    return {"relationships": get_relationships(novel_id)}


@app.post("/api/novels/{novel_id}/relationships", dependencies=[Depends(get_current_token)])
def api_create_relationship(novel_id: str, data: RelationshipCreate):
    rel = create_relationship(
        novel_id, data.character_a, data.character_b,
        data.relation_type, data.description,
    )
    return {"relationship": rel}


@app.put("/api/relationships/{rel_id}", dependencies=[Depends(get_current_token)])
def api_update_relationship(rel_id: str, data: RelationshipUpdate):
    # 操作前验证关系存在，防止对不存在的资源执行更新
    conn = get_db()
    try:
        row = conn.execute("SELECT id FROM character_relationships WHERE id = ?", (rel_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, "关系不存在")
    kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
    rel = update_relationship(rel_id, **kwargs)
    if not rel:
        raise HTTPException(404, "关系不存在")
    return {"relationship": rel}


@app.delete("/api/relationships/{rel_id}", dependencies=[Depends(get_current_token)])
def api_delete_relationship(rel_id: str):
    # 操作前验证关系存在，防止静默删除不存在的资源
    conn = get_db()
    try:
        row = conn.execute("SELECT id FROM character_relationships WHERE id = ?", (rel_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, "关系不存在")
    delete_relationship(rel_id)
    return {"ok": True}


@app.post("/api/novels/{novel_id}/relationships/sync", dependencies=[Depends(get_current_token)])
def api_sync_relationships(novel_id: str):
    """从人物画像同步角色到关系表"""
    rels = sync_relationships_from_profile(novel_id)
    return {"relationships": rels}


# ==================== 人物画像 API ====================

class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    profile: Optional[str] = None


@app.get("/api/novels/{novel_id}/characters", dependencies=[Depends(get_current_token)])
def api_get_characters(novel_id: str):
    return {"characters": get_characters(novel_id)}


@app.post("/api/novels/{novel_id}/characters/upload", dependencies=[Depends(get_current_token)])
async def api_upload_characters(novel_id: str, files: list[UploadFile] = File(...)):
    """上传多个 .txt 文件，文件名作为人物名，内容作为画像"""
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")

    if len(files) > 50:
        raise HTTPException(400, "单次最多上传 50 个文件")

    created = []
    for file in files:
        content_bytes = await file.read()
        if len(content_bytes) > 100_000:  # 100KB per file
            raise HTTPException(400, f"文件 {file.filename} 超过 100KB 限制")
        name = Path(file.filename or "unknown.txt").stem
        content = content_bytes.decode("utf-8")
        char = create_character(novel_id, name, content)
        created.append(char)

    return {"characters": created}


@app.put("/api/novels/{novel_id}/characters/{char_id}", dependencies=[Depends(get_current_token)])
def api_update_character(novel_id: str, char_id: str, data: CharacterUpdate):
    # 验证人物归属该小说，防止越权操作其他小说的人物
    existing = get_character(char_id)
    if not existing or existing.get("novel_id") != novel_id:
        raise HTTPException(404, "人物不存在")
    kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
    char = update_character(char_id, **kwargs)
    if not char:
        raise HTTPException(404, "人物不存在")
    return {"character": char}


@app.delete("/api/novels/{novel_id}/characters/{char_id}", dependencies=[Depends(get_current_token)])
def api_delete_character(novel_id: str, char_id: str):
    # 验证人物归属该小说，防止越权删除其他小说的人物
    existing = get_character(char_id)
    if not existing or existing.get("novel_id") != novel_id:
        raise HTTPException(404, "人物不存在")
    delete_character(char_id)
    return {"ok": True}


@app.post("/api/novels/{novel_id}/characters/ai-optimize", dependencies=[Depends(get_current_token)])
async def api_ai_optimize_characters(novel_id: str):
    """批量 AI 优化所有人物画像"""
    characters = get_characters(novel_id)
    if not characters:
        raise HTTPException(400, "请先添加人物画像")

    optimized = []
    for c in characters:
        try:
            updated = await ai_optimize_character(novel_id, c["id"])
            optimized.append(updated)
        except Exception as e:
            optimized.append({"id": c["id"], "name": c["name"], "error": str(e)})

    return {"characters": optimized}


@app.post("/api/novels/{novel_id}/characters/{char_id}/ai-optimize", dependencies=[Depends(get_current_token)])
async def api_ai_optimize_single_character(novel_id: str, char_id: str):
    try:
        char = await ai_optimize_character(novel_id, char_id)
        return {"character": char}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"优化失败: {str(e)}")


@app.post("/api/novels/{novel_id}/characters/ai-generate", dependencies=[Depends(get_current_token)])
async def api_ai_generate_characters(novel_id: str, data: dict = Body(default={})):
    """AI 根据大纲和世界观自动生成人物画像（预览，不直接保存）"""
    try:
        custom_prompt = data.get("custom_prompt", "") if data else ""
        result = await ai_generate_characters(novel_id, custom_prompt)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"生成失败: {str(e)}")


@app.post("/api/novels/{novel_id}/characters/apply-generated", dependencies=[Depends(get_current_token)])
async def api_apply_generated_characters(novel_id: str, data: dict = Body(...)):
    """应用 AI 生成的角色（前端选择后调用）"""
    characters = data.get("characters", [])
    if not characters:
        raise HTTPException(400, "角色列表不能为空")
    created = []
    for c in characters:
        name = c.get("name", "").strip()
        if not name:
            continue
        char = create_character(novel_id, name, c.get("profile", ""))
        created.append(char)
    return {"characters": created, "count": len(created)}


@app.post("/api/novels/{novel_id}/characters/extract-from-chapters", dependencies=[Depends(get_current_token)])
async def api_extract_characters(novel_id: str):
    """从已写章节提取角色和关系（预览）"""
    try:
        result = await extract_characters_from_chapters(novel_id)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"提取失败: {str(e)}")


@app.post("/api/novels/{novel_id}/relationships/apply-extracted", dependencies=[Depends(get_current_token)])
async def api_apply_extracted_relationships(novel_id: str, data: dict = Body(...)):
    """应用从章节提取的关系（前端选择后调用）"""
    relationships = data.get("relationships", [])
    if not relationships:
        raise HTTPException(400, "关系列表不能为空")
    created = []
    for r in relationships:
        a = r.get("character_a", "").strip()
        b = r.get("character_b", "").strip()
        if not a or not b:
            continue
        rel = create_relationship(novel_id, a, b, r.get("relation_type", "其他"), r.get("description", ""))
        created.append(rel)
    return {"relationships": created, "count": len(created)}


@app.post("/api/novels/{novel_id}/ai-optimize-world", dependencies=[Depends(get_current_token)])
async def api_ai_optimize_world(novel_id: str, data: dict = Body(default={})):
    try:
        custom_prompt = data.get("custom_prompt", "") if data else ""
        result = await ai_optimize_world_building(novel_id, custom_prompt)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"优化失败: {str(e)}")


@app.post("/api/novels/{novel_id}/ai-generate-outline", dependencies=[Depends(get_current_token)])
async def api_ai_generate_outline(novel_id: str):
    """AI 根据小说设定和已有内容生成大纲"""
    try:
        result = await ai_generate_outline(novel_id)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"生成失败: {str(e)}")


# ==================== 大纲生成（增强版） ====================

class OutlineGenerateRequest(BaseModel):
    custom_prompt: str = ""


@app.post("/api/novels/{novel_id}/generate-outline", dependencies=[Depends(get_current_token)])
async def api_generate_outline(novel_id: str, data: OutlineGenerateRequest):
    try:
        outline = await generate_outline(novel_id, data.custom_prompt)
        return {"outline": outline}
    except Exception as e:
        raise HTTPException(500, f"大纲生成失败: {str(e)}")


# ==================== AI 关系细化 ====================

@app.post("/api/novels/{novel_id}/relationships/ai-refine", dependencies=[Depends(get_current_token)])
async def api_ai_refine_relationships(novel_id: str):
    """AI 根据全部上下文（大纲、世界观、人物、章节）分析并细化人物关系"""
    try:
        result = await ai_refine_relationships(novel_id)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"AI 分析失败: {str(e)}")


# ==================== 文风分析 API ====================

class AnalyzeStyleRequest(BaseModel):
    chapter_ids: list[str] = []


@app.post("/api/novels/{novel_id}/analyze-style", dependencies=[Depends(get_current_token)])
async def api_analyze_style(novel_id: str, data: AnalyzeStyleRequest):
    """从选中的章节分析文风（流式）"""
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")
    if not data.chapter_ids:
        raise HTTPException(400, "请至少选择一个章节")
    if len(data.chapter_ids) > 10:
        raise HTTPException(400, "最多选择 10 个章节进行分析")

    async def event_stream():
        try:
            async for event_type, payload in analyze_style_from_chapters_stream(novel_id, data.chapter_ids):
                if event_type == "chunk":
                    yield f"data: {json.dumps({'type': 'chunk', 'data': payload}, ensure_ascii=False)}\n\n"
                elif event_type == "done":
                    yield f"data: {json.dumps({'type': 'done', 'style_reference': payload}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except ValueError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        except Exception:
            import logging
            logging.exception("文风分析失败")
            yield f"data: {json.dumps({'type': 'error', 'message': '分析失败，请检查 LLM 供应商配置'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/novels/{novel_id}/analyze-style-upload", dependencies=[Depends(get_current_token)])
async def api_analyze_style_upload(novel_id: str, file: UploadFile = File(...)):
    """从上传的文档分析文风（流式）"""
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")

    content_bytes = await file.read()
    if len(content_bytes) > 500_000:
        raise HTTPException(400, "文件超过 500KB 限制")
    try:
        text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "文件编码不支持，请使用 UTF-8 编码的文本文件")

    async def event_stream():
        try:
            async for event_type, payload in analyze_style_from_text_stream(text, novel_id):
                if event_type == "chunk":
                    yield f"data: {json.dumps({'type': 'chunk', 'data': payload}, ensure_ascii=False)}\n\n"
                elif event_type == "done":
                    yield f"data: {json.dumps({'type': 'done', 'style_reference': payload}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except ValueError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        except Exception:
            import logging
            logging.exception("文风分析失败")
            yield f"data: {json.dumps({'type': 'error', 'message': '分析失败，请检查 LLM 供应商配置'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ==================== 手动创建章节 API ====================

class ManualChapterCreate(BaseModel):
    title: str = ""
    content: str = ""
    chapter_number: Optional[int] = None


@app.post("/api/novels/{novel_id}/chapters/manual", dependencies=[Depends(get_current_token)])
def api_create_chapter_manual(novel_id: str, data: ManualChapterCreate):
    """手动创建章节（不调用AI）"""
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")
    chapter = create_chapter_manual(
        novel_id, data.title, data.content, data.chapter_number,
    )
    return {"chapter": chapter}


# ==================== 建议 API ====================

@app.post("/api/novels/{novel_id}/suggestions", dependencies=[Depends(get_current_token)])
async def api_get_suggestions(novel_id: str):
    try:
        result = await generate_suggestions(novel_id)
        return result
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"生成建议失败: {str(e)}")


# ==================== 向量状态 API ====================

@app.get("/api/config/vector/status", dependencies=[Depends(get_current_token)])
def api_vector_status():
    available = is_vector_available()
    cfg = get_vector_config()
    return {
        "available": available,
        "backend": cfg.get("backend", "sklearn"),
        "backend_label": {
            "sklearn": "sklearn TF-IDF",
            "sentence_transformers": "sentence-transformers",
            "openai": "自定义 Embedding API",
        }.get(cfg.get("backend", "sklearn"), cfg.get("backend", "sklearn")),
    }


# ==================== 认证 API ====================

@app.post("/api/auth/setup")
def api_auth_setup(data: AuthSetupRequest):
    """首次设置密码"""
    conn = get_db()
    try:
        row = conn.execute("SELECT auth_password FROM settings WHERE key = 'auth'").fetchone()
        if row and row["auth_password"]:
            raise HTTPException(403, "密码已设置，无法重复设置")

        password_hash = bcrypt.hashpw(data.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        token = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO settings (key, value, auth_password, auth_token)
               VALUES ('auth', '', ?, ?)
               ON CONFLICT(key) DO UPDATE SET auth_password=?, auth_token=?""",
            (password_hash, token, password_hash, token),
        )
        conn.commit()
        return {"token": token, "message": "密码设置成功"}
    finally:
        conn.close()


@app.post("/api/auth/login")
def api_auth_login(data: AuthLoginRequest):
    """验证密码，返回 session token"""
    conn = get_db()
    try:
        row = conn.execute("SELECT auth_password FROM settings WHERE key = 'auth'").fetchone()
    finally:
        conn.close()

    if not row or not row["auth_password"]:
        raise HTTPException(400, "尚未设置密码，请先设置密码")

    stored_hash = row["auth_password"].encode("utf-8")
    if not bcrypt.checkpw(data.password.encode("utf-8"), stored_hash):
        raise HTTPException(401, "密码错误")

    token = str(uuid.uuid4())
    conn = get_db()
    try:
        conn.execute(
            "UPDATE settings SET auth_token = ? WHERE key = 'auth'",
            (token,),
        )
        conn.commit()
    finally:
        conn.close()
    return {"token": token, "message": "登录成功"}


@app.get("/api/version")
def api_version():
    """返回应用版本信息（无需认证，用于前端显示和诊断）"""
    import platform
    return {
        "version": APP_VERSION,
        "notes": APP_VERSION_NOTES,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


@app.get("/api/auth/status")
def api_auth_status():
    """返回是否已设置密码"""
    conn = get_db()
    try:
        row = conn.execute("SELECT auth_password FROM settings WHERE key = 'auth'").fetchone()
    finally:
        conn.close()
    is_setup = bool(row and row["auth_password"])
    return {"is_setup": is_setup}


@app.post("/api/auth/verify")
def api_auth_verify(data: AuthVerifyRequest):
    """验证 token 是否有效"""
    conn = get_db()
    try:
        row = conn.execute("SELECT auth_password, auth_token FROM settings WHERE key = 'auth'").fetchone()
    finally:
        conn.close()

    # 未设置密码，token 验证无意义，直接返回有效
    if not row or not row["auth_password"]:
        return {"valid": True}

    # Security: 使用常量时间比较防止时序攻击
    if data.token and secrets.compare_digest(data.token, row["auth_token"] or ""):
        return {"valid": True}

    return {"valid": False}


# ==================== 备份迁移 API ====================

@app.post("/api/backup/export", dependencies=[Depends(get_current_token)])
def api_backup_export(body: BackupExportRequest):
    """导出全部数据为 JSON
    
    - include_config=True 时包含配置（providers/vector/reranker/image/tavily）
    - password 非空时用密码加密整个备份（密钥相关字段会以加密形式存储）
    - 无 password 时导出明文备份（兼容旧行为）
    """
    from services.secret_service import encrypt_backup_data, is_encryption_available
    
    data = export_backup(include_config=body.include_config)
    
    # 如果提供了密码，加密整个备份
    if body.password:
        if not is_encryption_available():
            raise HTTPException(500, "加密库未安装，无法加密备份。请运行: pip install cryptography")
        data = encrypt_backup_data(data, body.password)
    
    return data


@app.post("/api/backup/import", dependencies=[Depends(get_current_token)])
def api_backup_import(body: BackupImportRequest):
    """导入备份数据
    
    - 自动检测备份是否加密（_encrypted=true）
    - 如果加密，用 password 解密
    - include_config=True 时导入配置
    - 兼容旧版明文备份（无 _encrypted 字段）
    """
    from services.secret_service import decrypt_backup_data, is_backup_encrypted, is_encryption_available
    
    data = body.data
    
    # 检测是否加密
    if is_backup_encrypted(data):
        if not body.password:
            raise HTTPException(400, "此备份已加密，请输入密码")
        if not is_encryption_available():
            raise HTTPException(500, "加密库未安装，无法解密备份。请运行: pip install cryptography")
        try:
            data = decrypt_backup_data(data, body.password)
        except Exception as e:
            raise HTTPException(400, f"解密失败：密码错误或备份损坏（{str(e)}）")
    
    # 检测是否是 v1 旧格式（无 _version 字段）
    is_v1 = "_version" not in data
    
    result = import_backup(data, include_config=body.include_config)
    
    # 对 v1 旧格式备份，提示用户重新导出以升级格式
    if is_v1:
        result["format_upgraded"] = False
        result["message"] = "检测到 v1 旧格式备份，已成功导入。建议重新导出以升级到 v2 格式（支持百科条目、待确认变更等新数据）"
    else:
        result["format_upgraded"] = True
    
    return {"ok": True, "imported": result}


# ==================== 连续创作 API ====================

@app.post("/api/novels/{novel_id}/chapters/batch-generate", dependencies=[Depends(get_current_token)])
async def api_batch_generate_chapters(
    novel_id: str,
    chapter_count: Optional[int] = Form(None),
    provider_id: str = Form(""),
    suggestions: str = Form(""),
    chapter_suggestions: str = Form(""),  # JSON 数组，每章的创作走向，如 ["走向1", "走向2", ...]
):
    """连续生成多个章节（SSE 流式）

    参数：
    - chapter_count: 章节数量
    - provider_id: 供应商 ID
    - suggestions: 整体创作建议（作用于第一章）
    - chapter_suggestions: 每章独立的创作走向（JSON 数组），优先级高于 suggestions
    """
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")

    # 如果指定了 provider_id，临时切换供应商
    prev_provider = None
    if provider_id:
        from services.provider_service import get_provider as get_prov
        provider = get_prov(provider_id)
        if provider:
            from services.llm_service import _active_provider
            prev_provider = _active_provider
            set_active_provider(provider)

    # 确定生成章节数量，默认等于 summary_chapters_count
    if chapter_count is None:
        chapter_count = novel.get("summary_chapters_count", 3)

    # 校验章节数量范围
    if chapter_count < 1 or chapter_count > 50:
        # 恢复之前的供应商，避免临时切换残留
        if prev_provider is not None:
            set_active_provider(prev_provider)
        raise HTTPException(400, "章节数须在 1-50 之间")

    # 流式返回（广播模式：支持多个订阅者，用户离开页面后可恢复）
    # subscribers 和 finished 在 _register_batch_task 中已初始化到字典
    # 这里从字典获取引用，确保所有地方用的是同一份
    finished = _get_batch_finished(novel_id) or asyncio.Event()
    batch_abort = asyncio.Event()  # 中止标志

    # 解析每章独立的创作走向（JSON 数组）
    per_chapter_suggestions = []
    if chapter_suggestions:
        try:
            parsed = json.loads(chapter_suggestions)
            if isinstance(parsed, list):
                per_chapter_suggestions = [str(s) if s else "" for s in parsed]
        except (json.JSONDecodeError, TypeError):
            pass

    async def batch_task():
        try:
            # 预计算起始章节号，整个批次内递增（失败也跳过，避免重复生成同一章）
            existing_chapters = get_chapters(novel_id)
            base_number = max((ch["number"] for ch in existing_chapters), default=0) + 1

            # 注册批量任务状态（subscribers 和 finished 已在 _register_batch_task 中初始化）
            _register_batch_task(novel_id, novel.get("title", "未命名"), chapter_count)
            # _register_batch_task 会重置字典，需要重新获取 finished（保持已完成状态）
            # 但因为是新任务，finished 应该是未触发状态
            nonlocal finished
            finished = _get_batch_finished(novel_id)

            for i in range(chapter_count):
                # 检查中止
                if batch_abort.is_set():
                    _broadcast_batch_event(novel_id, {"type": "batch_aborted", "completed": i})
                    _unregister_batch_task(novel_id, "aborted")
                    break

                # 本轮要生成的章节号（无论上轮成功失败，都递增）
                ch_num = base_number + i

                # 更新任务状态
                _update_batch_task(
                    novel_id,
                    current_chapter=i + 1,
                    current_chapter_number=ch_num,
                )

                # 发送开始进度
                _broadcast_batch_event(novel_id, {
                    "type": "chapter_start",
                    "number": i + 1,
                    "total": chapter_count,
                    "chapter_number": ch_num,
                })

                chapter_queue: asyncio.Queue = asyncio.Queue()
                chapter_done = asyncio.Event()

                async def ch_stream_callback(msg):
                    if isinstance(msg, str):
                        chapter_queue.put_nowait({"type": "chunk", "data": msg})
                    elif isinstance(msg, dict):
                        chapter_queue.put_nowait(msg)

                async def single_chapter_task(ch_num: int = ch_num, ch_idx: int = i):
                    try:
                        # 确定本章的创作走向：
                        # 1. 优先使用 chapter_suggestions 中对应索引的走向
                        # 2. 否则使用整体 suggestions（仅第一章）
                        # 3. 都没有则为空字符串
                        chapter_suggestion = ""
                        if ch_idx < len(per_chapter_suggestions) and per_chapter_suggestions[ch_idx]:
                            chapter_suggestion = per_chapter_suggestions[ch_idx]
                        elif ch_idx == 0 and suggestions:
                            chapter_suggestion = suggestions

                        chapter = await generate_chapter(
                            novel_id, ch_num, "",
                            stream_callback=ch_stream_callback,
                            human_suggestions=chapter_suggestion,
                        )
                        chapter_queue.put_nowait({"type": "chapter_done", "chapter": chapter})
                    except Exception as e:
                        chapter_queue.put_nowait({"type": "error", "message": f"第{ch_num}章生成失败: {str(e)}"})
                    finally:
                        chapter_done.set()

                single_task = asyncio.create_task(single_chapter_task())
                _background_tasks.add(single_task)
                single_task.add_done_callback(_background_tasks.discard)

                while not chapter_done.is_set() or not chapter_queue.empty():
                    try:
                        msg = await asyncio.wait_for(chapter_queue.get(), timeout=2.0)
                        # 转发所有事件，chapter_done 转为标准格式
                        if msg.get("type") == "chapter_done":
                            _broadcast_batch_event(novel_id, {
                                "type": "chapter_done",
                                "chapter": msg["chapter"],
                                "number": i + 1,
                                "total": chapter_count,
                            })
                            # 章节完成，更新进度计数
                            _update_batch_task(novel_id, completed=i + 1)
                        else:
                            _broadcast_batch_event(novel_id, msg)
                    except asyncio.TimeoutError:
                        await asyncio.sleep(0.1)

            _broadcast_batch_event(novel_id, {"type": "batch_complete"})
            _unregister_batch_task(novel_id, "completed")
        except Exception as e:
            _broadcast_batch_event(novel_id, {"type": "error", "message": str(e)})
            _unregister_batch_task(novel_id, "failed")
        finally:
            if prev_provider is not None:
                set_active_provider(prev_provider)
            finished.set()
            # 清理 subscribers 引用（保留空列表，让恢复接口知道任务已结束）
            if novel_id in _active_batch_tasks:
                _active_batch_tasks[novel_id]["subscribers"] = []

    task = asyncio.create_task(batch_task())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    async def event_stream():
        # 每个连接创建自己的 queue，注册为订阅者
        my_queue: asyncio.Queue = asyncio.Queue()
        subs = _get_batch_subscribers(novel_id)
        if subs is not None:
            subs.append(my_queue)
        try:
            while not finished.is_set() or not my_queue.empty():
                try:
                    msg = await asyncio.wait_for(my_queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    # SSE 心跳，防止代理超时断开
                    yield ": heartbeat\n\n"
            yield "data: [DONE]\n\n"
        finally:
            # 连接断开时移除自己的 queue
            subs = _get_batch_subscribers(novel_id)
            if subs is not None:
                try:
                    subs.remove(my_queue)
                except ValueError:
                    pass

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/novels/{novel_id}/batch-stream", dependencies=[Depends(get_current_token)])
async def api_batch_stream_resume(novel_id: str):
    """恢复批量创作的 SSE 流（用户离开创作页面后返回时调用）

    从当前进度开始接收后续事件，不会重放历史事件。
    如果任务已结束或不存在，返回 404。
    """
    if novel_id not in _active_batch_tasks:
        raise HTTPException(404, "没有找到该小说的批量任务")

    t = _active_batch_tasks[novel_id]

    # 任务已结束，返回最终状态（不是 404，让前端能区分）
    if t.get("status") != "running":
        return JSONResponse({
            "ok": False,
            "status": t.get("status", "unknown"),
            "completed": t.get("completed", 0),
            "total": t.get("total", 0),
            "message": "任务已结束",
        })

    # 获取 finished 事件（不存在则创建）
    finished = _get_batch_finished(novel_id)
    if finished is None:
        raise HTTPException(404, "任务状态异常")

    # 如果任务已完成（finished 已触发但 status 还没更新）
    if finished.is_set():
        return JSONResponse({
            "ok": False,
            "status": t.get("status", "completed"),
            "completed": t.get("completed", 0),
            "total": t.get("total", 0),
            "message": "任务已结束",
        })

    # 获取订阅者列表（不存在则创建）
    subscribers = _get_batch_subscribers(novel_id)

    # 创建新的订阅者 queue
    my_queue: asyncio.Queue = asyncio.Queue()
    subscribers.append(my_queue)

    async def event_stream():
        try:
            # 1. 先发送恢复信号 + 当前进度快照
            snapshot = {
                "type": "batch_resume",
                "completed": t.get("completed", 0),
                "total": t.get("total", 0),
                "current_chapter": t.get("current_chapter", 0),
                "current_chapter_number": t.get("current_chapter_number", 0),
                "status": t.get("status", "running"),
                "novel_title": t.get("novel_title", ""),
                "history_count": len(_get_batch_history(novel_id)),
            }
            yield f"data: {json.dumps(snapshot, ensure_ascii=False)}\n\n"

            # 2. 重放历史事件（用户离开页面期间错过的事件）
            # 标记一个 history_replay 开始事件，让前端知道接下来的事件是重放的
            yield f"data: {json.dumps({'type': 'history_replay_start'}, ensure_ascii=False)}\n\n"
            history = _get_batch_history(novel_id)
            for evt in history:
                try:
                    yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
                except (TypeError, ValueError):
                    pass  # 跳过不可序列化的事件
            yield f"data: {json.dumps({'type': 'history_replay_end'}, ensure_ascii=False)}\n\n"

            # 3. 继续转发实时新事件
            while not finished.is_set() or not my_queue.empty():
                try:
                    msg = await asyncio.wait_for(my_queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
            yield "data: [DONE]\n\n"
        finally:
            try:
                subscribers.remove(my_queue)
            except ValueError:
                pass

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/novels/{novel_id}/batch-abort", dependencies=[Depends(get_current_token)])
def api_batch_abort(novel_id: str):
    """中止批量生成"""
    # 简单实现：通过全局标志
    _batch_abort_flags.setdefault(novel_id, asyncio.Event()).set()
    return {"ok": True}


@app.get("/api/active-batch-tasks", dependencies=[Depends(get_current_token)])
def api_get_active_batch_tasks():
    """获取所有正在进行的批量创作任务"""
    _cleanup_stale_tasks()
    # 返回所有 running 状态的任务，以及最近完成的任务（5 分钟内）
    now = time.monotonic()
    tasks = []
    for nid, t in _active_batch_tasks.items():
        # 运行中的任务，或最近 5 分钟内完成的任务
        if t.get("status") == "running" or now - t.get("last_update", 0) < 300:
            # 只返回可 JSON 序列化的字段
            # 排除 subscribers（asyncio.Queue 列表）和 finished（asyncio.Event），它们不可序列化
            safe = {k: v for k, v in t.items() if k not in ("subscribers", "finished")}
            tasks.append(safe)
    # 按开始时间倒序
    tasks.sort(key=lambda x: x.get("started_at", 0), reverse=True)
    return {"tasks": tasks, "count": len(tasks)}


# ==================== 重新生成最新章节 API ====================

@app.post("/api/chapters/{chapter_id}/regenerate", dependencies=[Depends(get_current_token)])
async def api_regenerate_chapter(
    chapter_id: str,
    provider_id: str = Form(""),
    suggestions: str = Form(""),
):
    """重新生成最新章节（仅允许最新章节）"""
    chapter = get_chapter(chapter_id)
    if not chapter:
        raise HTTPException(404, "章节不存在")

    novel_id = chapter["novel_id"]
    chapters = get_chapters(novel_id)

    if not chapters:
        raise HTTPException(400, "没有章节")

    # 验证是否是最新章节
    latest_chapter = chapters[-1]
    if latest_chapter["id"] != chapter_id:
        raise HTTPException(400, "只能重新生成最新章节")

    # 保存旧章节内容，失败时恢复
    old_content = chapter["content"]
    old_title = chapter["title"]
    
    # 先删除旧章节（生成成功后不可恢复，但失败时会恢复）
    delete_chapter(chapter_id)

    # 如果指定了 provider_id，临时切换供应商
    prev_provider = None
    if provider_id:
        from services.provider_service import get_provider as get_prov
        provider = get_prov(provider_id)
        if provider:
            from services.llm_service import _active_provider
            prev_provider = _active_provider
            set_active_provider(provider)

    # 重新生成章节，章节号不变
    chapter_number = chapter["number"]

    # 流式返回（使用 asyncio.Queue 避免阻塞事件循环）
    stream_queue: asyncio.Queue = asyncio.Queue()
    finished = asyncio.Event()

    async def regenerate_task():
        try:
            async def stream_callback(msg):
                if isinstance(msg, str):
                    stream_queue.put_nowait({"type": "chunk", "data": msg})
                elif isinstance(msg, dict):
                    stream_queue.put_nowait(msg)
            new_chapter = await generate_chapter(
                novel_id, chapter_number, "",
                stream_callback=stream_callback,
                human_suggestions=suggestions,
            )
            stream_queue.put_nowait({"type": "done", "chapter": new_chapter})
        except Exception as e:
            # 恢复旧章节
            try:
                create_chapter_manual(novel_id, old_title, old_content, chapter_number)
                stream_queue.put_nowait({"type": "error", "message": f"生成失败，已恢复原章节: {str(e)}"})
            except Exception as restore_err:
                stream_queue.put_nowait({"type": "error", "message": f"生成失败且恢复失败: {str(e)} (恢复错误: {restore_err})"})
        finally:
            if prev_provider is not None:
                set_active_provider(prev_provider)
            finished.set()

    # 保存后台任务引用，防止被垃圾回收
    task = asyncio.create_task(regenerate_task())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    async def event_stream():
        while not finished.is_set() or not stream_queue.empty():
            try:
                msg = await asyncio.wait_for(stream_queue.get(), timeout=15.0)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ==================== 世界观百科 API ====================

class WikiEntryCreate(BaseModel):
    category: str
    name: str
    description: str = ""
    metadata: str = ""


class WikiEntryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[str] = None


@app.get("/api/novels/{novel_id}/wiki", dependencies=[Depends(get_current_token)])
def api_get_wiki_entries(novel_id: str, category: str = ""):
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")
    return {
        "entries": get_wiki_entries(novel_id, category),
        "categories": WIKI_CATEGORIES,
    }


@app.post("/api/novels/{novel_id}/wiki", dependencies=[Depends(get_current_token)])
def api_create_wiki_entry(novel_id: str, data: WikiEntryCreate):
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")
    try:
        entry = create_wiki_entry(
            novel_id, data.category, data.name, data.description, data.metadata
        )
        return {"entry": entry}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.put("/api/wiki/{entry_id}", dependencies=[Depends(get_current_token)])
def api_update_wiki_entry(entry_id: str, data: WikiEntryUpdate):
    kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
    entry = update_wiki_entry(entry_id, **kwargs)
    if not entry:
        raise HTTPException(404, "条目不存在")
    return {"entry": entry}


@app.delete("/api/wiki/{entry_id}", dependencies=[Depends(get_current_token)])
def api_delete_wiki_entry(entry_id: str):
    delete_wiki_entry(entry_id)
    return {"ok": True}


@app.post("/api/novels/{novel_id}/wiki/ai-generate", dependencies=[Depends(get_current_token)])
async def api_ai_generate_wiki_entries(novel_id: str, data: dict = Body(default={})):
    """AI 根据大纲和世界观自动生成百科条目（预览，不直接保存）"""
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")
    try:
        custom_prompt = data.get("custom_prompt", "") if data else ""
        result = await ai_generate_wiki_entries(novel_id, custom_prompt)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"生成失败: {str(e)}")


@app.post("/api/novels/{novel_id}/wiki/apply-generated", dependencies=[Depends(get_current_token)])
def api_apply_generated_wiki_entries(novel_id: str, data: dict = Body(...)):
    """应用 AI 生成的百科条目（前端勾选后调用）"""
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")
    entries = data.get("entries", [])
    if not entries:
        raise HTTPException(400, "条目列表不能为空")
    result = apply_generated_wiki_entries(novel_id, entries)
    return result


# ==================== 待确认的设定变更 API ====================

@app.get("/api/novels/{novel_id}/pending-changes", dependencies=[Depends(get_current_token)])
def api_get_pending_changes(novel_id: str, status: str = "pending"):
    """获取待确认的设定变更列表"""
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")
    return {"changes": get_pending_changes(novel_id, status=status)}


@app.post("/api/pending-changes/{change_id}/accept", dependencies=[Depends(get_current_token)])
def api_accept_pending_change(change_id: str):
    """接受设定变更：更新状态并应用修改到对应设定"""
    # 先获取变更详情
    all_novels = list_novels()
    target_change = None
    target_novel_id = None
    for n in all_novels:
        changes = get_pending_changes(n["id"], status="all")
        for c in changes:
            if c["id"] == change_id:
                target_change = c
                target_novel_id = n["id"]
                break
        if target_change:
            break

    if not target_change:
        raise HTTPException(404, "变更记录不存在")

    if target_change["status"] != "pending":
        raise HTTPException(400, f"该变更已处理（当前状态：{target_change['status']}）")

    # 应用变更到对应设定
    tool = target_change["tool_name"]
    new_content = target_change["new_content"]
    try:
        if tool == "update_outline":
            update_novel(target_novel_id, outline=new_content)
        elif tool == "update_world_building":
            update_novel(target_novel_id, world_building=new_content)
        elif tool == "update_character":
            # 找到对应人物并更新
            target_name = target_change["target_name"]
            characters = get_characters(target_novel_id)
            found = None
            for c in characters:
                if c.get("name") == target_name:
                    found = c
                    break
            if not found:
                raise ValueError(f"人物「{target_name}」不存在")
            update_character(found["id"], name=target_name, profile=new_content)
        else:
            raise ValueError(f"未知的变更类型：{tool}")
    except Exception as e:
        raise HTTPException(500, f"应用变更失败：{str(e)}")

    # 更新状态为已接受
    update_pending_change_status(change_id, "accepted")
    return {"ok": True, "message": "变更已接受并应用"}


@app.post("/api/pending-changes/{change_id}/reject", dependencies=[Depends(get_current_token)])
def api_reject_pending_change(change_id: str):
    """拒绝设定变更"""
    update_pending_change_status(change_id, "rejected")
    return {"ok": True, "message": "变更已拒绝"}


@app.delete("/api/pending-changes/{change_id}", dependencies=[Depends(get_current_token)])
def api_delete_pending_change(change_id: str):
    """删除一条变更记录"""
    if not delete_pending_change(change_id):
        raise HTTPException(404, "变更记录不存在")
    return {"ok": True}


# ==================== 联网搜索 API ====================

@app.post("/api/search", dependencies=[Depends(get_current_token)])
async def api_search(data: dict = Body(...)):
    """联网搜索参考资料（通过 LLM 知识检索）"""
    query = data.get("query", "")
    if not query or not query.strip():
        raise HTTPException(400, "搜索内容不能为空")
    result = await web_search_for_reference(query)
    return result


# ==================== AI 配图 API ====================

class ImageConfigUpdate(BaseModel):
    image_api_url: str = ""
    image_api_key: str = ""
    image_api_model: str = ""


@app.get("/api/config/image", dependencies=[Depends(get_current_token)])
def api_get_image_config():
    """获取图片生成 API 配置（key 掩码）"""
    cfg = get_image_settings()
    key = cfg.get("image_api_key", "")
    return {
        "image_api_url": cfg.get("image_api_url", ""),
        "image_api_key": (key[:8] + "***" if key else ""),
        "image_api_model": cfg.get("image_api_model", ""),
    }


@app.put("/api/config/image", dependencies=[Depends(get_current_token)])
def api_update_image_config(data: ImageConfigUpdate):
    """更新图片生成 API 配置"""
    # image_api_key 以 "***" 结尾说明未修改，不覆盖
    api_key = data.image_api_key
    if api_key.endswith("***"):
        api_key = ""  # 空字符串在 update_settings 中表示清空，这里需要特殊处理
        # 取原 key 保留：通过不更新来实现
        existing = get_image_settings().get("image_api_key", "")
        api_key = existing
    update_image_settings(
        image_api_url=data.image_api_url,
        image_api_key=api_key,
        image_api_model=data.image_api_model,
    )
    return {"ok": True, "config": api_get_image_config()}


# ==================== Tavily 网络搜索配置 API ====================

class TavilyConfigUpdate(BaseModel):
    tavily_api_key: str = ""


@app.get("/api/config/tavily", dependencies=[Depends(get_current_token)])
def api_get_tavily_config():
    cfg = get_tavily_config()
    key = cfg.get("tavily_api_key", "")
    return {"tavily_api_key": (key[:4] + "***" + key[-4:]) if len(key) > 8 else ("***" if key else "")}


@app.put("/api/config/tavily", dependencies=[Depends(get_current_token)])
def api_update_tavily_config(data: TavilyConfigUpdate):
    # 如果 key 包含 ***，保留原值
    if "***" in data.tavily_api_key:
        return {"status": "ok"}  # 不更新
    update_tavily_config(data.tavily_api_key)
    return {"status": "ok"}


@app.post("/api/tavily-search", dependencies=[Depends(get_current_token)])
async def api_tavily_search(data: dict = Body(...)):
    query = data.get("query", "")
    if not query:
        raise HTTPException(400, "搜索内容不能为空")
    result = await tavily_search(query)
    return result


# ==================== 服务器配置 ====================

class ServerConfigUpdate(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None

@app.get("/api/config/server", dependencies=[Depends(get_current_token)])
def api_get_server_config():
    """获取服务器绑定配置"""
    return get_server_config()

@app.put("/api/config/server", dependencies=[Depends(get_current_token)])
def api_update_server_config(data: ServerConfigUpdate):
    """更新服务器绑定配置（需重启生效）"""
    try:
        return update_server_config(host=data.host, port=data.port)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/novels/{novel_id}/generate-image", dependencies=[Depends(get_current_token)])
async def api_generate_image(novel_id: str, data: dict = Body(...)):
    """生成角色立绘/场景图/封面

    data: {type: character|scene|cover, name: str, description: str}
    生成封面时会自动下载到本地 static/covers/novel_{novel_id}.png，无需存数据库。
    """
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")

    image_type = data.get("type", "character")
    name = data.get("name", "")
    description = data.get("description", "")
    if not name and image_type != "cover":
        raise HTTPException(400, "名称不能为空")

    result = await generate_image(novel_id, image_type, name, description)
    # 不抛 HTTPException，把 error 通过 200 返回，便于前端优雅降级
    return result


# ==================== 文档导入分析 API ====================

@app.post("/api/novels/{novel_id}/analyze-document", dependencies=[Depends(get_current_token)])
async def api_analyze_document(novel_id: str, data: dict = Body(...)):
    """分析上传的文档，提取风格/角色/世界观等素材"""
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")

    content = data.get("content", "")
    doc_type = data.get("type", "reference")
    if not content or not content.strip():
        raise HTTPException(400, "文档内容不能为空")
    # 限制长度，避免 token 超限
    if len(content) > 50000:
        content = content[:50000]
    result = await analyze_document(novel_id, content, doc_type)
    return result


# ==================== 静态文件 ====================

static_dir = BASE_DIR / "static"
if static_dir.exists():
    # 挂载静态文件，禁用缓存以便开发时实时更新
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import Response

    class NoCacheMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response: Response = await call_next(request)
            if "/static/" in request.url.path:
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
            return response

    app.add_middleware(NoCacheMiddleware)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def serve_index():
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), headers={
            "Cache-Control": "no-cache, no-store, must-revalidate"
        })
    return {"message": "AI Novel Writer API", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    # 从数据库读取绑定配置，环境变量作为后备
    try:
        _server_cfg = get_server_config()
    except Exception:
        _server_cfg = {"host": "127.0.0.1", "port": 8000}
    _dev_mode = _os.environ.get("NOVEL_WRITER_DEV", "1") == "1"
    # 环境变量优先于数据库配置（部署时可用环境变量强制覆盖）
    _host = _os.environ.get("NOVEL_WRITER_HOST", _server_cfg.get("host", "127.0.0.1"))
    _port = int(_os.environ.get("NOVEL_WRITER_PORT", _server_cfg.get("port", 8000)))
    uvicorn.run("main:app", host=_host, port=_port, reload=_dev_mode)


# ==================== Restart Endpoint ====================

@app.post("/api/system/restart", dependencies=[Depends(get_current_token)])
async def api_restart():
    """重启应用进程"""
    import threading
    import time
    from pathlib import Path

    def _do_restart():
        time.sleep(0.5)  # 等待响应发送完成
        # 方案：写入 _reload_trigger.py，内容每次不同（带时间戳）
        # uvicorn --reload 使用 watchfiles 基于内容变化检测，仅改 mtime 无效
        # 必须实际改变 .py 文件内容才能触发重载
        try:
            trigger = Path(__file__).parent / "_reload_trigger.py"
            trigger.write_text(
                f"# reload trigger {time.time()}\n",
                encoding="utf-8",
            )
        except Exception:
            # 写文件失败则退回信号方式
            import os
            import signal
            try:
                os.kill(os.getpid(), signal.SIGTERM)
            except Exception:
                pass

    threading.Thread(target=_do_restart, daemon=True).start()
    return {"ok": True, "message": "正在重启..."}