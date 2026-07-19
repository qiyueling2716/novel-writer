"""
导出服务 — 支持 TXT / HTML / Markdown 导出
- content_only 模式：仅导出正文，章节间用清晰分隔符标注，便于小说软件分章导入
- full 模式：导出大纲、世界观、人物画像 + 正文
- 章节标题格式：第X章 标题（X 为中文数字，如 第一章、第十二章）
- 封面图片：生成时已下载到本地 static/covers/，导出时复制到导出目录，HTML/MD 引用相对路径
"""
import html
import re
import shutil
from datetime import datetime
from pathlib import Path

from config import DEFAULT_EXPORT_DIR, COVERS_DIR


# 中文数字映射（1-99 足够，超过 99 章的小说极少）
_CN_NUMS = "零一二三四五六七八九"
_TENS = ["", "十", "二十", "三十", "四十", "五十", "六十", "七十", "八十", "九十"]


def _num_to_chinese(n: int) -> str:
    """将阿拉伯数字转换为中文数字（1-99）"""
    if n <= 0:
        return str(n)
    if n < 10:
        return _CN_NUMS[n]
    if n < 100:
        ten = n // 10
        unit = n % 10
        if unit == 0:
            return _TENS[ten]
        if ten == 1:
            return "十" + _CN_NUMS[unit]  # 十一、十二...
        return _TENS[ten] + _CN_NUMS[unit]  # 二十一、二十二...
    # 超过 99 直接用阿拉伯数字
    return str(n)


def _chapter_title(ch: dict) -> str:
    """构造章节标题：第X章 标题

    优先使用章节的 number 字段转中文，如 第一章 测试
    如果 number 不存在，则直接用 title
    如果 title 已经是 "第X章 ..." 格式，不重复添加
    """
    title = (ch.get("title") or "").strip()
    number = ch.get("number")
    if not number:
        return title or "未命名章节"
    # 如果标题已经是 "第X章" 开头，不重复添加
    if title and re.match(r'^第[一二三四五六七八九十百零\d]+章', title):
        return title
    prefix = f"第{_num_to_chinese(int(number))}章"
    return f"{prefix} {title}" if title else prefix


def _sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符"""
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def _prepare_cover_for_export(novel_id: str, export_dir: Path, novel_title: str) -> str:
    """准备封面图片用于导出。

    封面文件名固定为 novel_{novel_id}.png，存放在 static/covers/ 目录。
    导出时复制到导出目录，返回相对路径。
    返回空字符串表示无封面。

    :param novel_id: 小说 ID
    :param export_dir: 导出文件所在目录
    :param novel_title: 小说标题（用于命名封面文件）
    :return: 导出文件中引用的路径（相对路径）
    """
    if not novel_id:
        return ""

    # 封面文件名固定为 novel_{novel_id}.png
    local_file = COVERS_DIR / f"novel_{_sanitize_filename(novel_id)}.png"
    if not local_file.exists():
        return ""

    # 复制到导出目录，文件名用小说标题
    cover_filename = f"{_sanitize_filename(novel_title)}_cover.png"
    dest = export_dir / cover_filename
    try:
        shutil.copy2(local_file, dest)
        # 返回相对路径（HTML/MD 中用相对路径引用，确保移动文件夹后仍可用）
        return cover_filename
    except Exception as e:
        import logging
        logging.warning(f"复制封面到导出目录失败: {e}")
        return ""


def _get_export_path(novel_title: str, fmt: str, custom_path: str = "") -> Path:
    """确定导出路径"""
    if custom_path:
        path = Path(custom_path).resolve()
        # Security: 使用 is_relative_to 替代 startswith 防止路径穿越
        allowed_dirs = [DEFAULT_EXPORT_DIR.resolve()]
        if not any(path.is_relative_to(d) for d in allowed_dirs):
            raise ValueError("非法导出路径，仅允许导出到默认导出目录")
        if path.is_dir():
            filename = f"{_sanitize_filename(novel_title)}.{fmt}"
            path = path / filename
        return path
    else:
        DEFAULT_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{_sanitize_filename(novel_title)}.{fmt}"
        return DEFAULT_EXPORT_DIR / filename


# ==================== TXT 导出 ====================

def export_txt(novel: dict, chapters: list[dict], custom_path: str = "",
               include_meta: bool = True) -> str:
    """导出为 TXT 文件

    include_meta=True: 包含大纲、世界观、人物画像
    include_meta=False: 仅正文，章节间用分隔符标注，便于小说软件分章导入
    """
    path = _get_export_path(novel["title"] or "未命名小说", "txt", custom_path)

    lines = []

    if include_meta:
        lines.append(f"《{novel['title'] or '未命名小说'}》")
        lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        # 封面：查找本地封面文件，复制到导出目录
        cover_ref = _prepare_cover_for_export(novel.get("id", ""), path.parent, novel['title'] or '未命名小说')
        if cover_ref:
            lines.append(f"封面: {cover_ref}")
        lines.append("=" * 60)
        lines.append("")

        if novel.get("outline"):
            lines.append("【大纲】")
            lines.append(novel["outline"])
            lines.append("")

        if novel.get("world_building"):
            lines.append("【世界观设定】")
            lines.append(novel["world_building"])
            lines.append("")

        if novel.get("character_profiles"):
            lines.append("【人物画像】")
            lines.append(novel["character_profiles"])
            lines.append("")

        if novel.get("style_reference"):
            lines.append("【文风参考】")
            lines.append(novel["style_reference"])
            lines.append("")

        lines.append("=" * 60)
        lines.append("")
        lines.append("【正文】")
        lines.append("")

    for ch in chapters:
        # 章节标题行 — 格式：第X章 标题（如 第一章 测试）
        # 小说软件通常以此识别章节
        lines.append(_chapter_title(ch))
        lines.append("")
        lines.append(ch["content"])
        # 章节间用空行分隔
        lines.append("")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


# ==================== HTML 导出 ====================

def export_html(novel: dict, chapters: list[dict], custom_path: str = "",
                include_meta: bool = True) -> str:
    """导出为 HTML 文件"""
    path = _get_export_path(novel["title"] or "未命名小说", "html", custom_path)

    title_esc = html.escape(novel['title'] or '未命名小说')

    # 封面图片：查找本地封面文件，复制到导出目录
    cover_html = ""
    cover_ref = _prepare_cover_for_export(novel.get("id", ""), path.parent, novel['title'] or '未命名小说')
    if cover_ref:
        cover_html = f'<div class="cover"><img src="{html.escape(cover_ref)}" alt="封面"></div>'

    meta_html = ""
    if include_meta:
        if novel.get("outline"):
            meta_html += f'<section class="meta-section"><h2>大纲</h2><div class="meta-content">{html.escape(novel["outline"]).replace(chr(10), "<br>")}</div></section>'
        if novel.get("world_building"):
            meta_html += f'<section class="meta-section"><h2>世界观设定</h2><div class="meta-content">{html.escape(novel["world_building"]).replace(chr(10), "<br>")}</div></section>'
        if novel.get("character_profiles"):
            meta_html += f'<section class="meta-section"><h2>人物画像</h2><div class="meta-content">{html.escape(novel["character_profiles"]).replace(chr(10), "<br>")}</div></section>'
        if novel.get("style_reference"):
            meta_html += f'<section class="meta-section"><h2>文风参考</h2><div class="meta-content">{html.escape(novel["style_reference"]).replace(chr(10), "<br>")}</div></section>'
        if meta_html:
            meta_html = '<hr class="divider">' + meta_html + '<hr class="divider">'

    chapters_html = ""
    for ch in chapters:
        title_esc = html.escape(_chapter_title(ch))
        content_esc = html.escape(ch["content"]).replace("\n", "<br>")
        chapters_html += f"""
        <section class="chapter">
            <h2>{title_esc}</h2>
            <p>{content_esc}</p>
        </section>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>《{title_esc}》</title>
    <style>
        body {{ font-family: "Noto Serif CJK SC", "SimSun", serif; max-width: 800px; margin: 0 auto; padding: 40px 20px; line-height: 2; color: #333; }}
        h1 {{ text-align: center; font-size: 2em; margin-bottom: 40px; }}
        h2 {{ font-size: 1.4em; margin-top: 40px; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
        p {{ text-indent: 2em; margin: 0.5em 0; }}
        .meta {{ color: #999; font-size: 0.85em; text-align: center; margin-bottom: 30px; }}
        .divider {{ border: none; border-top: 2px solid #ccc; margin: 40px 0; }}
        .meta-section {{ margin: 20px 0; }}
        .meta-content {{ font-size: 0.9em; color: #666; line-height: 1.8; }}
        .cover {{ text-align: center; margin: 30px 0; }}
        .cover img {{ max-width: 100%; max-height: 500px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
        @media (max-width: 600px) {{ body {{ padding: 20px 12px; font-size: 0.95em; }} }}
    </style>
</head>
<body>
    <h1>《{title_esc}》</h1>
    <div class="meta">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
    {cover_html}
    {meta_html}
    {chapters_html}
</body>
</html>"""

    path.write_text(html_content, encoding="utf-8")
    return str(path)


# ==================== Markdown 导出 ====================

def export_markdown(novel: dict, chapters: list[dict], custom_path: str = "",
                    include_meta: bool = True) -> str:
    """导出为 Markdown 文件"""
    path = _get_export_path(novel["title"] or "未命名小说", "md", custom_path)

    lines = []
    lines.append(f"# 《{novel['title'] or '未命名小说'}》")
    lines.append(f"\n> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 封面图片：查找本地封面文件，复制到导出目录
    cover_ref = _prepare_cover_for_export(novel.get("id", ""), path.parent, novel['title'] or '未命名小说')
    if cover_ref:
        lines.append(f"![封面]({cover_ref})")
        lines.append("")

    if include_meta:
        if novel.get("outline"):
            lines.append("## 大纲\n")
            lines.append(novel["outline"])
            lines.append("")

        if novel.get("world_building"):
            lines.append("## 世界观设定\n")
            lines.append(novel["world_building"])
            lines.append("")

        if novel.get("character_profiles"):
            lines.append("## 人物画像\n")
            lines.append(novel["character_profiles"])
            lines.append("")

        if novel.get("style_reference"):
            lines.append("## 文风参考\n")
            lines.append(novel["style_reference"])
            lines.append("")

        lines.append("---\n")

    for ch in chapters:
        lines.append(f"## {_chapter_title(ch)}\n")
        lines.append(ch["content"])
        lines.append("")
        lines.append("---")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


EXPORTERS = {
    "txt": export_txt,
    "html": export_html,
    "md": export_markdown,
}


def _cleanup_old_exports(max_age_hours: int = 24):
    """清理超过 max_age_hours 小时的旧导出文件"""
    import time
    cutoff = time.time() - max_age_hours * 3600
    if not DEFAULT_EXPORT_DIR.exists():
        return
    for f in DEFAULT_EXPORT_DIR.iterdir():
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


def export_novel(novel: dict, chapters: list[dict], fmt: str = "txt",
                 custom_path: str = "", include_meta: bool = True) -> str:
    """
    导出小说
    :param novel: 小说信息
    :param chapters: 章节列表
    :param fmt: 格式 (txt/html/md)
    :param custom_path: 自定义路径（目录或文件路径）
    :param include_meta: True=包含设定(大纲/世界观/人物)，False=仅正文内容
    :return: 导出后的文件路径
    """
    exporter = EXPORTERS.get(fmt)
    if not exporter:
        raise ValueError(f"不支持的导出格式: {fmt}，支持: {list(EXPORTERS.keys())}")
    # 每次导出时清理旧文件
    _cleanup_old_exports()
    return exporter(novel, chapters, custom_path, include_meta=include_meta)
