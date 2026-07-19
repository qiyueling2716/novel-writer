"""
小说管理服务 — 小说的创建、章节生成、修改、剧情重复检测、人物关系、建议
"""
import re
import uuid
import asyncio
import json
import logging
from contextlib import closing
from datetime import datetime
from typing import Optional

import httpx

from config import NOVEL_CONFIG
from models.database import get_db, novel_row_to_dict, chapter_row_to_dict, relationship_row_to_dict, character_row_to_dict, wiki_entry_row_to_dict, pending_change_row_to_dict
from services.llm_service import chat_completion, chat_completion_stream, get_llm_config
from services.vector_service import check_duplicate, pairwise_check, summarize_chapters, is_vector_available
from services.reranker_service import is_reranker_available, rerank

logger = logging.getLogger(__name__)


# ==================== 小说 CRUD ====================

def create_novel(
    title: str = "",
    title_mode: str = "auto",
    outline: str = "",
    world_building: str = "",
    character_profiles: str = "",
    words_per_chapter: int = 3000,
    duplicate_check_interval: int = 3,
    summary_chapters_count: int = 3,
    expected_chapters: int = 0,
) -> dict:
    novel_id = str(uuid.uuid4())
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        conn.execute(
            """INSERT INTO novels (id, title, title_mode, outline, world_building,
               character_profiles, words_per_chapter, duplicate_check_interval,
               summary_chapters_count, expected_chapters)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (novel_id, title, title_mode, outline, world_building,
             character_profiles, words_per_chapter, duplicate_check_interval,
             summary_chapters_count, expected_chapters),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM novels WHERE id = ?", (novel_id,)).fetchone()
    return novel_row_to_dict(row)


def update_novel(novel_id: str, **kwargs) -> Optional[dict]:
    allowed = ["title", "title_mode", "outline", "world_building",
               "character_profiles", "words_per_chapter", "duplicate_check_interval",
               "summary_chapters_count", "style_reference", "expected_chapters", "max_tokens"]
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return get_novel(novel_id)

    updates["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [novel_id]

    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        conn.execute(f"UPDATE novels SET {set_clause} WHERE id = ?", values)
        conn.commit()
        row = conn.execute("SELECT * FROM novels WHERE id = ?", (novel_id,)).fetchone()
    return novel_row_to_dict(row) if row else None


def get_novel(novel_id: str) -> Optional[dict]:
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        row = conn.execute("SELECT * FROM novels WHERE id = ?", (novel_id,)).fetchone()
    return novel_row_to_dict(row) if row else None


def list_novels() -> list[dict]:
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        rows = conn.execute("SELECT * FROM novels ORDER BY updated_at DESC").fetchall()
        novels = []
        for r in rows:
            n = novel_row_to_dict(r)
            # 统计章节数和总字数（使用已存储的 words_count 字段）
            stats = conn.execute(
                "SELECT COUNT(*) as cnt, COALESCE(SUM(words_count), 0) as words FROM chapters WHERE novel_id = ?",
                (n["id"],),
            ).fetchone()
            n["chapter_count"] = stats["cnt"] if stats else 0
            n["total_words"] = stats["words"] if stats else 0
            novels.append(n)
    return novels


def delete_novel(novel_id: str):
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        conn.execute("DELETE FROM novels WHERE id = ?", (novel_id,))
        conn.commit()


# ==================== 章节 CRUD ====================

def get_chapters(novel_id: str) -> list[dict]:
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        rows = conn.execute(
            "SELECT * FROM chapters WHERE novel_id = ? ORDER BY number ASC", (novel_id,)
        ).fetchall()
    return [chapter_row_to_dict(r) for r in rows]


def get_chapter(chapter_id: str) -> Optional[dict]:
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        row = conn.execute("SELECT * FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
    return chapter_row_to_dict(row) if row else None


def update_chapter(chapter_id: str, **kwargs) -> Optional[dict]:
    """动态更新章节字段。
    通过 kwargs 指定需要更新的字段，未传入的字段保持不变；
    传入的值（含空字符串/0）也会被写入，从而支持将字段置空。"""
    allowed = ["title", "content", "status", "words_count", "embedding_json"]
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        # 无可更新字段时直接返回当前章节
        return get_chapter(chapter_id)

    updates["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [chapter_id]

    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        # 先确认章节存在，不存在则不更新并返回 None
        existing = conn.execute("SELECT id FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
        if not existing:
            return None
        conn.execute(f"UPDATE chapters SET {set_clause} WHERE id = ?", values)
        conn.commit()
        row = conn.execute("SELECT * FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
    return chapter_row_to_dict(row) if row else None


def delete_chapter(chapter_id: str):
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        conn.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))
        conn.commit()


# ==================== 人物关系 CRUD ====================

def get_relationships(novel_id: str) -> list[dict]:
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        rows = conn.execute(
            "SELECT * FROM character_relationships WHERE novel_id = ? ORDER BY created_at ASC",
            (novel_id,),
        ).fetchall()
    return [relationship_row_to_dict(r) for r in rows]


def create_relationship(novel_id: str, character_a: str, character_b: str,
                        relation_type: str = "", description: str = "") -> dict:
    rid = str(uuid.uuid4())
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        conn.execute(
            """INSERT INTO character_relationships (id, novel_id, character_a, character_b,
               relation_type, description)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (rid, novel_id, character_a, character_b, relation_type, description),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM character_relationships WHERE id = ?", (rid,)).fetchone()
    return relationship_row_to_dict(row)


def update_relationship(rel_id: str, **kwargs) -> Optional[dict]:
    allowed = ["character_a", "character_b", "relation_type", "description"]
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return None
    updates["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [rel_id]
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        conn.execute(f"UPDATE character_relationships SET {set_clause} WHERE id = ?", values)
        conn.commit()
        row = conn.execute("SELECT * FROM character_relationships WHERE id = ?", (rel_id,)).fetchone()
    return relationship_row_to_dict(row) if row else None


def delete_relationship(rel_id: str):
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        conn.execute("DELETE FROM character_relationships WHERE id = ?", (rel_id,))
        conn.commit()


def parse_characters_from_profile(profile_text: str) -> list[str]:
    """从人物画像文本中解析角色名列表"""
    if not profile_text:
        return []
    names = set()
    # 匹配模式: "角色名"、"名字："、"姓名："、行首的【XXX】
    patterns = [
        r'【(.+?)】',
        r'「(.+?)」',
        r'[（(](.+?)[)）]',
        r'^(.+?)[：:\s]',
        r'(.+?)[：:]',
    ]
    for line in profile_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        for pat in patterns:
            match = re.match(pat, line, re.MULTILINE)
            if match:
                name = match.group(1).strip()
                # 过滤掉太长的、太短的、明显不是名字的
                if 1 < len(name) <= 8 and not re.search(r'[：:，,。.]', name):
                    names.add(name)
                break
    # 如果没匹配到，尝试按行首取前几个字
    if not names:
        for line in profile_text.split('\n'):
            line = line.strip()
            if line and len(line) <= 10:
                names.add(line)
    return list(names)


def sync_relationships_from_profile(novel_id: str) -> list[dict]:
    """从人物画像表同步角色到关系表（仅添加新角色，不删除已有关系）"""
    novel = get_novel(novel_id)
    if not novel:
        return []

    # 优先从分离的人物画像表获取角色名
    characters = get_characters(novel_id)
    if characters:
        char_names = [c["name"] for c in characters]
    else:
        char_names = parse_characters_from_profile(novel.get("character_profiles", ""))

    existing = get_relationships(novel_id)
    existing_names = set()
    for r in existing:
        existing_names.add(r["character_a"])
        existing_names.add(r["character_b"])

    new_names = [n for n in char_names if n not in existing_names]
    if not new_names:
        return existing

    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        for name in new_names:
            rid = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO character_relationships (id, novel_id, character_a, character_b,
                   relation_type, description)
                   VALUES (?, ?, ?, ?, '待定义', '')""",
                (rid, novel_id, name, ""),
            )
        conn.commit()
    return get_relationships(novel_id)


# ==================== 人物画像 CRUD ====================

def get_characters(novel_id: str) -> list[dict]:
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        rows = conn.execute(
            "SELECT * FROM characters WHERE novel_id = ? ORDER BY created_at ASC",
            (novel_id,),
        ).fetchall()
    return [character_row_to_dict(r) for r in rows]


def get_character(char_id: str) -> Optional[dict]:
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        row = conn.execute("SELECT * FROM characters WHERE id = ?", (char_id,)).fetchone()
    return character_row_to_dict(row) if row else None


def create_character(novel_id: str, name: str, profile: str = "") -> dict:
    char_id = str(uuid.uuid4())
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        conn.execute(
            "INSERT INTO characters (id, novel_id, name, profile) VALUES (?, ?, ?, ?)",
            (char_id, novel_id, name, profile),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM characters WHERE id = ?", (char_id,)).fetchone()
    return character_row_to_dict(row)


def update_character(char_id: str, **kwargs) -> Optional[dict]:
    allowed = ["name", "profile"]
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return None
    updates["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [char_id]
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        conn.execute(f"UPDATE characters SET {set_clause} WHERE id = ?", values)
        conn.commit()
        row = conn.execute("SELECT * FROM characters WHERE id = ?", (char_id,)).fetchone()
    return character_row_to_dict(row) if row else None


def delete_character(char_id: str):
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        conn.execute("DELETE FROM characters WHERE id = ?", (char_id,))
        conn.commit()


# ==================== 小说章节生成 ====================

def _build_system_prompt(novel: dict, relationships: list[dict] = None,
                        characters: list[dict] = None) -> str:
    """构建生成小说的系统提示词（非智能体模式使用，全量注入设定）。
    characters 作为参数传入，避免在函数内部重复查询数据库。"""
    parts = [f"""你是一位资深小说家，正在创作一部长篇连载作品。你拥有以下完整设定档案，请将其内化为创作时的隐性约束，自然地体现在行文中，而非机械照搬或大段复述。"""]

    if novel.get("world_building"):
        parts.append(f"# 世界观设定\n{novel['world_building']}\n")

    # 优先使用外部传入的人物画像（避免函数内部查询数据库）
    chars = characters if characters is not None else get_characters(novel["id"])
    if chars:
        char_lines = []
        for c in chars:
            profile = c["profile"] or novel.get("character_profiles", "")
            if profile:
                char_lines.append(f"## {c['name']}\n{profile}")
        if char_lines:
            parts.append("# 人物档案\n" + "\n\n".join(char_lines) + "\n")
    elif novel.get("character_profiles"):
        parts.append(f"# 人物档案\n{novel['character_profiles']}\n")

    # 人物关系
    rels = relationships or []
    if rels:
        rel_lines = []
        for r in rels:
            if r.get("character_a") and r.get("character_b") and r.get("relation_type") and r["relation_type"] != "待定义":
                rel_lines.append(f"- {r['character_a']} 与 {r['character_b']}：{r['relation_type']}" +
                                 (f"——{r['description']}" if r.get("description") else ""))
        if rel_lines:
            parts.append("# 人物关系\n" + "\n".join(rel_lines) + "\n")

    if novel.get("style_reference"):
        parts.append(f"# 文风要求\n{novel['style_reference']}\n")

    parts.append("""# 创作准则

## 叙事原则
- 大纲是路线图不是剧本，可以丰富细节但不要偏离主方向
- 人物的每个选择都要有动机支撑，读者应该能理解"为什么这么做"
- 展示而非陈述（Show, don't tell）：用行动和对话展现情感，而非直接描述心理活动
- 对话承载信息或推动关系，删掉一切"是的""好的""明白了"之类的废话
- 场景描写要有具体的感官焦点（声音、气味、温度、触感），不要泛泛而写
- 每章结尾用剧情本身制造悬念（一个未解的谜、一个突发的转折、一个意味深长的画面），让读者期待下一章。悬念必须通过故事内容体现，绝不要在结尾添加"（未完待续）""（待续）""To be continued"之类的元标注——每章都是完整的叙事单元，写到自然停顿点即可收尾

## 一致性要求
- 永远不要在正文里解释设定，让角色通过行动和对话自然展现世界观
- 人物性格要前后一致，变化必须有触发事件和合理过渡
- 时间线要连贯，注意季节、昼夜、角色年龄等细节
- 已出场角色的名字、外貌特征、口头禅等要保持一致

## 节奏控制
- 紧张场景用短句，铺陈场景可以放缓
- 不要每章都是高潮，要有张弛有度
- 伏笔要在3-5章内有回收或推进，不要挖了不填

## 结尾要求
- 每章写到剧情的自然停顿点就结束
- 严禁添加"（未完待续）""（待续）""未完""To be continued""..."等任何暗示章节未完成的标注""")
    return "\n".join(parts)


def _build_chapter_prompt(novel: dict, chapter_number: int, previous_summaries: str,
                          duplicate_warnings: str = "",
                          human_suggestions: str = "") -> str:
    """构建单章生成提示词"""
    words = novel.get("words_per_chapter", 3000)
    outline = novel.get("outline", "")

    # 根据章节位置动态调整叙事节奏
    total_chapters = len(outline.split('\n')) if outline else 10
    position_ratio = chapter_number / max(total_chapters, 1)
    if position_ratio <= 0.33:
        pace = "铺垫阶段：建立场景、引入人物、埋设伏笔，节奏可稍缓，但要保持信息密度"
    elif position_ratio <= 0.66:
        pace = "推进阶段：矛盾升级、冲突爆发、关系变化，节奏加快，每章都要有实质进展"
    else:
        pace = "高潮收束：主线推进至关键转折，情节密集，张力拉满，回收之前的伏笔"

    prompt = f"""## 创作任务
创作第 {chapter_number} 章正文。

## 大纲参考
{outline if outline else "（无大纲，请根据前情自然发展）"}

## 前情提要
{previous_summaries if previous_summaries else "（这是第一章，直接开始）"}

## 本章要求
- 目标字数：约 {words} 字（不低于 {int(words * 0.8)} 字，不超过 {int(words * 1.3)} 字）
- 当前节奏定位：{pace}
- 承接上一章结尾的场景或情绪，不要突兀跳转
- 本章至少推进一个情节线索（主线进展/角色关系变化/伏笔揭示/新信息引入）"""

    if human_suggestions:
        prompt += f"\n\n## 用户指定要求\n{human_suggestions}\n（以上为用户对本章的具体要求，请在创作中予以体现）"

    if duplicate_warnings:
        prompt += f"\n\n## 重复预警\n以下情节已经写过，本章必须避开：\n{duplicate_warnings}"

    # 大纲约束：提取当前章节对应的大纲行，强化遵循
    if outline:
        outline_lines = outline.split('\n')
        current_outline_hint = ""
        for line in outline_lines:
            if f"第{chapter_number}章" in line:
                current_outline_hint = line.strip()
                break
        if current_outline_hint:
            prompt += f"\n\n## 大纲指定内容\n{current_outline_hint}\n（本章必须遵循此大纲规划，不得偏离）"
        else:
            prompt += f"\n\n## 大纲约束\n请参考完整大纲，确保本章内容与整体剧情走向一致。大纲：\n{outline[:500]}..."

    # 预期章节限制
    expected = novel.get("expected_chapters", 0)
    if expected > 0:
        is_extras = chapter_number > expected
        if is_extras:
            prompt += f"\n\n## 番外模式\n本章为番外篇（第{chapter_number}章，超出预期{expected}章）。番外可以：\n- 从配角视角讲述主线之外的故事\n- 补充正篇中未展开的情节\n- 讲述时间线之外的小故事\n- 与主线有关联但独立成篇"
        else:
            remaining = expected - chapter_number
            prompt += f"\n\n## 进度提醒\n本章为第{chapter_number}/{expected}章，剩余 {remaining} 章。请注意节奏控制，确保在剩余章节内完成主线收束。"

    prompt += "\n\n## 输出要求\n直接输出正文，不要标题、不要注释、不要前摇、不要分章标记。"
    return prompt


# ==================== Function Calling 工具定义 ====================

def _build_tools(novel: dict, existing_chapters: list[dict], 
                 characters: list[dict]) -> list[dict]:
    """构建供 LLM 使用的工具列表 — LLM 可调用选定小说的所有内容"""
    tools = [
        # ==================== 设定查询工具 ====================
        {
            "type": "function",
            "function": {
                "name": "get_world_building",
                "description": "获取本小说的完整世界观设定。包含世界规则、地理环境、社会结构、历史背景等。当你需要确认故事背景细节或检查设定一致性时调用。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_outline",
                "description": "获取本小说的完整大纲。包含整体剧情走向、各章节规划。当你需要确认当前章节在故事线中的位置、规划后续发展时调用。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_style_reference",
                "description": "获取本小说的文风参考。包含叙事风格、语言特点、描写偏好、节奏要求等。当你需要校准行文风格时调用。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        # ==================== 人物工具 ====================
        {
            "type": "function",
            "function": {
                "name": "list_characters",
                "description": "列出本小说所有人物的名字和简要标签。先调用此工具了解有哪些人物，再按需查看具体档案。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_character",
                "description": "获取指定人物的详细档案（性格、背景、外貌、动机、能力等）。先调用 list_characters 查看有哪些人物。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "人物名称（须与 list_characters 返回的名称完全一致）",
                        },
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_character_relationships",
                "description": "获取所有人物之间的关系图谱。当你需要了解人物间的互动关系、阵营归属、恩怨情仇时调用。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        # ==================== 世界观百科工具 ====================
        {
            "type": "function",
            "function": {
                "name": "list_wiki_entries",
                "description": "列出本小说的世界观百科条目（地点、势力阵营、物品道具、事件时间线）。当你需要了解故事中出现的地名、组织、重要物品或历史事件时调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": ["location", "faction", "item", "event"],
                            "description": "条目类别。location=地点，faction=势力阵营，item=物品道具，event=事件时间线。不传则返回全部类别。",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_wiki_entry",
                "description": "获取指定百科条目的详细信息。先调用 list_wiki_entries 查看有哪些条目。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "条目名称",
                        },
                    },
                    "required": ["name"],
                },
            },
        },
        # ==================== 章节工具 ====================
        {
            "type": "function",
            "function": {
                "name": "list_chapters",
                "description": "获取已有章节的列表概览（章节号、标题、字数）。当你需要了解已写章节的整体情况、确认进度时调用。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_chapter",
                "description": "获取指定章节的完整内容。当你需要回顾之前某一章的具体内容、对话或细节时调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "number": {
                            "type": "integer",
                            "description": "章节序号",
                        },
                    },
                    "required": ["number"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_recent_chapter_summary",
                "description": "获取最近若干章的剧情摘要（比直接读全文更节省 token）。当你需要快速了解近期剧情发展时调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "count": {
                            "type": "integer",
                            "description": "获取最近几章的摘要，默认3",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_chapters",
                "description": "用关键词搜索之前章节的相关内容（基于向量语义检索）。当你需要查找某个话题、场景、人物或物品在之前章节中的出现情况时调用。比逐章翻阅更高效。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词或自然语言描述",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "返回结果数量，默认3",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
    ]

    # 只有 reranker 可用时才添加精排搜索
    if is_reranker_available():
        tools.append({
            "type": "function",
            "function": {
                "name": "rerank_search",
                "description": "用关键词搜索并对结果进行智能重排序，返回最相关的内容片段。比 search_chapters 更精准，适合需要精确查找特定情节时使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词或描述",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "返回结果数量，默认3",
                        },
                    },
                    "required": ["query"],
                },
            },
        })

    # 只有配置了 Tavily API 时才添加网络搜索工具
    tavily_config = get_tavily_config()
    if tavily_config.get("tavily_api_key"):
        tools.append({
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "在网络搜索实时信息（地名、历史、文化、科学知识等）。当需要确认现实世界的背景知识、地理信息、历史事件或专业术语时调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词",
                        },
                    },
                    "required": ["query"],
                },
            },
        })

    # ==================== 编辑工具（AI 可维护设定） ====================
    # 新增类（add_*）：直接执行，不阻塞生成
    # 修改类（update_*）：暂存为 pending_change，生成完成后由用户确认
    tools.append({
        "type": "function",
        "function": {
            "name": "update_outline",
            "description": "更新小说大纲。当你认为大纲需要调整或补充（如新增剧情线、修正逻辑漏洞）时调用。传入更新后的完整大纲。修改会暂存待用户确认后生效。",
            "parameters": {
                "type": "object",
                "properties": {
                    "outline": {
                        "type": "string",
                        "description": "更新后的大纲全文",
                    },
                    "summary": {
                        "type": "string",
                        "description": "简要说明本次修改的理由（一句话）",
                    },
                },
                "required": ["outline"],
            },
        },
    })
    tools.append({
        "type": "function",
        "function": {
            "name": "update_world_building",
            "description": "更新世界观设定。当你发现世界观需要补充或修正时调用。传入更新后的完整世界观。修改会暂存待用户确认后生效。",
            "parameters": {
                "type": "object",
                "properties": {
                    "world_building": {
                        "type": "string",
                        "description": "更新后的世界观全文",
                    },
                    "summary": {
                        "type": "string",
                        "description": "简要说明本次修改的理由（一句话）",
                    },
                },
                "required": ["world_building"],
            },
        },
    })
    tools.append({
        "type": "function",
        "function": {
            "name": "add_character",
            "description": "添加一个新人物到小说中。当剧情中出现有名字的新角色时调用，以便后续章节保持一致。已存在同名人物时会跳过。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "人物名称",
                    },
                    "profile": {
                        "type": "string",
                        "description": "人物档案（性格、背景、外貌、动机等）",
                    },
                },
                "required": ["name"],
            },
        },
    })
    tools.append({
        "type": "function",
        "function": {
            "name": "update_character",
            "description": "更新已有人物的档案。当人物在剧情中发生重大变化（性格转变、获得新能力、身世揭露）时调用。修改会暂存待用户确认后生效。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "人物名称（须已存在）",
                    },
                    "profile": {
                        "type": "string",
                        "description": "更新后的人物档案全文",
                    },
                    "summary": {
                        "type": "string",
                        "description": "简要说明本次修改的理由（一句话）",
                    },
                },
                "required": ["name", "profile"],
            },
        },
    })
    tools.append({
        "type": "function",
        "function": {
            "name": "add_wiki_entry",
            "description": "添加一个世界观百科条目。当剧情中出现新的重要地点、势力、物品或事件时调用。已存在同名条目时会跳过。",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["location", "faction", "item", "event"],
                        "description": "条目类别：location=地点，faction=势力阵营，item=物品道具，event=事件时间线",
                    },
                    "name": {
                        "type": "string",
                        "description": "条目名称",
                    },
                    "description": {
                        "type": "string",
                        "description": "条目的详细描述",
                    },
                },
                "required": ["category", "name"],
            },
        },
    })

    return tools


async def _execute_tool(tool_name: str, args: dict, novel: dict,
                        existing_chapters: list[dict],
                        characters: list[dict],
                        novel_id: str) -> str:
    """执行 LLM 请求的工具调用，返回结果文本"""
    
    if tool_name == "get_world_building":
        wb = novel.get("world_building", "")
        return wb if wb else "（未设置世界观）"
    
    elif tool_name == "get_outline":
        outline = novel.get("outline", "")
        return outline if outline else "（未设置大纲）"
    
    elif tool_name == "get_style_reference":
        sr = novel.get("style_reference", "")
        return sr if sr else "（未设置文风参考）"
    
    elif tool_name == "list_characters":
        if not characters:
            return "（暂无人物档案）"
        names = [c["name"] for c in characters if c.get("name")]
        return "人物列表：" + "、".join(names)
    
    elif tool_name == "get_character":
        name = args.get("name", "")
        for c in characters:
            if c.get("name") == name:
                profile = c.get("profile", "") or novel.get("character_profiles", "")
                return f"## {name}\n{profile}" if profile else f"## {name}\n（无详细档案）"
        return f"未找到名为「{name}」的人物。请先调用 list_characters 查看可用人物。"
    
    elif tool_name == "get_character_relationships":
        rels = get_relationships(novel_id)
        if not rels:
            return "（暂无人物关系数据）"
        lines = []
        for r in rels:
            if r.get("character_a") and r.get("character_b") and r.get("relation_type"):
                line = f"- {r['character_a']} ↔ {r['character_b']}: {r['relation_type']}"
                if r.get("description"):
                    line += f"（{r['description']}）"
                lines.append(line)
        return "\n".join(lines) if lines else "（暂无有效人物关系）"
    
    elif tool_name == "list_wiki_entries":
        category = args.get("category", "")
        entries = get_wiki_entries(novel_id, category) if category else get_wiki_entries(novel_id)
        if not entries:
            return "（暂无百科条目）"
        cat_names = {"location": "地点", "faction": "势力阵营", "item": "物品道具", "event": "事件时间线"}
        lines = []
        for e in entries:
            cat_label = cat_names.get(e.get("category", ""), e.get("category", ""))
            desc_preview = (e.get("description", "") or "")[:80]
            lines.append(f"[{cat_label}] {e['name']}：{desc_preview}")
        return f"共 {len(entries)} 个条目：\n" + "\n".join(lines)
    
    elif tool_name == "get_wiki_entry":
        name = args.get("name", "")
        entries = get_wiki_entries(novel_id)
        for e in entries:
            if e.get("name") == name:
                cat_names = {"location": "地点", "faction": "势力阵营", "item": "物品道具", "event": "事件时间线"}
                cat_label = cat_names.get(e.get("category", ""), e.get("category", ""))
                desc = e.get("description", "") or "（无描述）"
                result = f"## [{cat_label}] {name}\n{desc}"
                if e.get("metadata"):
                    try:
                        meta = json.loads(e["metadata"])
                        if meta:
                            result += "\n\n### 附加属性\n"
                            for k, v in meta.items():
                                result += f"- {k}: {v}\n"
                    except json.JSONDecodeError:
                        pass
                return result
        return f"未找到名为「{name}」的百科条目。请先调用 list_wiki_entries 查看可用条目。"
    
    elif tool_name == "list_chapters":
        if not existing_chapters:
            return "（暂无章节）"
        lines = []
        for ch in existing_chapters:
            wc = ch.get("words_count", 0)
            lines.append(f"第{ch['number']}章《{ch['title']}》 ({wc}字)")
        return f"共 {len(existing_chapters)} 章：\n" + "\n".join(lines)
    
    elif tool_name == "get_recent_chapter_summary":
        count = args.get("count", 3)
        count = max(1, min(count, 10))
        if not existing_chapters:
            return "（暂无章节）"
        recent = existing_chapters[-count:]
        # 生成简要摘要：取每章前200字
        lines = []
        for ch in recent:
            content = ch.get("content", "")
            preview = content[:200].replace("\n", " ")
            lines.append(f"第{ch['number']}章《{ch['title']}》：{preview}...")
        return "\n".join(lines)
    
    elif tool_name == "get_chapter":
        number = args.get("number", 0)
        for ch in existing_chapters:
            if ch.get("number") == number:
                content = ch.get("content", "")
                # 限制返回长度，避免 messages 膨胀导致 token 耗尽
                if len(content) > 2000:
                    content = content[:2000] + "\n\n（本章共{}字，仅返回前2000字以节省 token。如需完整内容请分段查阅。）".format(len(content))
                return f"第{number}章《{ch['title']}》\n\n{content}"
        return f"未找到第{number}章。当前共有{len(existing_chapters)}章。"
    
    elif tool_name == "search_chapters":
        if not existing_chapters:
            return "（暂无章节可搜索）"
        query = args.get("query", "")
        top_k = args.get("top_k", 3)
        if not is_vector_available():
            # 降级：简单关键词匹配
            results = []
            for ch in existing_chapters:
                if query in ch.get("content", ""):
                    idx = ch["content"].index(query)
                    snippet = ch["content"][max(0, idx-100):idx+200]
                    results.append(f"第{ch['number']}章《{ch['title']}》：...{snippet}...")
                    if len(results) >= top_k:
                        break
            return "\n---\n".join(results) if results else f"未找到包含「{query}」的内容"
        
        try:
            from services.vector_service import encode_texts, cosine_similarity
            import numpy as np
            # 编码查询和章节
            chapter_texts = [ch["content"][:1000] for ch in existing_chapters]
            all_texts = [query] + chapter_texts
            embeddings = await encode_texts(all_texts)
            if embeddings is None:
                return f"向量检索不可用，无法搜索「{query}」"
            query_emb = embeddings[0:1]
            chapter_embs = embeddings[1:]
            sims = cosine_similarity(query_emb.flatten(), chapter_embs).flatten() if hasattr(cosine_similarity(query_emb.flatten(), chapter_embs), 'flatten') else [cosine_similarity(query_emb.flatten(), emb.reshape(1,-1)) for emb in chapter_embs]
            # 排序取 top_k
            ranked = sorted(enumerate(sims), key=lambda x: x[1], reverse=True)[:top_k]
            results = []
            for idx, sim in ranked:
                ch = existing_chapters[idx]
                content = ch["content"]
                # 截取最相关的片段
                snippet = content[:500]
                results.append(f"第{ch['number']}章《{ch['title']}》（相似度{sim:.2%}）：\n{snippet}")
            return "\n---\n".join(results)
        except Exception as e:
            return f"搜索失败: {e}"
    
    elif tool_name == "rerank_search":
        if not existing_chapters:
            return "（暂无章节可搜索）"
        query = args.get("query", "")
        top_k = args.get("top_k", 3)
        try:
            from services.reranker_service import rerank
            docs = [{"content": ch["content"][:500], "title": ch["title"], "number": ch["number"]} 
                    for ch in existing_chapters]
            reranked = await rerank(query, docs, top_n=top_k)
            results = []
            for d in reranked:
                results.append(f"第{d['number']}章《{d['title']}》（相关度{d.get('relevance_score', 0):.2%}）：\n{d['content']}")
            return "\n---\n".join(results) if results else f"未找到与「{query}」相关的内容"
        except Exception as e:
            return f"重排序搜索失败: {e}"
    
    elif tool_name == "web_search":
        query = args.get("query", "")
        if not query:
            return "搜索内容不能为空"
        result = await tavily_search(query)
        if result.get("error"):
            return result["error"]
        lines = []
        for i, r in enumerate(result.get("results", [])[:5], 1):
            lines.append(f"[{i}] {r['title']}\n{r['content'][:200]}\n来源: {r['url']}")
        return "\n\n".join(lines) if lines else "未找到相关结果"

    # ============ 编辑工具 ============
    # 新增类：直接执行（不会污染已有设定）
    elif tool_name == "add_character":
        name = args.get("name", "")
        if not name:
            return "人物名称不能为空"
        # 检查是否已存在
        for c in characters:
            if c.get("name") == name:
                return f"人物「{name}」已存在，无需重复添加。"
        profile = args.get("profile", "")
        create_character(novel_id, name=name, profile=profile)
        return f"已添加人物「{name}」。"

    elif tool_name == "add_wiki_entry":
        category = args.get("category", "")
        name = args.get("name", "")
        description = args.get("description", "")
        if not category or not name:
            return "类别和名称不能为空"
        if category not in WIKI_CATEGORIES:
            return f"无效类别「{category}」，有效类别：{list(WIKI_CATEGORIES.keys())}"
        # 检查是否已存在
        existing = get_wiki_entries(novel_id, category)
        for e in existing:
            if e.get("name") == name:
                return f"条目「{name}」已存在，无需重复添加。"
        create_wiki_entry(novel_id, category=category, name=name, description=description)
        return f"已添加百科条目 [{WIKI_CATEGORIES[category]}] {name}。"

    # 修改类：暂存为 pending_change，不立即生效，等用户确认
    elif tool_name == "update_outline":
        new_outline = args.get("outline", "")
        if not new_outline:
            return "大纲内容不能为空"
        old_outline = novel.get("outline", "") or ""
        summary = args.get("summary", "AI 在生成章节时提议修改大纲")
        create_pending_change(
            novel_id=novel_id,
            chapter_number=novel.get("_current_chapter_number", 0),
            tool_name="update_outline",
            target_name="大纲",
            old_content=old_outline,
            new_content=new_outline,
            change_summary=summary,
        )
        return "大纲修改请求已暂存，将在章节生成完成后由作者确认是否采纳。"

    elif tool_name == "update_world_building":
        new_wb = args.get("world_building", "")
        if not new_wb:
            return "世界观内容不能为空"
        old_wb = novel.get("world_building", "") or ""
        summary = args.get("summary", "AI 在生成章节时提议修改世界观")
        create_pending_change(
            novel_id=novel_id,
            chapter_number=novel.get("_current_chapter_number", 0),
            tool_name="update_world_building",
            target_name="世界观",
            old_content=old_wb,
            new_content=new_wb,
            change_summary=summary,
        )
        return "世界观修改请求已暂存，将在章节生成完成后由作者确认是否采纳。"

    elif tool_name == "update_character":
        name = args.get("name", "")
        new_profile = args.get("profile", "")
        if not name or not new_profile:
            return "人物名称和档案内容均不能为空"
        # 查找人物
        found = None
        for c in characters:
            if c.get("name") == name:
                found = c
                break
        if not found:
            return f"未找到名为「{name}」的人物。请先调用 list_characters 查看可用人物。"
        old_profile = found.get("profile", "") or ""
        summary = args.get("summary", f"AI 在生成章节时提议修改「{name}」的档案")
        create_pending_change(
            novel_id=novel_id,
            chapter_number=novel.get("_current_chapter_number", 0),
            tool_name="update_character",
            target_name=name,
            old_content=old_profile,
            new_content=new_profile,
            change_summary=summary,
        )
        return f"人物「{name}」的档案修改请求已暂存，将在章节生成完成后由作者确认。"

    return f"未知工具: {tool_name}"


def _build_agentic_system_prompt(novel: dict, chapter_number: int,
                                  existing_chapters: list[dict],
                                  characters: list[dict]) -> str:
    """构建智能体模式的系统提示词（不再全量注入设定，由 LLM 按需通过工具获取）"""
    parts = [f"""你是一位资深小说家，正在创作一部长篇连载作品，现在要写第 {chapter_number} 章。

这部小说的所有设定都存储在工具系统中，你拥有完整的查阅权限。请按需调用工具获取设定，不要凭记忆臆测。

## 查阅工具（设定查询，只读）
- get_world_building — 世界观设定（世界规则、地理、社会结构）
- get_outline — 完整大纲（剧情走向、章节规划）
- get_style_reference — 文风要求（叙事风格、语言特点）

## 人物工具（只读）
- list_characters — 人物列表（先查看有哪些角色）
- get_character(name) — 指定人物的详细档案（性格、背景、动机、能力）
- get_character_relationships — 人物关系图谱（互动关系、阵营、恩怨）

## 世界观百科工具（只读）
- list_wiki_entries(category?) — 百科条目列表（地点/势力/物品/事件），可按类别筛选
- get_wiki_entry(name) — 指定百科条目的详细信息

## 章节工具（只读）
- list_chapters — 已有章节列表概览（章节号、标题、字数）
- get_chapter(number) — 回看指定章节的完整内容
- get_recent_chapter_summary(count?) — 最近若干章的剧情摘要（节省 token，推荐先用这个）
- search_chapters(query) — 语义检索已写章节（查找特定话题/场景/人物的出现情况）
- rerank_search(query) — 精排搜索（比 search_chapters 更精准，适合精确查找）

## 编辑工具（可维护设定）
- add_character — 添加新人物（同名会自动跳过，直接生效）
- add_wiki_entry — 添加新百科条目（同名会自动跳过，直接生效）
- update_outline — 修改大纲（暂存待作者确认后生效）
- update_world_building — 修改世界观（暂存待作者确认后生效）
- update_character — 修改人物档案（暂存待作者确认后生效）

## 工具使用策略
1. 动笔前先想清楚：这章需要哪些设定？涉及哪些人物？需要回顾哪些前情？
2. 优先用 get_recent_chapter_summary 快速了解近期剧情，再按需深入查看具体章节
3. 涉及特定人物时务必调用 get_character 确认其性格、动机和能力
4. 如果不确定某个地名/物品/事件的设定，用 list_wiki_entries 查阅
5. 获取到关键设定后即可开始创作

## 工具调用说明
- 可按需多次调用查阅工具，确保对设定有完整理解后再动笔
- 剧情中出现新角色、新地点时，用 add_character / add_wiki_entry 记录（直接生效）
- 当剧情发展导致人物性格转变、身世揭露等重大变化时，用 update_character 提议修改（作者会确认）
- 发现大纲需要调整或世界观需要补充时，用 update_outline / update_world_building 提议修改（作者会确认）
- 查阅完成后，综合所有信息直接输出完整的小说正文，不要输出任何说明文字"""]

    if characters:
        names = "、".join(c["name"] for c in characters if c.get("name"))
        parts.append(f"本小说已有 {len(characters)} 个人物：{names}")
    if existing_chapters:
        parts.append(f"已完成 {len(existing_chapters)} 章（第1章到第{existing_chapters[-1]['number']}章）。")

    # 大纲约束：强调必须遵循大纲
    outline = novel.get("outline", "")
    if outline:
        # 提取当前章节对应的大纲行
        current_outline_hint = ""
        for line in outline.split('\n'):
            if f"第{chapter_number}章" in line:
                current_outline_hint = line.strip()
                break
        if current_outline_hint:
            parts.append(f"## 大纲指定内容\n{current_outline_hint}\n（本章必须遵循此大纲规划，不得偏离。如需查阅完整大纲可调用 get_outline。）")
        else:
            parts.append("## 大纲约束\n本章必须与整体大纲的剧情走向保持一致。动笔前请调用 get_outline 查阅完整大纲，确保本章不偏离主线。")

    # 预期章节限制
    expected = novel.get("expected_chapters", 0)
    if expected > 0:
        is_extras = chapter_number > expected
        if is_extras:
            parts.append(f"## 番外模式\n本章为番外篇（第{chapter_number}章，超出预期{expected}章）。番外可以：\n- 从配角视角讲述主线之外的故事\n- 补充正篇中未展开的情节\n- 讲述时间线之外的小故事\n- 与主线有关联但独立成篇")
        else:
            remaining = expected - chapter_number
            parts.append(f"## 进度提醒\n本章为第{chapter_number}/{expected}章，剩余 {remaining} 章。请注意节奏控制，确保在剩余章节内完成主线收束。")

    parts.append("""
## 创作准则

### 叙事原则
- 大纲是路线图不是剧本，可以丰富细节但不要偏离主方向
- 人物的每个选择都要有动机支撑，读者应该能理解"为什么这么做"
- 展示而非陈述（Show, don't tell）：用行动和对话展现情感，而非直接描述心理活动
- 对话承载信息或推动关系，删掉一切"是的""好的""明白了"之类的废话
- 场景描写要有具体的感官焦点（声音、气味、温度、触感），不要泛泛而写
- 每章结尾用剧情本身制造悬念（一个未解的谜、一个突发的转折、一个意味深长的画面），让读者期待下一章。注意：悬念必须通过故事内容体现，绝不要在结尾添加"（未完待续）""（待续）""To be continued"之类的元标注——每章都是完整的叙事单元，写到自然停顿点即可收尾
- 不要在正文中复述设定信息（"修真者分为炼气、筑基……"），让角色通过行动自然展现

### 一致性要求
- 永远不要在正文里解释设定，让角色通过行动和对话自然展现世界观
- 人物性格要前后一致，变化必须有触发事件和合理过渡
- 时间线要连贯，注意季节、昼夜、角色年龄等细节
- 已出场角色的名字、外貌特征、口头禅等要保持一致
- 如果调用了工具查看角色或设定，务必以工具返回的信息为准，不要凭记忆臆测

### 节奏控制
- 紧张场景用短句，铺陈场景可以放缓
- 不要每章都是高潮，要有张弛有度
- 伏笔要在3-5章内有回收或推进，不要挖了不填
- 战斗/冲突场景不要拖沓，3-5个回合内分出胜负或转换
- 情感戏不要直白表白，用细节和动作暗示

### 输出要求
- 最终输出只有正文，不要输出思考过程、章节标题、或任何元信息
- 需要查资料就先调工具，查完再动笔
- 不要在正文中标注"第X章"，系统会自动添加章节标题
- 不要在正文开头或结尾添加"以下是第X章的内容"之类的说明
- 结尾禁止添加"（未完待续）""（待续）""未完""To be continued""..."等任何暗示章节未完成的标注，每章写到剧情的自然停顿点就结束""")

    return "\n".join(parts)


def _build_agentic_user_prompt(novel: dict, chapter_number: int,
                                previous_summaries: str,
                                duplicate_warnings: str = "",
                                human_suggestions: str = "") -> str:
    """构建智能体模式的用户提示词"""
    words = novel.get("words_per_chapter", 3000)
    
    prompt = f"""## 创作任务
创作第 {chapter_number} 章正文。

## 前情提要
{previous_summaries if previous_summaries else "（这是第一章，直接开始）"}

## 本章要求
- 目标字数：约 {words} 字（不低于 {int(words * 0.8)} 字，不超过 {int(words * 1.3)} 字）
- 承接上一章结尾的场景或情绪，不要突兀跳转
- 本章至少推进一个情节线索（主线进展/角色关系变化/伏笔揭示/新信息引入）

## 建议的查阅流程
1. 先用 get_recent_chapter_summary 了解近期剧情
2. 根据本章涉及的人物，用 get_character 查看其档案
3. 如需确认世界观细节，调用 get_world_building 或 list_wiki_entries
4. 查阅完毕后，直接输出正文"""

    if human_suggestions:
        prompt += f"\n\n## 用户指定要求\n{human_suggestions}\n（以上为用户对本章的具体要求，请在创作中予以体现）"

    if duplicate_warnings:
        prompt += f"\n\n## 重复预警\n以下情节已经写过，本章必须避开：\n{duplicate_warnings}"

    # 大纲约束：强调必须遵循大纲
    outline = novel.get("outline", "")
    if outline:
        # 提取当前章节对应的大纲行
        current_outline_hint = ""
        for line in outline.split('\n'):
            if f"第{chapter_number}章" in line:
                current_outline_hint = line.strip()
                break
        if current_outline_hint:
            prompt += f"\n\n## 大纲指定内容\n{current_outline_hint}\n（本章必须遵循此大纲规划，不得偏离。如需查阅完整大纲可调用 get_outline。）"
        else:
            prompt += "\n\n## 大纲约束\n本章必须与整体大纲的剧情走向保持一致。动笔前请调用 get_outline 查阅完整大纲，确保本章不偏离主线。"

    # 预期章节限制
    expected = novel.get("expected_chapters", 0)
    if expected > 0:
        is_extras = chapter_number > expected
        if is_extras:
            prompt += f"\n\n## 番外模式\n本章为番外篇（第{chapter_number}章，超出预期{expected}章）。番外可以：\n- 从配角视角讲述主线之外的故事\n- 补充正篇中未展开的情节\n- 讲述时间线之外的小故事\n- 与主线有关联但独立成篇"
        else:
            remaining = expected - chapter_number
            prompt += f"\n\n## 进度提醒\n本章为第{chapter_number}/{expected}章，剩余 {remaining} 章。请注意节奏控制，确保在剩余章节内完成主线收束。"

    prompt += "\n\n## 输出\n查阅完设定后，直接输出正文。不要标题、不要注释、不要前摇、不要分章标记。"
    return prompt


async def generate_chapter_title(novel: dict, chapter_content: str,
                                 chapter_number: int) -> str:
    # 如果正文无效（太短或全是省略号），直接用默认标题，避免 AI 生成奇怪标题
    import re
    effective = re.sub(r'[\s\.·…。、，,！!？?；;：:""\'\'\"\'\-\—\~～\(\)（）\[\]【】]', '', chapter_content or '')
    if len(effective) < 100:
        return f"第{chapter_number}章"

    prompt = f"""为以下章节内容拟一个标题。

要求：
- 8字以内
- 有画面感或悬念感，不要直白剧透
- 能引发读者好奇
- 只输出标题文字本身，不要加引号、不要加"标题:"前缀、不要输出任何说明

章节内容（前500字）：
{chapter_content[:500]}

标题："""
    try:
        resp = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50,
            temperature=0.7,
        )
        title = resp["choices"][0]["message"]["content"].strip().strip('"').strip("'").strip('"').strip('"')
        # 标题长度保护：超过 30 字符视为 AI 输出了说明性文字，截断到 15 字
        if len(title) > 30:
            # 尝试取第一个换行/句号前的部分
            for sep in ['\n', '。', '；', '，', '.', ',', '!']:
                if sep in title:
                    title = title.split(sep)[0].strip()
                    break
            # 如果仍然太长，硬截断
            if len(title) > 20:
                title = title[:15]
        # 过滤掉明显是说明文字的标题（包含"由于""无法""请""章节"等词）
        if any(w in title for w in ['由于', '无法', '请', '章节内容', '根据', '提示']):
            return f"第{chapter_number}章"
        return title[:30] if title else f"第{chapter_number}章"
    except Exception:
        return f"第{chapter_number}章"


async def generate_chapter(
    novel_id: str,
    chapter_number: int,
    chapter_title: str = "",
    stream_callback=None,
    human_suggestions: str = "",
    max_tokens_override: Optional[int] = None,
) -> dict:
    """生成一章小说内容"""
    novel = get_novel(novel_id)
    if not novel:
        raise ValueError("小说不存在")

    # Token 预算：优先使用调用方传入的 override，其次使用小说设置，最后默认 8192
    chapter_max_tokens = max_tokens_override or novel.get("max_tokens", 0) or 8192

    existing_chapters = get_chapters(novel_id)
    relationships = get_relationships(novel_id)
    # 一次性查询人物画像，传入 _build_system_prompt，避免函数内部重复查询数据库
    characters = get_characters(novel_id)

    # 使用 LLM 总结前文（可配置总结章数）
    summary_count = novel.get("summary_chapters_count", 3)
    previous_summaries = ""
    if existing_chapters and summary_count > 0:
        try:
            previous_summaries = await summarize_chapters(
                existing_chapters, novel, summary_count
            )
        except Exception:
            # 降级：直接拼接前 200 字
            recent = existing_chapters[-summary_count:]
            previous_summaries = "\n".join(
                f"第{ch['number']}章《{ch['title']}》: {ch['content'][:200]}"
                for ch in recent if ch["content"]
            )

    # 剧情重复检测
    duplicate_warnings = ""
    dup_interval = novel.get("duplicate_check_interval", 3)
    if existing_chapters and len(existing_chapters) >= dup_interval and is_vector_available():
        recent_texts = [ch["content"][:500] for ch in existing_chapters[-5:] if ch["content"]]
        if len(recent_texts) >= 2:
            duplicates = await pairwise_check(recent_texts)
            if duplicates:
                warnings = []
                for d in duplicates:
                    warnings.append(
                        f"- 第{d['pair'][0]+1}章与第{d['pair'][1]+1}章相似度 {d['similarity']:.2%}"
                    )
                duplicate_warnings = "检测到以下可能的剧情重复：\n" + "\n".join(warnings)

    system_prompt = _build_system_prompt(novel, relationships, characters)
    user_prompt = _build_chapter_prompt(novel, chapter_number, previous_summaries, duplicate_warnings, human_suggestions)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # 尝试使用 Function Calling 智能体模式（LLM 按需获取设定）
    use_agentic = stream_callback is not None  # 流式模式下优先使用智能体
    if use_agentic:
        try:
            from services.llm_service import agentic_generate
            agentic_messages = [
                {"role": "system", "content": _build_agentic_system_prompt(novel, chapter_number, existing_chapters, characters)},
                {"role": "user", "content": _build_agentic_user_prompt(novel, chapter_number, previous_summaries, duplicate_warnings, human_suggestions)},
            ]
            tools = _build_tools(novel, existing_chapters, characters)
            
            async def tool_executor(tool_name: str, tool_args: dict) -> str:
                # 注入当前章节号，供 pending_change 记录使用
                novel["_current_chapter_number"] = chapter_number
                return await _execute_tool(tool_name, tool_args, novel, existing_chapters, characters, novel_id)
            
            content = await agentic_generate(
                messages=agentic_messages,
                tools=tools,
                tool_executor=tool_executor,
                stream_callback=stream_callback,
                max_rounds=15,
                max_tokens=chapter_max_tokens,  # 推理模型需要更大的 token 预算（reasoning + content）
            )
        except Exception as e:
            # 智能体模式失败（如供应商不支持 function calling），降级到普通模式
            import logging
            logging.warning("智能体模式失败，降级到普通模式: %s", e)
            # 清空前端已累积的内容，避免拼接重复
            if stream_callback:
                await stream_callback({"type": "content_replace", "data": ""})
                collected = []
                async for chunk in chat_completion_stream(messages, max_tokens=chapter_max_tokens):
                    collected.append(chunk)
                    await stream_callback(chunk)
                content = "".join(collected)
            else:
                resp = await chat_completion(messages, max_tokens=chapter_max_tokens)
                content = resp["choices"][0]["message"]["content"]
    elif stream_callback:
        collected = []
        async for chunk in chat_completion_stream(messages, max_tokens=chapter_max_tokens):
            collected.append(chunk)
            await stream_callback(chunk)
        content = "".join(collected)
    else:
        resp = await chat_completion(messages, max_tokens=chapter_max_tokens)
        content = resp["choices"][0]["message"]["content"]

    # 文本清洗：去除多余空行（连续空行合并为单个，去除首尾空白行）
    lines = content.split('\n')
    cleaned_lines = []
    prev_blank = False
    for line in lines:
        if line.strip() == '':
            if not prev_blank and cleaned_lines:  # 跳过连续空行和开头空行
                cleaned_lines.append('')
            prev_blank = True
        else:
            cleaned_lines.append(line.rstrip())  # 去除行尾空白
            prev_blank = False
    # 去除末尾空行
    while cleaned_lines and cleaned_lines[-1] == '':
        cleaned_lines.pop()
    content = '\n'.join(cleaned_lines)

    # 兜底清洗：去除结尾的"未完待续"类元标注（即使提示词已禁止，AI 仍可能输出）
    import re
    # 匹配结尾的各种"未完成"标注（中英文、全半角括号、省略号组合）
    ending_pattern = re.compile(
        r'\s*[\(（]?\s*(?:未完待续|未完|待续|连载中|未完待續|to\s*be\s*continued|TBC)[\)）]?\s*'
        r'(?:[\.。…·]*)?\s*$',
        re.IGNORECASE,
    )
    # 可能需要多次匹配（如 "（未完待续）..." 后面又跟了东西）
    prev_len = -1
    while prev_len != len(content):
        prev_len = len(content)
        # 去除结尾单独一行的省略号或"未完待续"
        content = ending_pattern.sub('', content)
        # 去除末尾单独的省略号行（如 "..." 或 "……" 独占一行）
        content = re.sub(r'\n\s*[\.·…]{2,}\s*$', '', content)
    content = content.rstrip()

    # 无效内容检测：AI 偶尔会输出全是省略号/空白/占位符的内容（字数可能虚高）
    # 去除所有空白和省略号类字符后，检查有效内容长度
    effective_content = re.sub(r'[\s\.·…。、，,！!？?；;：:""\'\'\"\'\-\—\~～\(\)（）\[\]【】]', '', content)
    if len(effective_content) < 50:
        # 内容基本是省略号/标点，视为生成失败
        if use_agentic or stream_callback:
            import logging
            logging.warning("生成内容无效（有效字符仅 %d，疑似全是省略号/占位符），尝试重试", len(effective_content))
            if stream_callback:
                await stream_callback({
                    "type": "thinking",
                    "data": f"（检测到生成内容无效：{len(content)}字但有效字符仅{len(effective_content)}，疑似全是省略号，正在重试...）",
                    "incremental": True,
                })
                await stream_callback({"type": "content_replace", "data": ""})
            # 使用简化的 prompt 重新生成，跳过复杂系统提示
            retry_messages = [
                {"role": "system", "content": "你是一位资深小说家。请直接输出小说正文，不要思考过程，不要输出任何说明。"},
                {"role": "user", "content": user_prompt},
            ]
            retry_content = ""
            retry_max_tokens = max(chapter_max_tokens * 2, 16384)  # 重试给更大预算
            if stream_callback:
                try:
                    async for chunk in chat_completion_stream(retry_messages, max_tokens=retry_max_tokens):
                        retry_content += chunk
                        await stream_callback(chunk)
                except Exception as retry_err:
                    logging.warning("重试也失败: %s", retry_err)
            else:
                try:
                    resp = await chat_completion(retry_messages, max_tokens=retry_max_tokens)
                    retry_content = resp["choices"][0]["message"]["content"]
                except Exception as retry_err:
                    logging.warning("重试也失败: %s", retry_err)
            # 重试内容也要做有效字符检查
            retry_effective = re.sub(r'[\s\.·…。、，,！!？?；;：:""\'\'\"\'\-\—\~～\(\)（）\[\]【】]', '', retry_content)
            if len(retry_effective) >= 50:
                content = retry_content
            else:
                raise ValueError(f"生成内容无效（有效字符仅{len(effective_content)}，重试后仍为{len(retry_effective)}），疑似模型故障。请更换供应商或模型重试。")
        else:
            raise ValueError(f"生成内容无效（有效字符仅{len(effective_content)}），可能模型输出异常。请检查供应商配置或重试。")

    # 空内容保护 + 自动续写重试
    elif len(content.strip()) < 50:
        # 推理模型可能思考后未输出正文，尝试自动续写一次
        if use_agentic or stream_callback:
            import logging
            logging.info("生成内容过短(%d字符)，尝试自动续写", len(content))
            if stream_callback:
                await stream_callback({
                    "type": "thinking",
                    "data": "（正文生成不完整，正在重试...）",
                    "incremental": True,
                })
                await stream_callback({"type": "content_replace", "data": ""})
            # 使用简化的 prompt 重新生成，跳过复杂系统提示
            retry_messages = [
                {"role": "system", "content": "你是一位资深小说家。请直接输出小说正文，不要思考过程，不要输出任何说明。"},
                {"role": "user", "content": user_prompt},
            ]
            retry_content = ""
            retry_max_tokens = max(chapter_max_tokens * 2, 16384)  # 重试给更大预算
            if stream_callback:
                try:
                    async for chunk in chat_completion_stream(retry_messages, max_tokens=retry_max_tokens):
                        retry_content += chunk
                        await stream_callback(chunk)
                except Exception as retry_err:
                    logging.warning("重试也失败: %s", retry_err)
            else:
                try:
                    resp = await chat_completion(retry_messages, max_tokens=retry_max_tokens)
                    retry_content = resp["choices"][0]["message"]["content"]
                except Exception as retry_err:
                    logging.warning("重试也失败: %s", retry_err)
            if len(retry_content.strip()) >= 50:
                content = retry_content
            else:
                raise ValueError(f"生成内容过短（{len(content)}字符），重试后仍失败。请检查供应商配置或尝试更换模型。")
        else:
            raise ValueError(f"生成内容过短（{len(content)}字符），可能生成失败。请检查供应商配置或重试。")

    # 通知前端用清洗后的内容替换流式内容
    if stream_callback:
        await stream_callback({"type": "content_replace", "data": content})

    title = chapter_title
    if not title and novel.get("title_mode", "auto") == "auto":
        title = await generate_chapter_title(novel, content, chapter_number)
    elif not title:
        title = f"第{chapter_number}章"

    words_count = len(content)

    chapter_id = str(uuid.uuid4())
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        # 章节号唯一性检查：如果已存在则自动递增到下一个可用编号
        actual_number = chapter_number
        while conn.execute(
            "SELECT id FROM chapters WHERE novel_id=? AND number=?",
            (novel_id, actual_number),
        ).fetchone():
            actual_number += 1
        if actual_number != chapter_number:
            # 章节号被调整，更新标题中的编号（如果有）
            pass
        conn.execute(
            """INSERT INTO chapters (id, novel_id, number, title, content, status, words_count)
               VALUES (?, ?, ?, ?, ?, 'review', ?)""",
            (chapter_id, novel_id, actual_number, title, content, words_count),
        )
        conn.execute(
            "UPDATE novels SET updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), novel_id),
        )
        conn.commit()

    # 检查本次生成产生的待确认变更，通过 stream 推送给前端
    pending = get_pending_changes(novel_id, status="pending")
    # 只推送本次章节产生的变更（通过 chapter_number 匹配）
    current_pending = [p for p in pending if p.get("chapter_number") == chapter_number]
    if current_pending and stream_callback:
        await stream_callback({
            "type": "pending_changes",
            "data": current_pending,
            "count": len(current_pending),
        })

    return get_chapter(chapter_id)


async def check_novel_duplicates(novel_id: str) -> list[dict]:
    chapters = get_chapters(novel_id)
    texts = [ch["content"][:500] for ch in chapters if ch["content"]]
    if len(texts) < 2:
        return []
    if not is_vector_available():
        return []

    # 使用向量相似度进行初筛
    raw_results = await pairwise_check(texts)
    if not raw_results:
        return []

    # 如果 reranker 可用，使用 reranker 对 pairwise chapters 做精排
    if is_reranker_available() and raw_results:
        try:
            reranked_results = []
            for d in raw_results:
                i, j = d["pair"]
                # 以其中一章为 query，另一章为文档，做精排
                query_text = texts[i]
                doc = {"text": texts[j]}
                ranked = await rerank(query_text, [doc])
                if ranked:
                    reranked_score = ranked[0].get("relevance_score", d["similarity"])
                    reranked_results.append({
                        "pair": (i, j),
                        "similarity": reranked_score,
                        "text_a_preview": texts[i][:80],
                        "text_b_preview": texts[j][:80],
                        "reranked": True,
                    })
            reranked_results.sort(key=lambda x: x["similarity"], reverse=True)
            return reranked_results
        except Exception:
            # reranker 失败，降级到余弦相似度结果
            pass

    return raw_results


# ==================== 建议模块 ====================

async def generate_suggestions(novel_id: str) -> dict:
    """基于当前大纲、世界观、人物、关系、章节，生成写作建议"""
    novel = get_novel(novel_id)
    if not novel:
        raise ValueError("小说不存在")

    chapters = get_chapters(novel_id)
    relationships = get_relationships(novel_id)

    context = []
    if novel.get("outline"):
        context.append(f"【大纲】\n{novel['outline']}")
    if novel.get("world_building"):
        context.append(f"【世界观】\n{novel['world_building']}")
    if novel.get("character_profiles"):
        context.append(f"【人物画像】\n{novel['character_profiles']}")

    if relationships:
        rel_lines = []
        for r in relationships:
            if r.get("character_a") and r.get("relation_type") and r["relation_type"] != "待定义":
                rel_lines.append(f"  {r['character_a']} ↔ {r['character_b']}: {r['relation_type']}" +
                                 (f"（{r['description']}）" if r.get("description") else ""))
        if rel_lines:
            context.append("【人物关系】\n" + "\n".join(rel_lines))

    # 已有章节摘要
    if chapters:
        recent = chapters[-5:]
        ch_summaries = []
        for ch in recent:
            if ch["content"]:
                ch_summaries.append(f"第{ch['number']}章《{ch['title']}》: {ch['content'][:300]}")
        if ch_summaries:
            context.append("【已写章节摘要】\n" + "\n".join(ch_summaries))

    joined_context = '\n'.join(context)
    prompt = f"""你是资深小说编辑，请审阅以下作品并给出写作建议。

# 作品资料
{joined_context}

# 审阅要点
1. 情节节奏：哪里拖沓或仓促？有无断裂的伏笔？下一步走向是否清晰？
2. 人物：主要角色是否立体？弧光是否完整？哪些关系冲突还没被充分利用？
3. 世界观：设定是否被用到了？有无矛盾？和剧情融合度如何？
4. 叙事技巧：视角、悬念、信息释放节奏是否得当？场景与心理描写是否平衡？
5. 语言：风格是否统一？对话是否自然且有角色辨识度？

# 输出
给出 3-5 条具体可执行的建议。每条先指出问题，再给改进方向，不超过 100 字。用编号列表输出。"""

    try:
        resp = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
            temperature=0.7,
        )
        return {
            "suggestions": resp["choices"][0]["message"]["content"].strip(),
            "chapter_count": len(chapters),
            "relationship_count": len(relationships),
        }
    except Exception as e:
        return {"suggestions": f"生成建议失败: {str(e)}", "chapter_count": len(chapters), "relationship_count": len(relationships)}


# ==================== 大纲生成（增强版） ====================

async def generate_outline(novel_id: str, custom_prompt: str = "") -> str:
    """AI生成大纲，注入书名、已有信息、预期章节数"""
    novel = get_novel(novel_id)
    if not novel:
        raise ValueError("小说不存在")

    title = novel.get("title", "")
    expected_chapters = novel.get("expected_chapters", 0)
    world_building = novel.get("world_building", "")
    character_profiles = novel.get("character_profiles", "")
    existing_outline = novel.get("outline", "")

    # 获取已有章节信息
    chapters = get_chapters(novel_id)
    chapter_info = ""
    if chapters:
        chapter_info = f"已写 {len(chapters)} 章"

    # 计算分阶段章节数（用于强约束）
    if expected_chapters > 0:
        if expected_chapters < 10:
            # 小章节量：不强制三幕比例，直接均分
            setup_count = max(1, expected_chapters // 3)
            develop_count = max(1, expected_chapters // 3)
            climax_count = max(1, expected_chapters - setup_count - develop_count)
            # 防止总和超过 expected_chapters
            total_assigned = setup_count + develop_count + climax_count
            if total_assigned > expected_chapters:
                climax_count = max(1, expected_chapters - setup_count - develop_count)
        else:
            setup_count = max(3, int(expected_chapters * 0.3))
            develop_count = max(4, int(expected_chapters * 0.4))
            climax_count = expected_chapters - setup_count - develop_count
    else:
        setup_count = develop_count = climax_count = 0

    prompt_parts = []
    prompt_parts.append(f"你是一位资深小说策划，请为以下小说生成或优化大纲。")
    prompt_parts.append(f"\n## 小说信息")
    prompt_parts.append(f"- 书名：{title}")
    if expected_chapters > 0:
        prompt_parts.append(f"- 预期总章节数：{expected_chapters} 章")
    if chapter_info:
        prompt_parts.append(f"- {chapter_info}")
    if world_building:
        prompt_parts.append(f"\n## 世界观设定\n{world_building[:800]}")
    if character_profiles:
        prompt_parts.append(f"\n## 人物画像\n{character_profiles[:800]}")
    if existing_outline:
        prompt_parts.append(f"\n## 现有大纲\n{existing_outline}")
        prompt_parts.append(f"\n请在此基础上优化和完善大纲。")
    else:
        prompt_parts.append(f"\n请从零开始创作大纲。")

    if expected_chapters > 0:
        prompt_parts.append(f"""
## ⚠️ 章节数量要求（必须严格遵守）
- 大纲必须包含恰好 {expected_chapters} 章，从第1章到第{expected_chapters}章
- 不允许少于 {expected_chapters} 章，也不允许多于 {expected_chapters} 章
- 如果你发现 {expected_chapters} 章无法完整讲述故事，请压缩每章内容密度而非减少章节数
- 输出前请自行数一遍，确保章节数恰好为 {expected_chapters}

## 结构规划（三幕式）
本小说共 {expected_chapters} 章，分为三个阶段：

### 第一幕：铺垫期（第1章 ~ 第{setup_count}章，共{setup_count}章）
- 建立世界观：核心规则、社会结构、关键地点
- 引入主要人物：主角出场、核心配角亮相、主要对手暗示
- 埋设伏笔：至少3个重要伏笔，分布在第1-{setup_count}章中
- 第1章必须有强力的开场钩子（悬念/冲突/意外），抓住读者
- 第{setup_count}章前后发生"激励事件"，主角被迫踏上主线旅程

### 第二幕：推进期（第{setup_count+1}章 ~ 第{setup_count+develop_count}章，共{develop_count}章）
- 矛盾层层升级：每3-5章一个小高潮，推进主线
- 角色关系变化：结盟、背叛、感情发展、能力成长
- 支线交织：支线为主线服务，不喧宾夺主
- 第{setup_count + develop_count // 2}章前后发生"中点转折"，故事方向逆转
- 伏笔回收：第一幕的伏笔在此阶段逐步回收或推进
- 第{setup_count+develop_count}章是"灵魂黑夜"，主角陷入最大困境

### 第三幕：收束期（第{setup_count+develop_count+1}章 ~ 第{expected_chapters}章，共{climax_count}章）
- 主线决战：所有线索汇聚，终极对决
- 伏笔全部回收，不留悬念（除非是系列作）
- 角色弧光完成：主角完成转变
- 第{expected_chapters}章为终章，给出令人满意的结局
- 结局可以是圆满/开放/悲剧，但要与整体基调一致

## 每章格式
每章用一行概括，格式严格为：
第X章：章节标题 - 本章核心事件与冲突

示例：
第1章：陨落之夜 - 主角宗门被灭，独自逃入禁地，意外获得上古传承
第2章：禁地求生 - 主角在禁地中磨练生存技能，发现传承者的秘密
""")
    else:
        prompt_parts.append(f"""
## 结构要求
- 采用三幕式结构：前30%铺垫，中40%推进，后30%收束
- 每章只解决一个问题，同时抛出下一个问题——链式悬念
- 伏笔要在3-5章内有回收或呼应
- 每章用一行概括：第X章：章节标题 - 本章核心事件与冲突
""")

    prompt_parts.append(f"""
## 输出要求
- 直接输出大纲内容，不要前摇，不要输出任何说明文字
- 格式：每行一章，第X章：标题 - 概要
- 大纲要具体到每章的核心事件和冲突，不要泛泛而谈
- 每章概要要体现戏剧张力，不要写成流水账""")

    if custom_prompt:
        prompt_parts.append(f"\n## 用户附加要求\n{custom_prompt}")

    messages = [
        {"role": "system", "content": "你是一位资深小说策划，擅长构建紧凑、有张力的长篇故事结构。你严格遵循用户的章节数量要求。"},
        {"role": "user", "content": "\n".join(prompt_parts)},
    ]

    # 50章大纲每章约30字，至少需要1500字内容，加上格式开销，需要充足token
    max_tokens = max(4000, expected_chapters * 120) if expected_chapters > 0 else 4000
    resp = await chat_completion(messages, stream=False, max_tokens=max_tokens)
    content = resp["choices"][0]["message"]["content"]
    return content.strip()


# ==================== AI 优化 ====================

async def ai_generate_outline(novel_id: str) -> dict:
    """使用 LLM 根据小说信息和已有内容生成大纲"""
    novel = get_novel(novel_id)
    if not novel:
        raise ValueError("小说不存在")

    characters = get_characters(novel_id)
    chapters = get_chapters(novel_id)

    context_parts = []
    if novel.get("world_building"):
        context_parts.append(f"【世界观】\n{novel['world_building'][:800]}")
    if novel.get("synopsis"):
        context_parts.append(f"【简介】\n{novel['synopsis']}")
    if characters:
        char_lines = [f"- {c['name']}：{(c.get('profile') or '')[:200]}" for c in characters]
        context_parts.append("【人物】\n" + "\n".join(char_lines))
    if chapters:
        ch_lines = [f"第{ch['number']}章《{ch['title']}》：{ch['content'][:200]}..." for ch in chapters[-5:]]
        context_parts.append("【已写章节】\n" + "\n".join(ch_lines))

    joined = "\n\n".join(context_parts) if context_parts else "（暂无其他设定，请自由发挥）"
    # 优先使用 expected_chapters，否则回退到 total_chapters
    total = novel.get("expected_chapters", 0) or novel.get("total_chapters", 20)
    if total <= 0:
        total = 20

    # 计算分阶段章节数
    if total < 10:
        setup_count = max(1, total // 3)
        develop_count = max(1, total // 3)
        climax_count = max(1, total - setup_count - develop_count)
        if setup_count + develop_count + climax_count > total:
            climax_count = max(1, total - setup_count - develop_count)
    else:
        setup_count = max(3, int(total * 0.3))
        develop_count = max(4, int(total * 0.4))
        climax_count = total - setup_count - develop_count

    prompt = f"""你是小说剧情策划。为以下作品设计一份完整大纲。

# 作品信息
标题：{novel.get('title', '未命名')}
类型：{novel.get('genre', '未指定')}

# 已有素材
{joined}

# ⚠️ 章节数量要求（必须严格遵守）
- 大纲必须包含恰好 {total} 章，从第1章到第{total}章
- 不允许少于 {total} 章，也不允许多于 {total} 章
- 如果你发现 {total} 章无法完整讲述故事，请压缩每章内容密度而非减少章节数
- 输出前请自行数一遍，确保章节数恰好为 {total}

# 结构规划（三幕式）
共 {total} 章：
- 第一幕 铺垫期（第1~{setup_count}章）：建立世界、引入人物、埋设伏笔、激励事件
- 第二幕 推进期（第{setup_count+1}~{setup_count+develop_count}章）：矛盾升级、关系变化、中点转折、灵魂黑夜
- 第三幕 收束期（第{setup_count+develop_count+1}~{total}章）：主线决战、伏笔回收、角色弧光完成、终章结局

# 设计原则
1. 起承转合：前1/4建立世界和人物，中段推升矛盾冲突，后1/4收束高潮
2. 每章只解决一个问题，同时抛出下一个问题——链式悬念
3. 主线始终清晰，支线为主线服务，不喧宾夺主
4. 重要伏笔要在3-5章内有回收或呼应
5. 已有章节的剧情不要重复，大纲要衔接现有内容继续发展
6. 避免流水账式概括，每章的概括要体现该章的戏剧张力

# 输出格式
严格按以下格式，每章一行：

第1章 章节标题 - 本章核心冲突和剧情推进的一句话概括
第2章 章节标题 - 本章核心冲突和剧情推进的一句话概括

以此类推，必须覆盖全部 {total} 章，不多不少。"""

    try:
        max_tokens = max(4000, total * 120)
        resp = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.7,
        )
        outline = resp["choices"][0]["message"]["content"].strip()
        update_novel(novel_id, outline=outline)
        return {"outline": outline}
    except Exception as e:
        raise ValueError(f"AI 生成大纲失败: {str(e)}")


async def ai_generate_characters(novel_id: str, custom_prompt: str = "") -> dict:
    """AI 根据大纲、世界观、已有章节自动生成人物画像

    返回生成的角色列表（预览），不直接保存，由前端确认后应用。
    """
    novel = get_novel(novel_id)
    if not novel:
        raise ValueError("小说不存在")

    existing = get_characters(novel_id)
    existing_names = [c["name"] for c in existing]

    context = []
    if novel.get("outline"):
        context.append(f"【大纲】\n{novel['outline'][:1200]}")
    if novel.get("world_building"):
        context.append(f"【世界观】\n{novel['world_building'][:800]}")
    if novel.get("style_reference"):
        context.append(f"【文风参考】\n{novel['style_reference'][:400]}")

    chapters = get_chapters(novel_id)
    if chapters:
        ch_text = chapters[-3:]  # 最近3章
        ch_summaries = []
        for ch in ch_text:
            if ch["content"]:
                ch_summaries.append(f"第{ch['number']}章《{ch['title']}》: {ch['content'][:400]}")
        if ch_summaries:
            context.append("【已写章节摘要】\n" + "\n".join(ch_summaries))

    if not any(context):
        raise ValueError("请先填写大纲或世界观设定，AI才能生成人物")

    if existing_names:
        context.append(f"【已有角色（不要重复）】\n{', '.join(existing_names)}")

    joined = '\n\n'.join(context)
    prompt = f"""你是小说人物设计师。根据以下作品信息，设计这部小说需要的核心角色。

# 作品信息
{joined}

# 设计原则
1. 设计 3-6 个核心角色（主角、重要配角、关键反派/对手），不要设计路人
2. 每个角色必须有明确的剧情功能（推动主线、制造冲突、提供助力、设置障碍）
3. 角色之间应自带关系张力（不要都是朋友，要有对立面）
4. 遵循已有大纲和世界观，不创造与设定矛盾的角色
5. 每个角色要有"想要"和"需要"的区分——想要的是表层目标，需要的是深层成长
6. 给每个角色一个致命弱点或内心矛盾，这是角色弧光的驱动力
7. 角色之间至少存在一组对立关系（价值观冲突/利益冲突/情感纠葛）

# 输出格式
严格按以下格式，每个角色一段，用 --- 分隔：

角色名
外貌：标志性特征（1句，要有辨识度）
性格：核心特质+矛盾弱点（1句，性格中要有矛盾点）
背景：出身和关键转折（1句，要有塑造人物的创伤或机遇）
动机：最想要什么+最害怕什么（1句，欲望与恐惧形成张力）
能力：擅长什么+不擅长什么（1句，能力要有明确边界）
---

只输出角色信息，不要输出其他内容。"""

    if custom_prompt:
        prompt += f"\n\n# 用户附加要求\n{custom_prompt}"

    try:
        resp = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
            temperature=0.7,
        )
        result_text = resp["choices"][0]["message"]["content"].strip()

        # 解析角色
        characters = []
        blocks = result_text.split('---')
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            lines = block.split('\n')
            name = lines[0].strip().replace('#', '').replace('角色名：', '').replace('角色名:', '').strip()
            if not name or len(name) > 20:
                # 尝试从第一行提取名字
                for line in lines[1:]:
                    if line.strip() and not line.strip().startswith(('外貌', '性格', '背景', '动机', '能力')):
                        continue
                    break
                if not name:
                    continue
            # 跳过已存在的角色
            if name in existing_names:
                continue
            # 将所有行合并为画像
            profile_lines = [l.strip() for l in lines[1:] if l.strip()]
            profile = '\n'.join(profile_lines)
            if name and profile:
                characters.append({"name": name, "profile": profile})

        return {
            "characters": characters,
            "existing_count": len(existing_names),
        }
    except Exception as e:
        raise ValueError(f"AI 生成失败: {str(e)}")


async def extract_characters_from_chapters(novel_id: str) -> dict:
    """从已写章节中提取角色和关系，返回预览结果"""
    novel = get_novel(novel_id)
    if not novel:
        raise ValueError("小说不存在")

    chapters = get_chapters(novel_id)
    if not chapters:
        raise ValueError("暂无已写章节")

    # 合并章节内容（最多取最近10章的前800字）
    ch_texts = []
    for ch in chapters[-10:]:
        if ch["content"]:
            ch_texts.append(f"第{ch['number']}章《{ch['title']}》:\n{ch['content'][:800]}")

    if not ch_texts:
        raise ValueError("章节内容为空，无法提取")

    existing = get_characters(novel_id)
    existing_names = [c["name"] for c in existing]

    joined = '\n\n'.join(ch_texts)
    prompt = f"""你是小说分析师。从以下已写章节中提取所有出现过的角色和角色之间的关系。

# 章节内容
{joined}

# 已有角色（标注 ★ 表示已存在，避免重复提取）
{', '.join(existing_names) if existing_names else '（暂无）'}

# 提取规则
1. 提取所有有名字且有对话/行动的角色（不包括仅被提及的路人）
2. 为每个角色总结：外貌特征、性格特点、身份背景（基于章节中出现的信息，不要编造）
3. 提取角色之间的明确关系（有互动证据的，不要猜测）
4. 关系类型从以下选择：挚友、恋人、仇敌、师徒、亲人、盟友、暗恋、主仆、竞争、从属、其他
5. 如果角色已存在于已有角色列表中，在名字前加 ★ 标记

# 输出格式
## 角色
角色名 | 外貌特征 | 性格特点 | 身份背景

## 关系
角色A | 角色B | 关系类型 | 关系描述（基于章节中的互动证据）

只输出提取结果，不要输出其他内容。"""

    try:
        resp = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
            temperature=0.3,
        )
        result_text = resp["choices"][0]["message"]["content"].strip()

        # 解析角色
        characters = []
        relationships = []
        in_char_section = False
        in_rel_section = False

        for line in result_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            if line.startswith('## 角色') or line.startswith('##角色'):
                in_char_section = True
                in_rel_section = False
                continue
            elif line.startswith('## 关系') or line.startswith('##关系'):
                in_char_section = False
                in_rel_section = True
                continue

            if '|' not in line:
                continue

            parts = [p.strip() for p in line.split('|')]
            if in_char_section and len(parts) >= 2:
                name = parts[0].replace('★', '').strip()
                if not name:
                    continue
                # 合并剩余部分为画像
                profile_parts = [p for p in parts[1:] if p]
                profile = ' | '.join(profile_parts) if len(profile_parts) > 1 else (profile_parts[0] if profile_parts else '')
                is_existing = '★' in parts[0] or name in existing_names
                characters.append({"name": name, "profile": profile, "is_existing": is_existing})
            elif in_rel_section and len(parts) >= 4:
                relationships.append({
                    "character_a": parts[0].replace('★', '').strip(),
                    "character_b": parts[1].replace('★', '').strip(),
                    "relation_type": parts[2],
                    "description": parts[3],
                })

        return {
            "characters": characters,
            "relationships": relationships,
            "chapter_count": len(chapters),
            "existing_count": len(existing_names),
        }
    except Exception as e:
        raise ValueError(f"提取失败: {str(e)}")


async def ai_optimize_character(novel_id: str, char_id: str) -> dict:
    """使用 LLM 优化单个人物画像"""
    character = get_character(char_id)
    if not character:
        raise ValueError("人物不存在")

    novel = get_novel(novel_id)
    world_building = novel.get("world_building", "") if novel else ""

    context = f"人物名称: {character['name']}\n"
    if character["profile"]:
        context += f"当前画像:\n{character['profile']}\n"
    if world_building:
        context += f"\n世界观背景:\n{world_building[:800]}\n"

    prompt = f"""你是小说人物设计师。为角色「{character['name']}」撰写一份人物档案。

# 已有信息
{context}

# 撰写要求
用以下六个维度构建一个立体的、能驱动剧情的角色。每个维度 2-3 句，语言精炼：

1. 外貌：让人一眼记住的特征（不是全身描写，而是标志性细节——一道疤、一种站姿、一件常穿的衣物）
2. 性格：核心特质 + 一个与之矛盾的弱点（勇敢的人怕什么？冷酷的人对谁心软？）
3. 背景：出身和关键转折，解释他为什么是现在这个人
4. 动机：他最想要什么？最害怕失去什么？这两个答案驱动他的一切行为
5. 能力：擅长什么？不擅长什么？能力的边界在哪里？
6. 人际：他如何对待不同类型的人？什么能让他信任或背叛？

直接输出档案正文，不要加标题或编号。"""

    try:
        resp = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
            temperature=0.7,
        )
        optimized = resp["choices"][0]["message"]["content"].strip()
        update_character(char_id, profile=optimized)
        return get_character(char_id)
    except Exception as e:
        raise ValueError(f"AI 优化失败: {str(e)}")


async def ai_optimize_world_building(novel_id: str, custom_prompt: str = "") -> dict:
    """使用 LLM 优化世界观设定"""
    novel = get_novel(novel_id)
    if not novel:
        raise ValueError("小说不存在")

    current = novel.get("world_building", "")
    outline = novel.get("outline", "")

    prompt = f"""你是小说世界观架构师。为这部小说构建一份世界观设定。

# 当前设定
{current if current else "（从零构建）"}

# 大纲参考
{outline[:800] if outline else "（无）"}

# 写作要求
写一份有机的、像小说设定集般流畅的世界观文档。不要分条罗列、不要用小标题、不要按维度逐段填空——写成自然衔接的叙述，让读者一口气读完就能理解这个世界。

好的世界观应该让以下元素自然融入叙述中（而不是逐条回答）：
- 这个世界的时代背景和核心矛盾（什么力量在撕裂这个世界？）
- 谁掌握权力、谁被压迫、阶层之间的张力在哪里
- 这个社会的信仰、禁忌、风俗如何塑造角色的行为约束
- 核心能力体系（科技/魔法/武力）的规则和代价——没有限制的能力等于没有戏剧性
- 2-3 个关键地点，每个地点自带氛围和潜在冲突
- 1-2 个可作为伏笔的历史谜团

# 禁止事项
- 不要输出"时代背景：""社会结构："这样的维度标签
- 不要分成六个段落各自独立，要写成连贯的整体
- 不要用"1. 2. 3."编号
- 不要在末尾添加总结或说明

直接输出世界观正文。"""

    if custom_prompt:
        prompt += f"\n\n# 用户附加要求\n{custom_prompt}"

    try:
        resp = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=6000,
            temperature=0.7,
        )
        optimized = resp["choices"][0]["message"]["content"].strip()
        update_novel(novel_id, world_building=optimized)
        return {"world_building": optimized}
    except Exception as e:
        raise ValueError(f"AI 优化失败: {str(e)}")


async def ai_refine_relationships(novel_id: str) -> dict:
    """使用 LLM 根据全部上下文（大纲、世界观、人物、章节）细化人物关系"""
    novel = get_novel(novel_id)
    if not novel:
        raise ValueError("小说不存在")

    characters = get_characters(novel_id)
    existing_rels = get_relationships(novel_id)
    chapters = get_chapters(novel_id)

    if not characters:
        raise ValueError("请先添加人物画像")

    context = []
    if novel.get("outline"):
        context.append(f"【大纲】\n{novel['outline'][:600]}")
    if novel.get("world_building"):
        context.append(f"【世界观】\n{novel['world_building'][:600]}")

    char_lines = []
    for c in characters:
        profile = c["profile"] or ""
        char_lines.append(f"- {c['name']}：{profile[:300]}")
    context.append("【人物档案】\n" + "\n".join(char_lines))

    if chapters:
        ch_summaries = []
        for ch in chapters[-5:]:
            if ch["content"]:
                ch_summaries.append(f"第{ch['number']}章：{ch['content'][:300]}")
        if ch_summaries:
            context.append("【已写章节摘要】\n" + "\n".join(ch_summaries))

    joined = '\n\n'.join(context)
    prompt = f"""你是小说人物关系设计师。根据以下作品信息，分析角色之间的关系网。

# 作品信息
{joined}

# 分析原则
1. 每条关系必须包含：角色A、角色B、关系类型、关系描述
2. 关系类型从以下选择：挚友、恋人、仇敌、师徒、亲人、盟友、暗恋、主仆、竞争、从属
3. 关系描述必须体现两点：他们之间的情感态度 + 这段关系潜在的冲突或张力
4. 只为真正有互动或潜在互动的角色配对，不要凑数
5. 优先分析主角的关系网，再扩展到次要角色
6. 如果已有人为设定的关系不合理，可以修正

# 输出格式
严格按以下格式，每行一条，用 | 分隔，不要输出其他内容：

角色A | 角色B | 关系类型 | 情感态度与潜在冲突

## 示例
林动 | 绫清竹 | 暗恋 | 林动倾慕但不敢表白，绫清竹刻意保持距离，身份差距是隐形屏障
林动 | 应欢欢 | 盟友 | 因共同敌人暂时合作，但应欢欢隐藏的目的随时可能撕裂同盟

只输出关系行，不要输出其他内容。"""

    try:
        resp = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
            temperature=0.6,
        )
        result_text = resp["choices"][0]["message"]["content"].strip()
        
        # 解析结果为结构化数据
        relationships = []
        for line in result_text.split('\n'):
            line = line.strip()
            if not line or '|' not in line:
                continue
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 4 and parts[0] and parts[1]:
                relationships.append({
                    "character_a": parts[0],
                    "character_b": parts[1],
                    "relation_type": parts[2],
                    "description": parts[3],
                })
        
        return {
            "suggestions": result_text,
            "relationships": relationships,
            "character_count": len(characters),
            "relationship_count": len(existing_rels),
        }
    except Exception as e:
        raise ValueError(f"AI 分析失败: {str(e)}")


# ==================== 文风分析 ====================

async def analyze_style_from_chapters_stream(novel_id: str, chapter_ids: list[str]):
    """流式版：从章节分析文风，逐块 yield 文本"""
    if len(chapter_ids) > 10:
        raise ValueError("最多选择 10 个章节进行分析")
    chapters = get_chapters(novel_id)
    selected = [ch for ch in chapters if ch["id"] in chapter_ids and ch["content"]]
    if not selected:
        raise ValueError("未找到有效的章节内容")

    samples = []
    for ch in selected:
        text = ch["content"][:800]
        samples.append(f"第{ch['number']}章《{ch['title']}》：\n{text}")

    joined = '\n\n'.join(samples)
    prompt = f"""分析以下小说章节的文风，用 200-400 字写成一段可直接用作创作参考的文风指南。

{joined}

分析维度：
1. 叙事视角（第几人称）和节奏特征（快/慢、详略偏好）
2. 语言风格：华丽或朴素？古典或现代？长句为主还是短句为主？
3. 描写偏好：偏重场景/心理/对话/动作？偏好哪种感官描写？
4. 对话特点：占比多少？口语化程度？是否信息密集？
5. 情感基调和氛围

直接输出文风描述，写成一段连贯的文字，不要分点列出。"""

    full_text = ""
    async for chunk in chat_completion_stream(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=800,
    ):
        full_text += chunk
        yield ("chunk", chunk)

    style = full_text.strip()
    update_novel(novel_id, style_reference=style)
    yield ("done", style)


async def analyze_style_from_text_stream(text: str, novel_id: str = ""):
    """流式版：从上传文本分析文风，逐块 yield 文本"""
    if not text or len(text) < 50:
        raise ValueError("文本内容过短，无法分析文风")

    sample = text[:2000]
    prompt = f"""分析以下文本的文风，用 200-400 字写成一段可直接用作创作参考的文风指南。

文本样本：
{sample}

分析维度：
1. 叙事视角和节奏特征
2. 语言风格：华丽或朴素？古典或现代？句式特征？
3. 描写偏好：偏重哪种类型？感官描写特征？
4. 对话特点：占比、口语化程度、信息密度
5. 情感基调和氛围

直接输出文风描述，写成一段连贯的文字，不要分点列出。"""

    full_text = ""
    async for chunk in chat_completion_stream(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=800,
    ):
        full_text += chunk
        yield ("chunk", chunk)

    style = full_text.strip()
    if novel_id:
        update_novel(novel_id, style_reference=style)
    yield ("done", style)


# ==================== 手动创建章节 ====================

# ==================== 备份迁移 ====================

def export_backup(include_config: bool = False) -> dict:
    """导出全部数据为 JSON
    
    Args:
        include_config: 是否包含配置（providers/vector/reranker/image/tavily）
                        配置中的 api_key 以明文导出（读取时已解密），
                        整个备份可由调用方用用户密码加密
    
    Returns:
        dict 包含：
        - novels, chapters, characters, character_relationships, wiki_entries, pending_changes
        - 若 include_config=True，额外包含 config 字段（providers/vector/reranker/image/tavily）
        - _version: 备份格式版本号
        - _exported_at: 导出时间
    """
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        novels = [novel_row_to_dict(r) for r in conn.execute("SELECT * FROM novels ORDER BY updated_at DESC").fetchall()]
        chapters = [chapter_row_to_dict(r) for r in conn.execute("SELECT * FROM chapters ORDER BY novel_id, number ASC").fetchall()]
        characters = [character_row_to_dict(r) for r in conn.execute("SELECT * FROM characters ORDER BY novel_id, created_at ASC").fetchall()]
        relationships = [relationship_row_to_dict(r) for r in conn.execute("SELECT * FROM character_relationships ORDER BY novel_id, created_at ASC").fetchall()]
        wiki_entries = [wiki_entry_row_to_dict(r) for r in conn.execute("SELECT * FROM wiki_entries ORDER BY category, name ASC").fetchall()]
        pending_changes = [pending_change_row_to_dict(r) for r in conn.execute("SELECT * FROM pending_changes ORDER BY created_at ASC").fetchall()]
    
    result = {
        "_version": 2,
        "_exported_at": datetime.now().isoformat(),
        "novels": novels,
        "chapters": chapters,
        "characters": characters,
        "character_relationships": relationships,
        "wiki_entries": wiki_entries,
        "pending_changes": pending_changes,
    }
    
    # 可选：包含配置（api_key 为明文，因为读取时已解密）
    if include_config:
        config = _export_config()
        result["config"] = config
    
    return result


def _export_config() -> dict:
    """导出所有配置（api_key 为明文，因为读取时已解密）"""
    config = {}
    
    # providers
    try:
        from services.provider_service import list_providers
        config["providers"] = list_providers()
    except Exception:
        config["providers"] = []
    
    # vector config
    try:
        from services.vector_service import _runtime_vector_config
        config["vector_config"] = {**_runtime_vector_config}
    except Exception:
        config["vector_config"] = {}
    
    # reranker config
    try:
        from services.reranker_service import _runtime_reranker_config
        config["reranker_config"] = {**_runtime_reranker_config}
    except Exception:
        config["reranker_config"] = {}
    
    # image settings
    try:
        config["image_settings"] = get_settings()
    except Exception:
        config["image_settings"] = {}
    
    # tavily config
    try:
        config["tavily_config"] = get_tavily_config()
    except Exception:
        config["tavily_config"] = {}
    
    # server config (不含敏感信息)
    try:
        server_cfg = get_server_config()
        config["server_config"] = server_cfg
    except Exception:
        config["server_config"] = {}
    
    return config


def _import_config(config: dict):
    """导入配置（api_key 会被加密后存储）"""
    if not isinstance(config, dict):
        return
    
    # providers
    providers = config.get("providers", [])
    if isinstance(providers, list) and providers:
        try:
            from services.provider_service import _save, list_providers
            # 直接覆盖：用备份中的 providers 替换当前
            _save(providers)
        except Exception as e:
            import logging
            logging.warning("导入 providers 失败: %s", e)
    
    # vector config
    vc = config.get("vector_config", {})
    if isinstance(vc, dict) and vc:
        try:
            update_vector_config(
                backend=vc.get("backend", ""),
                model_name=vc.get("model_name", ""),
                similarity_threshold=vc.get("similarity_threshold", 0.75),
                device=vc.get("device", "cpu"),
                use_independent_embedding=vc.get("use_independent_embedding", False),
                embedding_api_base=vc.get("embedding_api_base", ""),
                embedding_api_key=vc.get("embedding_api_key", ""),
                embedding_model=vc.get("embedding_model", ""),
                embedding_path=vc.get("embedding_path", ""),
            )
        except Exception as e:
            import logging
            logging.warning("导入 vector_config 失败: %s", e)
    
    # reranker config
    rc = config.get("reranker_config", {})
    if isinstance(rc, dict) and rc:
        try:
            from services.reranker_service import update_reranker_config
            update_reranker_config(
                enabled=rc.get("enabled", False),
                use_independent=rc.get("use_independent", False),
                api_base=rc.get("api_base", ""),
                api_key=rc.get("api_key", ""),
                model=rc.get("model", ""),
                rerank_path=rc.get("rerank_path", ""),
                top_n=rc.get("top_n", 3),
            )
        except Exception as e:
            import logging
            logging.warning("导入 reranker_config 失败: %s", e)
    
    # image settings
    is_cfg = config.get("image_settings", {})
    if isinstance(is_cfg, dict) and is_cfg:
        try:
            update_settings(
                image_api_url=is_cfg.get("image_api_url", ""),
                image_api_key=is_cfg.get("image_api_key", ""),
                image_api_model=is_cfg.get("image_api_model", ""),
            )
        except Exception as e:
            import logging
            logging.warning("导入 image_settings 失败: %s", e)
    
    # tavily config
    tc = config.get("tavily_config", {})
    if isinstance(tc, dict) and tc:
        try:
            update_tavily_config(tc.get("tavily_api_key", ""))
        except Exception as e:
            import logging
            logging.warning("导入 tavily_config 失败: %s", e)
    
    # server config
    sc = config.get("server_config", {})
    if isinstance(sc, dict) and sc:
        try:
            update_server_config(**sc)
        except Exception as e:
            import logging
            logging.warning("导入 server_config 失败: %s", e)


def import_backup(data: dict, include_config: bool = False) -> dict:
    """导入备份数据
    
    Args:
        data: 备份数据 dict
        include_config: 是否导入配置（providers/vector/reranker/image/tavily）
    
    返回导入统计
    """
    if not isinstance(data, dict):
        raise ValueError("备份数据格式无效")

    # 安全限制：防止导入过大数据
    MAX_NOVELS = 100
    MAX_CHAPTERS_PER_NOVEL = 500
    MAX_CHARS_PER_NOVEL = 200
    MAX_RELS_PER_NOVEL = 200

    # 在打开连接前做基础校验，避免无谓的连接占用
    novels_data = data.get("novels", [])
    if not isinstance(novels_data, list) or len(novels_data) > MAX_NOVELS:
        raise ValueError(f"小说数量无效（最多 {MAX_NOVELS} 部）")

    imported = {"novels": 0, "chapters": 0, "characters": 0, "relationships": 0,
                "wiki_entries": 0, "pending_changes": 0, "config": False}
    novel_ids = set()

    # closing 确保连接关闭；with conn 形成事务（正常结束 commit，异常自动 rollback）
    with closing(get_db()) as conn:
        with conn:
            # 导入小说：INSERT OR IGNORE 插入新小说（已存在的忽略，避免级联删除），随后 UPDATE 覆盖为备份值
            for novel in novels_data[:MAX_NOVELS]:
                if not isinstance(novel, dict):
                    continue
                nid = novel.get("id", str(uuid.uuid4()))
                if not isinstance(nid, str) or len(nid) < 1:
                    nid = str(uuid.uuid4())
                novel_ids.add(nid)

                title = str(novel.get("title", ""))[:200]
                title_mode = str(novel.get("title_mode", "auto"))[:20]
                outline = str(novel.get("outline", ""))
                world_building = str(novel.get("world_building", ""))
                character_profiles = str(novel.get("character_profiles", ""))
                words_per_chapter = int(novel.get("words_per_chapter", 3000))
                duplicate_check_interval = int(novel.get("duplicate_check_interval", 3))
                summary_chapters_count = int(novel.get("summary_chapters_count", 3))
                style_reference = str(novel.get("style_reference", ""))
                created_at = str(novel.get("created_at", ""))
                updated_at = str(novel.get("updated_at", ""))

                conn.execute(
                    """INSERT OR IGNORE INTO novels
                       (id, title, title_mode, outline, world_building, character_profiles,
                        words_per_chapter, duplicate_check_interval, summary_chapters_count,
                        style_reference, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (nid, title, title_mode, outline, world_building, character_profiles,
                     words_per_chapter, duplicate_check_interval, summary_chapters_count,
                     style_reference, created_at, updated_at),
                )
                # 无论新建还是已存在，统一用备份值覆盖（UPDATE 不会触发级联删除）
                conn.execute(
                    """UPDATE novels SET title=?, title_mode=?, outline=?, world_building=?,
                       character_profiles=?, words_per_chapter=?, duplicate_check_interval=?,
                       summary_chapters_count=?, style_reference=?, created_at=?, updated_at=?
                       WHERE id=?""",
                    (title, title_mode, outline, world_building, character_profiles,
                     words_per_chapter, duplicate_check_interval, summary_chapters_count,
                     style_reference, created_at, updated_at, nid),
                )
                imported["novels"] += 1

            # 导入章节：同样使用 INSERT OR IGNORE + UPDATE，避免 REPLACE 级联删除
            chapters_data = data.get("chapters", [])
            if isinstance(chapters_data, list):
                for ch in chapters_data[:MAX_NOVELS * MAX_CHAPTERS_PER_NOVEL]:
                    if not isinstance(ch, dict):
                        continue
                    cid = ch.get("id", str(uuid.uuid4()))
                    nid = ch.get("novel_id", "")
                    if nid not in novel_ids:
                        continue  # 跳过不属于任何小说的章节
                    number = int(ch.get("number", 0))
                    title = str(ch.get("title", ""))[:200]
                    content = str(ch.get("content", ""))
                    status = str(ch.get("status", "draft"))[:20]
                    words_count = int(ch.get("words_count", 0))
                    embedding_json = str(ch.get("embedding_json", ""))
                    created_at = str(ch.get("created_at", ""))
                    updated_at = str(ch.get("updated_at", ""))

                    conn.execute(
                        """INSERT OR IGNORE INTO chapters
                           (id, novel_id, number, title, content, status, words_count,
                            embedding_json, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (cid, nid, number, title, content, status, words_count,
                         embedding_json, created_at, updated_at),
                    )
                    conn.execute(
                        """UPDATE chapters SET novel_id=?, number=?, title=?, content=?,
                           status=?, words_count=?, embedding_json=?, created_at=?, updated_at=?
                           WHERE id=?""",
                        (nid, number, title, content, status, words_count, embedding_json,
                         created_at, updated_at, cid),
                    )
                    imported["chapters"] += 1

            # 导入人物画像：同样使用 INSERT OR IGNORE + UPDATE
            chars_data = data.get("characters", [])
            if isinstance(chars_data, list):
                for c in chars_data[:MAX_NOVELS * MAX_CHARS_PER_NOVEL]:
                    if not isinstance(c, dict):
                        continue
                    cid = c.get("id", str(uuid.uuid4()))
                    nid = c.get("novel_id", "")
                    if nid not in novel_ids:
                        continue
                    name = str(c.get("name", ""))[:50]
                    profile = str(c.get("profile", ""))
                    created_at = str(c.get("created_at", ""))
                    updated_at = str(c.get("updated_at", ""))

                    conn.execute(
                        """INSERT OR IGNORE INTO characters
                           (id, novel_id, name, profile, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (cid, nid, name, profile, created_at, updated_at),
                    )
                    conn.execute(
                        """UPDATE characters SET novel_id=?, name=?, profile=?,
                           created_at=?, updated_at=? WHERE id=?""",
                        (nid, name, profile, created_at, updated_at, cid),
                    )
                    imported["characters"] += 1

            # 导入人物关系：同样使用 INSERT OR IGNORE + UPDATE
            rels_data = data.get("character_relationships", [])
            if isinstance(rels_data, list):
                for r in rels_data[:MAX_NOVELS * MAX_RELS_PER_NOVEL]:
                    if not isinstance(r, dict):
                        continue
                    rid = r.get("id", str(uuid.uuid4()))
                    nid = r.get("novel_id", "")
                    if nid not in novel_ids:
                        continue
                    character_a = str(r.get("character_a", ""))[:50]
                    character_b = str(r.get("character_b", ""))[:50]
                    relation_type = str(r.get("relation_type", ""))[:30]
                    description = str(r.get("description", ""))
                    created_at = str(r.get("created_at", ""))
                    updated_at = str(r.get("updated_at", ""))

                    conn.execute(
                        """INSERT OR IGNORE INTO character_relationships
                           (id, novel_id, character_a, character_b, relation_type, description,
                            created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (rid, nid, character_a, character_b, relation_type, description,
                         created_at, updated_at),
                    )
                    conn.execute(
                        """UPDATE character_relationships SET novel_id=?, character_a=?,
                           character_b=?, relation_type=?, description=?, created_at=?, updated_at=?
                           WHERE id=?""",
                        (nid, character_a, character_b, relation_type, description,
                         created_at, updated_at, rid),
                    )
                    imported["relationships"] += 1

            # 导入百科条目（v2 新增）
            wiki_data = data.get("wiki_entries", [])
            if isinstance(wiki_data, list):
                for w in wiki_data:
                    if not isinstance(w, dict):
                        continue
                    wid = w.get("id", str(uuid.uuid4()))
                    nid = w.get("novel_id", "")
                    if nid not in novel_ids:
                        continue
                    category = str(w.get("category", ""))[:30]
                    name = str(w.get("name", ""))[:100]
                    description = str(w.get("description", ""))
                    created_at = str(w.get("created_at", ""))
                    updated_at = str(w.get("updated_at", ""))
                    if category not in WIKI_CATEGORIES:
                        continue

                    conn.execute(
                        """INSERT OR IGNORE INTO wiki_entries
                           (id, novel_id, category, name, description, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (wid, nid, category, name, description, created_at, updated_at),
                    )
                    conn.execute(
                        """UPDATE wiki_entries SET novel_id=?, category=?, name=?, description=?,
                           created_at=?, updated_at=? WHERE id=?""",
                        (nid, category, name, description, created_at, updated_at, wid),
                    )
                    imported["wiki_entries"] += 1

            # 导入待确认变更（v2 新增）
            pending_data = data.get("pending_changes", [])
            if isinstance(pending_data, list):
                for p in pending_data:
                    if not isinstance(p, dict):
                        continue
                    pid = p.get("id", str(uuid.uuid4()))
                    nid = p.get("novel_id", "")
                    if nid not in novel_ids:
                        continue
                    conn.execute(
                        """INSERT OR IGNORE INTO pending_changes
                           (id, novel_id, chapter_number, tool_name, target_name,
                            old_content, new_content, change_summary, status, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (pid, nid, p.get("chapter_number", 0),
                         str(p.get("tool_name", ""))[:50],
                         str(p.get("target_name", ""))[:200],
                         str(p.get("old_content", "")),
                         str(p.get("new_content", "")),
                         str(p.get("change_summary", "")),
                         str(p.get("status", "pending"))[:20],
                         str(p.get("created_at", ""))),
                    )
                    imported["pending_changes"] += 1

    # 导入配置（可选）
    if include_config and data.get("config"):
        try:
            _import_config(data["config"])
            imported["config"] = True
        except Exception as e:
            import logging
            logging.warning("导入配置失败: %s", e)

    return imported


def create_chapter_manual(novel_id: str, title: str, content: str,
                          chapter_number: Optional[int] = None) -> dict:
    """手动创建章节（不调用AI）"""
    chapters = get_chapters(novel_id)
    if chapter_number is None:
        # 使用最大章节号 + 1，而非 len + 1，避免删除章节后号冲突
        chapter_number = max((ch["number"] for ch in chapters), default=0) + 1

    words_count = len(content)
    chapter_id = str(uuid.uuid4())
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        conn.execute(
            """INSERT INTO chapters (id, novel_id, number, title, content, status, words_count)
               VALUES (?, ?, ?, ?, ?, 'draft', ?)""",
            (chapter_id, novel_id, chapter_number, title, content, words_count),
        )
        conn.execute(
            "UPDATE novels SET updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), novel_id),
        )
        conn.commit()
    return get_chapter(chapter_id)


# ==================== 世界观百科 ====================

WIKI_CATEGORIES = {
    'location': '地点',
    'faction': '势力阵营',
    'item': '物品道具',
    'event': '事件时间线',
}


def get_wiki_entries(novel_id: str, category: str = "") -> list[dict]:
    """获取百科条目，可按类别筛选"""
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        if category:
            rows = conn.execute(
                "SELECT * FROM wiki_entries WHERE novel_id=? AND category=? ORDER BY sort_order, created_at",
                (novel_id, category),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM wiki_entries WHERE novel_id=? ORDER BY category, sort_order, created_at",
                (novel_id,),
            ).fetchall()
    return [wiki_entry_row_to_dict(r) for r in rows]


def create_wiki_entry(novel_id: str, category: str, name: str,
                      description: str = "", metadata: str = "") -> dict:
    """创建一条百科条目"""
    if category not in WIKI_CATEGORIES:
        raise ValueError(f"无效的类别: {category}")
    if not name or not name.strip():
        raise ValueError("名称不能为空")

    entry_id = str(uuid.uuid4())
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        # 自动计算 sort_order（同类别末尾追加）
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) AS m FROM wiki_entries WHERE novel_id=? AND category=?",
            (novel_id, category),
        ).fetchone()
        sort_order = (max_order["m"] if max_order else -1) + 1
        conn.execute(
            """INSERT INTO wiki_entries (id, novel_id, category, name, description, metadata, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (entry_id, novel_id, category, name.strip(), description, metadata, sort_order),
        )
        conn.execute(
            "UPDATE novels SET updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), novel_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM wiki_entries WHERE id = ?", (entry_id,)).fetchone()
    return wiki_entry_row_to_dict(row)


def update_wiki_entry(entry_id: str, name: str = "",
                      description: str = "", metadata: str = "") -> Optional[dict]:
    """更新百科条目，仅更新非空字段"""
    updates = {}
    if name:
        updates["name"] = name.strip()
    # description / metadata 允许清空：用 None 占位的语义不可行，
    # 这里约定「未传」用空字符串表示跳过，传 "" 视为清空。
    # 因此只有当调用者明确传入非空字符串时才更新 description / metadata。
    # 但为了允许清空，采用「全字段都更新」的策略：
    # 由于本函数签名区分不出来「未传」与「空字符串」，这里直接接受传入值覆盖。
    if description is not None and description != "":
        updates["description"] = description
    if metadata is not None and metadata != "":
        updates["metadata"] = metadata
    if not updates:
        # 仍要返回当前条目，便于调用方获取
        with closing(get_db()) as conn:
            row = conn.execute("SELECT * FROM wiki_entries WHERE id = ?", (entry_id,)).fetchone()
        return wiki_entry_row_to_dict(row) if row else None

    updates["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [entry_id]
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        conn.execute(f"UPDATE wiki_entries SET {set_clause} WHERE id = ?", values)
        row = conn.execute("SELECT * FROM wiki_entries WHERE id = ?", (entry_id,)).fetchone()
        if row:
            # 同步更新对应小说的 updated_at
            conn.execute(
                "UPDATE novels SET updated_at = ? WHERE id = (SELECT novel_id FROM wiki_entries WHERE id=?)",
                (datetime.now().isoformat(), entry_id),
            )
        conn.commit()
    return wiki_entry_row_to_dict(row) if row else None


def delete_wiki_entry(entry_id: str):
    """删除百科条目"""
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        row = conn.execute("SELECT novel_id FROM wiki_entries WHERE id = ?", (entry_id,)).fetchone()
        conn.execute("DELETE FROM wiki_entries WHERE id = ?", (entry_id,))
        if row:
            conn.execute(
                "UPDATE novels SET updated_at = ? WHERE id = ?",
                (datetime.now().isoformat(), row["novel_id"]),
            )
        conn.commit()


async def ai_generate_wiki_entries(novel_id: str, custom_prompt: str = "") -> dict:
    """AI 根据大纲和世界观自动生成百科条目，返回预览（不直接保存）"""
    novel = get_novel(novel_id)
    if not novel:
        raise ValueError("小说不存在")

    context = []
    if novel.get("outline"):
        context.append(f"【大纲】\n{novel['outline'][:1000]}")
    if novel.get("world_building"):
        context.append(f"【世界观】\n{novel['world_building'][:800]}")

    # 已有角色信息
    characters = get_characters(novel_id)
    if characters:
        char_names = [c["name"] for c in characters]
        context.append(f"【已有角色】\n{', '.join(char_names)}")

    # 已有条目避免重复
    existing = get_wiki_entries(novel_id)
    existing_names = [e["name"] for e in existing]
    if existing_names:
        context.append(f"【已有条目（不要重复）】\n{', '.join(existing_names)}")

    if not any([novel.get("outline"), novel.get("world_building")]):
        raise ValueError("请先填写大纲或世界观设定，AI 才能生成百科条目")

    joined = "\n\n".join(context)

    prompt = f"""你是小说世界观设定师。根据以下作品信息，提炼出这部小说中需要记录的世界观百科条目。

# 作品信息
{joined}

# 生成规则
1. 从大纲和世界观中提取真实存在的设定，不要凭空创造与设定矛盾的内容
2. 每个类别（地点 / 势力阵营 / 物品道具 / 事件时间线）生成 2-6 条核心条目
3. 地点：故事发生的关键场所、城市、地理区域
4. 势力阵营：组织、国家、门派、家族等有组织属性的群体
5. 物品道具：对剧情有推动作用的关键物品、法宝、神器
6. 事件时间线：影响世界格局或主线发展的重要历史事件、转折点
7. 每条目描述控制在 30-150 字，简明扼要说明其本质和剧情意义
8. 严格不要与「已有条目」重复
9. 类别必须从以下四个英文标识中选择：location / faction / item / event

# 输出格式
严格按以下格式，每行一个条目，用 | 分隔三段，不要加任何额外说明、标题或编号：

类别 | 名称 | 描述

示例：
location | 玄霄宗 | 位于天柱峰顶的修真大派，主角入门修行之地
faction | 魔道联盟 | 由七大魔门组成的松散联盟，长期与正道为敌
item | 碎星剑 | 上古陨铁所铸灵剑，剑灵觉醒后可破万法
event | 万妖之乱 | 三百年前妖族大举入侵，正魔两道被迫联手抵御的浩劫

只输出条目列表，不要输出任何其他内容。"""

    if custom_prompt:
        prompt += f"\n\n# 用户附加要求\n{custom_prompt}"

    try:
        resp = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
            temperature=0.6,
        )
        result_text = resp["choices"][0]["message"]["content"].strip()

        # 解析：每行一条「类别 | 名称 | 描述」
        entries = []
        seen_names = set()
        valid_categories = set(WIKI_CATEGORIES.keys())
        for raw_line in result_text.split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            # 去掉可能的行首编号（如 "1."、"-"、"*"）
            line = re.sub(r'^[\d]+[\.\)]?\s*', '', line)
            line = line.lstrip('-*•').strip()
            if '|' not in line:
                continue
            parts = [p.strip() for p in line.split('|', 2)]
            if len(parts) < 3:
                continue
            cat, name, desc = parts[0], parts[1], parts[2]
            # 类别别名映射（容错）
            cat_lower = cat.lower()
            if cat_lower not in valid_categories:
                # 尝试中文 → 英文（注意：空字符串 in 任意字符串恒为 True，必须先排除）
                if cat:
                    for en, zh in WIKI_CATEGORIES.items():
                        if cat in zh or zh in cat:
                            cat_lower = en
                            break
            if cat_lower not in valid_categories:
                continue
            if not name or len(name) > 50:
                continue
            # 去重（已有或本次已出现）
            if name in existing_names or name in seen_names:
                continue
            seen_names.add(name)
            entries.append({
                "category": cat_lower,
                "name": name,
                "description": desc,
            })

        return {
            "entries": entries,
            "existing_count": len(existing_names),
        }
    except Exception as e:
        raise ValueError(f"AI 生成百科条目失败: {str(e)}")


def apply_generated_wiki_entries(novel_id: str, entries: list[dict]) -> dict:
    """批量应用 AI 生成的百科条目（前端选择后调用）"""
    created = []
    for e in entries:
        category = e.get("category", "").strip()
        name = e.get("name", "").strip()
        if not category or not name:
            continue
        if category not in WIKI_CATEGORIES:
            continue
        description = e.get("description", "") or ""
        metadata = e.get("metadata", "") or ""
        try:
            entry = create_wiki_entry(novel_id, category, name, description, metadata)
            created.append(entry)
        except ValueError:
            continue
    return {"entries": created, "count": len(created)}


# ==================== 待确认的设定变更 ====================

def create_pending_change(novel_id: str, chapter_number: int, tool_name: str,
                          target_name: str, old_content: str, new_content: str,
                          change_summary: str = "") -> dict:
    """创建一条待确认的设定变更记录"""
    change_id = str(uuid.uuid4())
    with closing(get_db()) as conn:
        conn.execute(
            """INSERT INTO pending_changes
               (id, novel_id, chapter_number, tool_name, target_name,
                old_content, new_content, change_summary, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (change_id, novel_id, chapter_number, tool_name, target_name,
             old_content, new_content, change_summary),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM pending_changes WHERE id = ?", (change_id,)).fetchone()
    return pending_change_row_to_dict(row)


def get_pending_changes(novel_id: str, status: str = "pending") -> list[dict]:
    """获取待确认的设定变更列表，按时间倒序"""
    with closing(get_db()) as conn:
        if status == "all":
            rows = conn.execute(
                "SELECT * FROM pending_changes WHERE novel_id=? ORDER BY created_at DESC",
                (novel_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM pending_changes WHERE novel_id=? AND status=? ORDER BY created_at DESC",
                (novel_id, status),
            ).fetchall()
    return [pending_change_row_to_dict(r) for r in rows]


def update_pending_change_status(change_id: str, status: str) -> Optional[dict]:
    """更新变更状态（accepted / rejected）"""
    if status not in ("accepted", "rejected"):
        raise ValueError("状态必须是 accepted 或 rejected")
    with closing(get_db()) as conn:
        conn.execute(
            "UPDATE pending_changes SET status = ? WHERE id = ?",
            (status, change_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM pending_changes WHERE id = ?", (change_id,)).fetchone()
    return pending_change_row_to_dict(row) if row else None


def delete_pending_change(change_id: str) -> bool:
    """删除一条变更记录"""
    with closing(get_db()) as conn:
        cur = conn.execute("DELETE FROM pending_changes WHERE id = ?", (change_id,))
        conn.commit()
        return cur.rowcount > 0


# ==================== 图片生成 API 配置 ====================

def get_settings() -> dict:
    """读取图片生成 API 配置（存储在 settings 表 key='image_api' 行）
    image_api_key 加密存储，读取时自动解密
    """
    from services.secret_service import decrypt_value
    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        row = conn.execute(
            "SELECT image_api_url, image_api_key, image_api_model FROM settings WHERE key = 'image_api'"
        ).fetchone()
    if not row:
        return {"image_api_url": "", "image_api_key": "", "image_api_model": ""}
    return {
        "image_api_url": row["image_api_url"] if row["image_api_url"] else "",
        "image_api_key": decrypt_value(row["image_api_key"]) if row["image_api_key"] else "",
        "image_api_model": row["image_api_model"] if row["image_api_model"] else "",
    }


def update_settings(image_api_url: str = "", image_api_key: str = "",
                    image_api_model: str = "") -> dict:
    """更新图片生成 API 配置。
    空字符串表示清空对应字段；未传字段（None）表示不修改。
    image_api_key 会加密后存储。
    """
    from services.secret_service import encrypt_value
    updates = {}
    if image_api_url is not None:
        updates["image_api_url"] = image_api_url
    if image_api_key is not None:
        # 加密后存储（空值不加密）
        updates["image_api_key"] = encrypt_value(image_api_key) if image_api_key else ""
    if image_api_model is not None:
        updates["image_api_model"] = image_api_model

    # 使用 closing 确保连接在任何情况下都会关闭，避免连接泄漏
    with closing(get_db()) as conn:
        # 先确保 key='image_api' 行存在
        existing = conn.execute(
            "SELECT key FROM settings WHERE key = 'image_api'"
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO settings (key, value, image_api_url, image_api_key, image_api_model) "
                "VALUES ('image_api', '', ?, ?, ?)",
                (
                    updates.get("image_api_url", ""),
                    updates.get("image_api_key", ""),
                    updates.get("image_api_model", ""),
                ),
            )
        else:
            if updates:
                set_clause = ", ".join(f"{k} = ?" for k in updates)
                values = list(updates.values())
                conn.execute(
                    f"UPDATE settings SET {set_clause} WHERE key = 'image_api'",
                    values,
                )
        conn.commit()
    return get_settings()


# ==================== Tavily 网络搜索配置 ====================

def get_tavily_config() -> dict:
    """获取 Tavily API 配置（tavily_api_key 加密存储，读取时自动解密）"""
    from services.secret_service import decrypt_value
    with closing(get_db()) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='tavily_api'").fetchone()
        if row and row["value"]:
            cfg = json.loads(row["value"])
            # 透明解密 tavily_api_key
            if cfg.get("tavily_api_key"):
                cfg["tavily_api_key"] = decrypt_value(cfg["tavily_api_key"])
            return cfg
    return {"tavily_api_key": ""}


def update_tavily_config(tavily_api_key: str):
    """更新 Tavily API 配置（tavily_api_key 加密后存储）"""
    from services.secret_service import encrypt_value
    encrypted_key = encrypt_value(tavily_api_key) if tavily_api_key else ""
    with closing(get_db()) as conn:
        config = json.dumps({"tavily_api_key": encrypted_key})
        conn.execute("""
            INSERT INTO settings (key, value) VALUES ('tavily_api', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (config,))
        conn.commit()


async def tavily_search(query: str, max_results: int = 5) -> dict:
    """使用 Tavily API 进行网络搜索"""
    config = get_tavily_config()
    api_key = config.get("tavily_api_key", "")
    if not api_key:
        return {"error": "Tavily API 未配置，请在设置中配置 Tavily API Key", "results": []}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                },
            )
            if resp.status_code != 200:
                return {"error": f"Tavily API 错误 ({resp.status_code})", "results": []}
            data = resp.json()
            results = []
            for r in data.get("results", []):
                results.append({
                    "title": r.get("title", ""),
                    "content": r.get("content", ""),
                    "url": r.get("url", ""),
                })
            return {"query": query, "results": results}
    except Exception as e:
        logger.error(f"Tavily 搜索失败: {e}")
        return {"error": f"搜索失败: {str(e)}", "results": []}


# ==================== 服务器配置 ====================

def get_server_config() -> dict:
    """获取服务器绑定配置"""
    with closing(get_db()) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='server_config'").fetchone()
        if row and row["value"]:
            try:
                return json.loads(row["value"])
            except json.JSONDecodeError:
                pass
    return {"host": "127.0.0.1", "port": 8000}


def update_server_config(host: str = None, port: int = None) -> dict:
    """更新服务器绑定配置。None 表示不修改对应字段。"""
    current = get_server_config()
    if host is not None:
        # 安全：仅允许合法的绑定地址
        allowed_hosts = ["127.0.0.1", "0.0.0.0", "localhost"]
        if host not in allowed_hosts:
            raise ValueError(f"不允许的绑定地址，仅支持: {', '.join(allowed_hosts)}")
        current["host"] = host
    if port is not None:
        if not (1 <= port <= 65535):
            raise ValueError("端口必须在 1-65535 范围内")
        current["port"] = port
    with closing(get_db()) as conn:
        config = json.dumps(current)
        conn.execute("""
            INSERT INTO settings (key, value) VALUES ('server_config', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (config,))
        conn.commit()
    return current


# ==================== 联网搜索参考资料 ====================

async def web_search_for_reference(query: str) -> dict:
    """使用 LLM 的搜索能力搜索参考资料。

    通过 chat_completion 调用 LLM，让模型基于自身知识返回结构化参考资料。
    返回 {query, results: [{title, content, url}]}。
    """
    if not query or not query.strip():
        return {"query": query, "results": [], "error": "搜索内容不能为空"}

    prompt = f"""你是资料检索助手。请针对以下写作相关的查询，给出 3-5 条参考资料。
每条资料应包含：标题、正文摘要（80-200字，与查询紧密相关、可被作家直接借鉴的实质性内容）、来源URL（如能给出可信来源请提供，否则留空字符串）。

查询：{query}

严格按以下 JSON 数组格式输出，不要输出 JSON 之外的任何文字、解释或 Markdown 代码块标记：

[
  {{"title": "资料标题1", "content": "资料摘要正文1", "url": "https://..."}},
  {{"title": "资料标题2", "content": "资料摘要正文2", "url": "https://..."}}
]

注意：内容必须真实、与查询相关，不要编造看似权威实则虚假的URL；若不确定URL可留空字符串。"""

    try:
        resp = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=1500,
        )
        text = resp["choices"][0]["message"]["content"].strip()
        results = _parse_search_results(text)
        return {"query": query, "results": results}
    except Exception as e:
        logging.exception("web_search_for_reference 失败")
        return {"query": query, "results": [], "error": f"搜索失败: {str(e)}"}


def _parse_search_results(text: str) -> list[dict]:
    """从 LLM 返回文本中解析搜索结果 JSON 列表，容错处理"""
    if not text:
        return []
    # 去除可能的 Markdown 代码块标记
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # 移除首行 ``` 或 ```json
        lines = cleaned.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    # 截取第一个 JSON 数组
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    json_str = cleaned[start:end + 1]
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    results = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        content = str(item.get("content", "")).strip()
        url = str(item.get("url", "")).strip()
        if not title and not content:
            continue
        results.append({"title": title, "content": content, "url": url})
    return results


# ==================== AI 配图 ====================

def _build_image_prompt(image_type: str, name: str, description: str, novel: dict = None) -> str:
    """根据类型构造图片生成 prompt"""
    novel_title = (novel or {}).get("title", "")
    world = (novel or {}).get("world_building", "") or ""

    type_map = {
        "character": "character portrait, full body, detailed face, costume design",
        "scene": "scene illustration, environment, atmosphere, wide shot",
        "cover": "book cover illustration, dramatic composition, eye-catching",
    }
    type_hint = type_map.get(image_type, "illustration")

    parts = []
    if image_type == "character":
        parts.append(f"Character portrait of {name or 'a character'}")
    elif image_type == "scene":
        parts.append(f"Scene illustration of {name or 'a location'}")
    elif image_type == "cover":
        parts.append(f"Book cover illustration for novel '{novel_title or name or 'Untitled'}'")

    if description:
        parts.append(description)
    if world:
        parts.append(f"world setting context: {world[:300]}")

    parts.append(type_hint)
    parts.append("high quality, detailed, cinematic lighting, digital art")
    return ", ".join(parts)


async def generate_image(novel_id: str, image_type: str, name: str, description: str) -> dict:
    """生成角色立绘 / 场景图 / 封面图。

    检查 settings 中的图片生成 API 配置；若未配置则返回 error 提示，
    不抛异常以便前端优雅降级。
    """
    valid_types = {"character", "scene", "cover"}
    if image_type not in valid_types:
        return {"error": f"无效的图片类型: {image_type}"}

    cfg = get_settings()
    api_url = cfg.get("image_api_url", "").strip()
    api_key = cfg.get("image_api_key", "").strip()
    api_model = cfg.get("image_api_model", "").strip()

    if not api_url:
        return {"error": "图片生成 API 未配置，请在设置中配置图片生成 API"}

    # 自动修正 API URL：
    # 用户可能填的是 base URL（如 https://api.openai.com/v1）或聊天接口（/v1/chat/completions）
    # 图片生成需要用 /v1/images/generations 接口
    original_url = api_url
    # 1. 如果 URL 以 /chat/completions 结尾，替换为 /images/generations
    if api_url.rstrip('/').endswith('/chat/completions'):
        api_url = api_url.rstrip('/')[:-len('/chat/completions')] + '/images/generations'
    # 2. 如果 URL 以 /completions 结尾，替换为 /images/generations
    elif api_url.rstrip('/').endswith('/completions'):
        api_url = api_url.rstrip('/')[:-len('/completions')] + '/images/generations'
    # 3. 如果 URL 以 /v1 结尾（base URL），补全 /images/generations
    elif api_url.rstrip('/').endswith('/v1'):
        api_url = api_url.rstrip('/') + '/images/generations'
    # 4. 如果 URL 不含 /images/generations 且不以 / 结尾，且看起来是 base URL（无具体端点路径）
    elif '/images/generations' not in api_url and '/chat/' not in api_url and '/completions' not in api_url:
        # 可能是 base URL 如 https://api.example.com 或 https://api.example.com/v1/
        api_url = api_url.rstrip('/') + ('/v1/images/generations' if '/v1' not in api_url else '/images/generations')

    if api_url != original_url:
        logging.info(f"图片生成 API URL 自动修正: {original_url} -> {api_url}")

    novel = get_novel(novel_id) if novel_id else None
    prompt = _build_image_prompt(image_type, name, description, novel)

    # 兼容 OpenAI 风格的 images/generations 接口
    payload = {"prompt": prompt, "n": 1, "size": "1024x1024"}
    if api_model:
        payload["model"] = api_model

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            resp = await client.post(api_url, json=payload, headers=headers)
            if resp.status_code >= 400:
                body = resp.text[:500]
                return {"error": f"图片 API 错误 ({resp.status_code}): {body}"}
            data = resp.json()
        # 兼容多种返回格式
        image_url = ""
        if isinstance(data, dict):
            if data.get("data") and isinstance(data["data"], list) and data["data"]:
                first = data["data"][0]
                if isinstance(first, dict):
                    image_url = first.get("url") or first.get("image_url") or ""
                    if not image_url and first.get("b64_json"):
                        image_url = "data:image/png;base64," + first["b64_json"]
                elif isinstance(first, str):
                    image_url = first
            elif data.get("url"):
                image_url = data["url"]
            elif data.get("image_url"):
                image_url = data["image_url"]
            elif data.get("b64_json"):
                image_url = "data:image/png;base64," + data["b64_json"]

        if not image_url:
            return {"error": "图片 API 未返回有效的图片URL"}

        # 如果是封面，下载图片到本地（避免远程 URL 过期）
        # 封面文件名固定为 novel_{novel_id}.png，通过文件名规则即可找到，无需存数据库
        if image_type == "cover":
            local_path = await _download_cover_to_local(novel_id, image_url)
            if local_path:
                return {"image_url": local_path, "prompt": prompt}
            # 下载失败则回退到远程 URL（虽然会过期，但至少能临时显示）
            logging.warning(f"封面下载失败，回退到远程 URL: {image_url[:100]}")

        return {"image_url": image_url, "prompt": prompt}
    except httpx.HTTPError as e:
        logging.exception("generate_image 网络错误")
        # httpx 的 ConnectError 等异常 str() 可能为空，补充类型信息
        err_msg = str(e) or type(e).__name__
        return {"error": f"图片生成请求失败: {err_msg}"}
    except Exception as e:
        logging.exception("generate_image 失败")
        return {"error": f"图片生成失败: {str(e)}"}


async def _download_cover_to_local(novel_id: str, image_url: str) -> str:
    """下载封面图片到本地 covers 目录。

    封面文件名固定为 novel_{novel_id}.png，通过文件名规则即可找到，无需存数据库。
    返回本地 URL 路径（如 /static/covers/novel_xxx.png），失败返回空字符串。
    支持 http(s) URL 和 data:image/...;base64,... 格式。
    """
    import base64
    import re as _re
    from config import COVERS_DIR

    try:
        # 确保目录存在
        COVERS_DIR.mkdir(parents=True, exist_ok=True)
        # 文件名固定为 novel_{novel_id}.png（统一扩展名，浏览器通过文件头识别格式）
        filename = f"novel_{_sanitize_filename(novel_id)}.png"
        filepath = COVERS_DIR / filename

        # 处理 data URL（base64 内嵌图片）
        if image_url.startswith("data:image/"):
            match = _re.match(r"data:image/(\w+);base64,(.+)", image_url)
            if not match:
                return ""
            img_data = base64.b64decode(match.group(2))
            filepath.write_bytes(img_data)
            logging.info(f"封面已保存到本地（base64）: {filepath}")
            return f"/static/covers/{filename}"

        # 处理 http(s) URL
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            resp = await client.get(image_url)
            if resp.status_code >= 400:
                logging.warning(f"下载封面失败: HTTP {resp.status_code}")
                return ""
            img_data = resp.content

        filepath.write_bytes(img_data)
        logging.info(f"封面已下载到本地: {filepath} ({len(img_data)} bytes)")
        return f"/static/covers/{filename}"
    except Exception as e:
        logging.exception(f"下载封面到本地失败: {e}")
        return ""


# ==================== 文档导入分析 ====================

async def analyze_document(novel_id: str, content: str, doc_type: str = "reference") -> dict:
    """分析上传的文档，提取风格/角色/世界观等素材。

    doc_type:
      - reference: 提取写作风格、叙事手法、可借鉴的元素
      - worldbuilding: 提取地理/势力/物品等世界观元素
      - character: 提取角色特征和关系

    返回 {type, analysis: str, suggestions: [...]}
    """
    valid_types = {"reference", "worldbuilding", "character"}
    if doc_type not in valid_types:
        doc_type = "reference"

    if not content or not content.strip():
        return {"type": doc_type, "analysis": "", "suggestions": [], "error": "文档内容为空"}

    # 限制长度，避免 token 超限
    sample = content[:5000]

    novel = get_novel(novel_id) if novel_id else None
    novel_title = (novel or {}).get("title", "")

    if doc_type == "reference":
        prompt = f"""你是小说写作导师。请分析以下参考文本，提炼出可供作者借鉴的写作要点。

参考文本：
{sample}

请从以下维度分析：
1. 叙事视角与节奏
2. 语言风格与句式特征
3. 描写偏好（场景/心理/对话/动作）
4. 对话特点
5. 情感基调与氛围
6. 可借鉴的具体写作技巧（举 2-3 个原文中的例子）

直接输出分析正文，写成一段或几段连贯的文字，最后另起一行用「## 建议」开头列出 3-5 条可操作建议。"""

    elif doc_type == "worldbuilding":
        prompt = f"""你是小说世界观架构师。请从以下文本中提取世界观元素，整理成可直接用于小说设定的素材。

文本：
{sample}

请提取并归类以下元素（若文本中存在）：
1. 地点/场景：故事发生的关键场所、城市、地理区域
2. 势力/组织：国家、门派、家族、组织等有组织属性的群体
3. 物品/道具：对剧情有推动作用的关键物品
4. 历史事件：影响世界格局的重要事件
5. 规则体系：科技/魔法/武力等核心体系的规则与限制

直接输出分析正文，最后另起一行用「## 建议」开头列出 3-5 条如何将这些元素融入小说创作的建议。"""

    else:  # character
        prompt = f"""你是小说人物分析师。请从以下文本中提取角色特征和人物关系。

文本：
{sample}

请分析：
1. 出现的主要角色，每个角色的姓名（如有）、外貌特征、性格特点、背景、动机
2. 角色之间的关系类型与情感态度
3. 角色塑造上的写作技巧

直接输出分析正文，最后另起一行用「## 建议」开头列出 3-5 条如何借鉴这些角色塑造方法的建议。"""

    try:
        resp = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=2000,
        )
        analysis = resp["choices"][0]["message"]["content"].strip()

        # 从分析结果中拆分出「## 建议」部分
        suggestions = []
        if "## 建议" in analysis:
            main_part, _, sug_part = analysis.partition("## 建议")
            main_part = main_part.strip()
            sug_part = sug_part.strip()
            # 按行切分建议
            for line in sug_part.split("\n"):
                line = re.sub(r'^[\d]+[\.\)]?\s*', '', line.strip())
                line = line.lstrip('-*•').strip()
                if line:
                    suggestions.append(line)
            analysis = main_part
        else:
            # 没有明确标记时，按段落兜底提取短句作为建议
            for para in analysis.split("\n"):
                para = para.strip()
                if para and len(para) < 80 and (para.startswith("建议") or "可以" in para or "应" in para):
                    suggestions.append(para.lstrip("-*••").strip())

        return {
            "type": doc_type,
            "analysis": analysis,
            "suggestions": suggestions[:10],
            "novel_title": novel_title,
        }
    except Exception as e:
        logging.exception("analyze_document 失败")
        return {
            "type": doc_type,
            "analysis": "",
            "suggestions": [],
            "error": f"分析失败: {str(e)}",
        }