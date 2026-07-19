"""
数据模型 — 使用 SQLite + JSON 字段存储结构化数据
"""
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import DB_PATH


def get_db() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)  # busy_timeout 10秒
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")  # 写冲突时等待5秒
    return conn


def _get_settings_columns(conn) -> set:
    """获取 settings 表的列名集合"""
    cursor = conn.execute("PRAGMA table_info(settings)")
    return {row[1] for row in cursor.fetchall()}


def init_db():
    """初始化数据库表"""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS novels (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            title_mode TEXT DEFAULT 'auto',
            outline TEXT DEFAULT '',
            world_building TEXT DEFAULT '',
            character_profiles TEXT DEFAULT '',
            words_per_chapter INTEGER DEFAULT 3000,
            duplicate_check_interval INTEGER DEFAULT 3,
            summary_chapters_count INTEGER DEFAULT 3,
            style_reference TEXT DEFAULT '',
            expected_chapters INTEGER DEFAULT 0,
            max_tokens INTEGER DEFAULT 16384,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS chapters (
            id TEXT PRIMARY KEY,
            novel_id TEXT NOT NULL,
            number INTEGER NOT NULL,
            title TEXT DEFAULT '',
            content TEXT DEFAULT '',
            status TEXT DEFAULT 'draft',
            words_count INTEGER DEFAULT 0,
            embedding_json TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS character_relationships (
            id TEXT PRIMARY KEY,
            novel_id TEXT NOT NULL,
            character_a TEXT NOT NULL DEFAULT '',
            character_b TEXT NOT NULL DEFAULT '',
            relation_type TEXT DEFAULT '',
            description TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS characters (
            id TEXT PRIMARY KEY,
            novel_id TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            profile TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT '',
            auth_password TEXT DEFAULT '',
            auth_token TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS wiki_entries (
            id TEXT PRIMARY KEY,
            novel_id TEXT NOT NULL,
            category TEXT NOT NULL,  -- 'location', 'faction', 'item', 'event'
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            metadata TEXT DEFAULT '',  -- JSON: 额外属性（如地理坐标、势力等级等）
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
        );

        -- 索引：加速常用查询 + 级联删除
        CREATE INDEX IF NOT EXISTS idx_chapters_novel_number ON chapters(novel_id, number);
        CREATE INDEX IF NOT EXISTS idx_characters_novel ON characters(novel_id);
        CREATE INDEX IF NOT EXISTS idx_relationships_novel ON character_relationships(novel_id);
    """)

    # 待确认的设定变更表（AI 生成章节时产生的修改请求，需用户确认）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_changes (
            id TEXT PRIMARY KEY,
            novel_id TEXT NOT NULL,
            chapter_number INTEGER,
            tool_name TEXT NOT NULL,          -- update_outline / update_world_building / update_character
            target_name TEXT DEFAULT '',      -- 被修改的目标名称（如人物名）
            old_content TEXT DEFAULT '',      -- 原始内容
            new_content TEXT DEFAULT '',      -- AI 提议的新内容
            change_summary TEXT DEFAULT '',   -- AI 给出的修改理由
            status TEXT DEFAULT 'pending',    -- pending / accepted / rejected
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pending_changes_novel ON pending_changes(novel_id, status)")

    # 数据库迁移：确保 wiki_entries 表存在（兼容旧版数据库）
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wiki_entries (
                id TEXT PRIMARY KEY,
                novel_id TEXT NOT NULL,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                metadata TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wiki_entries_novel ON wiki_entries(novel_id, category)")
    except sqlite3.OperationalError:
        pass  # 表/索引已存在，忽略

    # 数据库迁移：为已有的 chapters 表添加 UNIQUE 约束（通过唯一索引实现）
    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_chapters_novel_number_unique ON chapters(novel_id, number)")
    except sqlite3.OperationalError:
        pass  # 可能已存在或有重复数据
    existing_cols = _get_settings_columns(conn)
    migrations = [
        ("auth_password", "TEXT DEFAULT ''"),
        ("auth_token", "TEXT DEFAULT ''"),
        # 图片生成 API 配置字段（key='image_api' 行使用）
        ("image_api_url", "TEXT DEFAULT ''"),
        ("image_api_key", "TEXT DEFAULT ''"),
        ("image_api_model", "TEXT DEFAULT ''"),
        # Tavily 网络搜索 API Key（key='tavily_api' 行使用）
        ("tavily_api_key", "TEXT DEFAULT ''"),
    ]
    for col_name, col_def in migrations:
        if col_name not in existing_cols:
            try:
                conn.execute(f"ALTER TABLE settings ADD COLUMN {col_name} {col_def}")
            except sqlite3.OperationalError:
                pass  # 列已存在，忽略

    # 数据库迁移：为旧版 novels 表添加缺失列
    novel_cols = {row[1] for row in conn.execute("PRAGMA table_info(novels)").fetchall()}
    novel_migrations = [
        ("style_reference", "TEXT DEFAULT ''"),
        ("title_mode", "TEXT DEFAULT 'auto'"),
        ("duplicate_check_interval", "INTEGER DEFAULT 3"),
        ("summary_chapters_count", "INTEGER DEFAULT 3"),
        ("expected_chapters", "INTEGER DEFAULT 0"),
        ("max_tokens", "INTEGER DEFAULT 16384"),
    ]
    for col_name, col_def in novel_migrations:
        if col_name not in novel_cols:
            try:
                conn.execute(f"ALTER TABLE novels ADD COLUMN {col_name} {col_def}")
            except sqlite3.OperationalError:
                pass

    # 数据库迁移：为旧版 chapters 表添加缺失列
    chapter_cols = {row[1] for row in conn.execute("PRAGMA table_info(chapters)").fetchall()}
    chapter_migrations = [
        ("words_count", "INTEGER DEFAULT 0"),
        ("embedding_json", "TEXT DEFAULT ''"),
        ("status", "TEXT DEFAULT 'draft'"),
    ]
    for col_name, col_def in chapter_migrations:
        if col_name not in chapter_cols:
            try:
                conn.execute(f"ALTER TABLE chapters ADD COLUMN {col_name} {col_def}")
            except sqlite3.OperationalError:
                pass

    conn.commit()
    conn.close()


# ---------- 辅助函数 ----------

def novel_row_to_dict(row) -> dict:
    keys = row.keys() if hasattr(row, 'keys') else []
    def _get(key, default=''):
        try:
            return row[key]
        except (IndexError, KeyError):
            return default
    return {
        "id": _get("id"),
        "title": _get("title"),
        "title_mode": _get("title_mode", "auto"),
        "outline": _get("outline"),
        "world_building": _get("world_building"),
        "character_profiles": _get("character_profiles"),
        "words_per_chapter": _get("words_per_chapter", 3000),
        "duplicate_check_interval": _get("duplicate_check_interval", 3),
        "summary_chapters_count": _get("summary_chapters_count", 3),
        "style_reference": _get("style_reference"),
        "expected_chapters": _get("expected_chapters", 0),
        "max_tokens": _get("max_tokens", 16384),
        "created_at": _get("created_at"),
        "updated_at": _get("updated_at"),
    }


def chapter_row_to_dict(row) -> dict:
    def _get(key, default=''):
        try:
            return row[key]
        except (IndexError, KeyError):
            return default
    return {
        "id": _get("id"),
        "novel_id": _get("novel_id"),
        "number": _get("number", 0),
        "title": _get("title"),
        "content": _get("content"),
        "status": _get("status", "draft"),
        "words_count": _get("words_count", 0),
        "embedding_json": _get("embedding_json"),
        "created_at": _get("created_at"),
        "updated_at": _get("updated_at"),
    }


def relationship_row_to_dict(row) -> dict:
    def _get(key, default=''):
        try:
            return row[key]
        except (IndexError, KeyError):
            return default
    return {
        "id": _get("id"),
        "novel_id": _get("novel_id"),
        "character_a": _get("character_a"),
        "character_b": _get("character_b"),
        "relation_type": _get("relation_type", "待定义"),
        "description": _get("description"),
        "created_at": _get("created_at"),
        "updated_at": _get("updated_at"),
    }


def character_row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "novel_id": row["novel_id"],
        "name": row["name"],
        "profile": row["profile"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def wiki_entry_row_to_dict(row) -> dict:
    def _get(key, default=''):
        try:
            return row[key]
        except (IndexError, KeyError):
            return default
    return {
        "id": _get("id"),
        "novel_id": _get("novel_id"),
        "category": _get("category"),
        "name": _get("name"),
        "description": _get("description"),
        "metadata": _get("metadata"),
        "sort_order": _get("sort_order", 0),
        "created_at": _get("created_at"),
        "updated_at": _get("updated_at"),
    }


def pending_change_row_to_dict(row) -> dict:
    def _get(key, default=''):
        try:
            return row[key]
        except (IndexError, KeyError):
            return default
    return {
        "id": _get("id"),
        "novel_id": _get("novel_id"),
        "chapter_number": _get("chapter_number", 0),
        "tool_name": _get("tool_name"),
        "target_name": _get("target_name"),
        "old_content": _get("old_content"),
        "new_content": _get("new_content"),
        "change_summary": _get("change_summary"),
        "status": _get("status", "pending"),
        "created_at": _get("created_at"),
    }