#!/usr/bin/env python3
"""
Markdown 文档 → 知识库 SQLite 全流程脚本
===========================================

完整复刻 OpenBidKit 的文档切片拆分逻辑：

  阶段一：读取 Markdown
  阶段二：createRawBlocks() —— 按标题/空行/内容类型切分为原始块
  阶段三：mergeSemanticBlocks() —— 语义合并碎片块（目标 500 字符）
  阶段四：filterBlocks() —— 过滤无意义块（页码/目录/封面/签章/重复/过短）
  阶段五（可选）：AI 条目提取 + 段落匹配 + 补漏
  阶段六：写入 SQLite

用法：
  python md_to_knowledge_base.py input.md -o output.sqlite

  # 启用 AI 提取（需要 OPENAI_API_KEY 或兼容的 API）
  python md_to_knowledge_base.py input.md --ai --api-key sk-ws-H.RYMPPRP.s2mR.MEUCIEBWxef1mkhNiLiVkckHvIi6InH8jAXmUGmcGpUxU0zOAiEA6hAVS8foi-Ch4ADanf5N4i3KJTG3qx1r1xF-n0yNnUw --model gpt-4o

  # 使用自定义 API 地址
  python md_to_knowledge_base.py input.md --ai --api-base https://your-api.com/v1

依赖：
  pip install openai  # 仅 --ai 模式需要
"""


import argparse
import json
import os
import re
import sqlite3
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone


# ============================================================================
# 配置常量（对齐原 JS 实现）
# ============================================================================

OVERSIZED_BLOCK_CHARS = 8000          # 单块最大字符数
SEMANTIC_MERGE_TARGET_CHARS = 500     # 语义合并目标大小
RECOVERY_MAX_ATTEMPTS = 2             # AI 补漏最大轮次
DEFAULT_BATCH_SIZE = 20               # AI 分批匹配粒度
DEFAULT_AI_TEMPERATURE = 0.1          # AI 匹配/补漏温度
EXTRACT_AI_TEMPERATURE = 0.2          # AI 提取温度


# ============================================================================
# 工具函数
# ============================================================================

def now():
    return datetime.now(timezone.utc).isoformat()

def create_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"

def safe_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1F]+', '_', str(name or '未命名')).strip() or '未命名'

def get_content_char_count(text: str) -> int:
    """去除空格后的字符数"""
    return len(re.sub(r'\s+', '', str(text or '')))

def strip_markdown_fence(content: str) -> str:
    """剥除外层 ```markdown ``` 包裹"""
    content = str(content or '')
    content = re.sub(r'^```[\s\S]*?\n', '', content)
    content = re.sub(r'```$', '', content)
    return content.strip()

def split_oversized_text(text: str, limit: int) -> list:
    """按句子边界拆分超大文本"""
    parts = []
    buffer = ''
    sentences = re.split(r'(?<=[。！？!?；;])\s*', str(text or ''))
    for sentence in sentences:
        if not sentence:
            continue
        if buffer and len(buffer) + len(sentence) > limit:
            parts.append(buffer.strip())
            buffer = ''
        buffer += sentence
    if buffer.strip():
        parts.append(buffer.strip())
    return parts if parts else [str(text or '')]


# ============================================================================
# 块过滤辅助判断函数
# ============================================================================

def normalize_repeated_text(text: str) -> str:
    """规范化文本用于重复检测"""
    result = str(text or '')
    result = re.sub(r'^#+\s*', '', result)
    result = re.sub(r'\s+', '', result)
    result = re.sub(r'[\-—_·.。:：|第页共]', '', result)
    return result.strip().lower()

def is_page_number_block(text: str) -> bool:
    """是否为页码块"""
    normalized = str(text or '').strip()
    compact = re.sub(r'\s+', '', normalized)
    if re.match(r'^[-—_]*\d+[-—_]*$', compact):
        return True
    if re.match(r'^第\d+页(共\d+页)?$', compact):
        return True
    if re.match(r'^\d+/\d+$', compact):
        return True
    if re.match(r'^page\d+(of\d+)?$', compact, re.IGNORECASE):
        return True
    return False

def is_catalog_block(text: str) -> bool:
    """是否为目录块"""
    normalized = str(text or '').strip()
    compact = re.sub(r'\s+', '', normalized)
    if re.match(r'^(#+)?(目录|目次|contents)$', compact, re.IGNORECASE):
        return True

    lines = [line.strip() for line in normalized.split('\n') if line.strip()]
    if len(lines) < 2:
        return False

    catalog_line_pattern = re.compile(r'(?:\.{2,}|…{2,}|·{2,}|\s{4,})\s*\d+\s*$')
    catalog_lines = [line for line in lines if catalog_line_pattern.search(line)]
    return len(catalog_lines) >= int(len(lines) * 0.6 + 0.5)

def is_cover_block(text: str, index: int) -> bool:
    """是否为封面块"""
    if index > 12:
        return False

    normalized = str(text or '').strip()
    compact = re.sub(r'\s+', '', normalized)
    if not compact or len(compact) > 220:
        return False

    cover_markers = ['投标文件', '投标书', '正本', '副本', '项目名称', '招标编号',
                     '投标人', '编制日期', '日期：', '日期:']
    has_marker = any(marker in compact for marker in cover_markers)
    has_long_sentence = bool(re.search(r'[。！？；]', normalized)) and len(normalized) > 80
    return has_marker and not has_long_sentence

def is_signature_block(text: str) -> bool:
    """是否为签章块"""
    normalized = str(text or '').strip()
    compact = re.sub(r'\s+', '', normalized)
    if not compact or len(compact) > 260:
        return False
    # 排除"签字确认"等有意义的内容
    if re.search(r'(签字确认|用户签字|双方责任人.{0,12}签字)', compact):
        return False
    has_keyword = re.search(
        r'(盖章|签章|签名|法定代表人|授权代表|委托代理人|被授权人|年月日|投标人代表签字|代表签字)',
        compact
    )
    has_long_sentence = bool(re.search(r'[。！？；].{20,}', normalized))
    return bool(has_keyword) and not has_long_sentence

def strip_bold_marker(text: str) -> str:
    """去除 **粗体** 标记"""
    result = str(text or '').strip()
    m = re.match(r'^\*\*(.+)\*\*$', result)
    if m:
        return m.group(1).strip()
    return result

def is_table_block(block: dict) -> bool:
    """是否为表格块（兼容 HTML <table> 和 Markdown pipe table 两种格式）"""
    content = str(block.get('content', '')).strip()
    # HTML 表格格式（原项目 convert.mjs 输出格式）
    if re.match(r'^<table[\s>]', content, re.IGNORECASE):
        return True
    # Markdown pipe table 格式（直接输入的 .md 文件）
    lines = content.split('\n')
    # 至少需要 2 行：表头行 + 分隔行
    pipe_lines = [l for l in lines if re.match(r'^\s*\|.*\|\s*$', l)]
    if len(pipe_lines) >= 2:
        # 检查是否存在分隔行（如 |---|---|）
        has_separator = any(re.match(r'^\s*\|[\s\-:]+\|', l) for l in pipe_lines)
        if has_separator:
            return True
    return False

def is_semantic_heading_block(block: dict) -> bool:
    """判断块是否为语义标题（非 Markdown # 标题，而是加粗/编号等表示的标题）"""
    original = str(block.get('content', '')).strip()
    normalized = strip_bold_marker(original)
    compact_length = get_content_char_count(normalized)
    if not normalized or compact_length > 100:
        return False
    if re.search(r'[。！？；;]$', normalized):
        return False

    # 加粗文本
    if re.match(r'^\*\*.+\*\*$', original):
        return True
    # 数字编号：1.2.3 xxx
    if re.match(r'^\d+(?:\.\d+)+\s*[^。！？；;]{1,80}$', normalized):
        return True
    # 数字编号：1. xxx
    if re.match(r'^\d+\.\s*[^。！？；;]{1,80}$', normalized):
        return True
    # 中文数字：一、xxx
    if re.match(r'^[一二三四五六七八九十]+[、.．]\s*[^。！？；;]{1,80}$', normalized):
        return True
    # 圈号：①xxx
    if re.match(r'^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳][、.．]?\s*[^。！？；;]{1,80}$', normalized):
        return True
    # 括号中文数字：（一）xxx
    if re.match(r'^（[一二三四五六七八九十]+）\s*[^。！？；;]{1,80}$', normalized):
        return True
    # 第X章/节/部分
    if re.match(r'^第[一二三四五六七八九十\d]+[章节部分篇]\s*[^。！？；;]{0,80}$', normalized):
        return True
    return False


# ============================================================================
# 阶段二：创建原始块 (createRawBlocks)
# ============================================================================

def create_raw_blocks(markdown: str) -> list:
    """
    按 Markdown 结构逐行扫描切分为原始块。
    切分边界：标题行 / 空行 / 内容类型变化(table/list/paragraph)。
    单块超过 OVERSIZED_BLOCK_CHARS 时按句子二次拆分。
    """
    blocks = []
    lines = str(markdown or '').split('\n')
    buffer = []
    current_type = 'paragraph'
    headings = []

    def push_buffer():
        nonlocal buffer, current_type
        content = '\n'.join(buffer).strip()
        if not content:
            buffer = []
            return

        limit = int(OVERSIZED_BLOCK_CHARS * 0.75)
        chunks = split_oversized_text(content, limit) if len(content) > OVERSIZED_BLOCK_CHARS else [content]
        for chunk in chunks:
            blocks.append({
                'id': f'R{len(blocks) + 1:06d}',
                'type': current_type,
                'heading_path': [h for h in headings if h],
                'content': chunk,
            })
        buffer = []

    for line in lines:
        # 检测 Markdown 标题
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if heading_match:
            push_buffer()
            level = len(heading_match.group(1))
            # 调整 headings 数组长度以匹配标题层级
            while len(headings) < level:
                headings.append('')
            headings[level - 1] = heading_match.group(2).strip()
            # 清除更深层级的 heading
            headings[level:] = []
            current_type = 'heading'
            buffer = [line]
            push_buffer()
            current_type = 'paragraph'
            continue

        trimmed = line.strip()
        if not trimmed:
            push_buffer()
            current_type = 'paragraph'
            continue

        # 判断行类型
        if re.match(r'^\s*\|.*\|\s*$', line):
            next_type = 'table'
        elif re.match(r'^\s*(?:[-*+]\s+|\d+[.)、]\s+)', line):
            next_type = 'list'
        else:
            next_type = 'paragraph'

        # 类型变化时刷新缓冲区（paragraph 之间不刷新）
        if buffer and current_type != next_type and (current_type != 'paragraph' or next_type != 'paragraph'):
            push_buffer()
        current_type = next_type
        buffer.append(line)

    push_buffer()
    return blocks


# ============================================================================
# 阶段三：语义合并 (mergeSemanticBlocks)
# ============================================================================

def merge_semantic_blocks(raw_blocks: list) -> list:
    """
    将碎片化的原始块按语义规则合并。
    目标大小：SEMANTIC_MERGE_TARGET_CHARS (500) 字符。
    - 表格始终独立成块
    - 标题块先缓冲，遇到正文后再决定是否合并
    - 段落块持续累积到目标大小
    """
    merged = []
    buffer = []

    def buffer_text():
        return '\n\n'.join(b['content'] for b in buffer)

    def buffer_has_only_headings():
        return len(buffer) > 0 and all(is_semantic_heading_block(b) for b in buffer)

    def flush_buffer():
        nonlocal buffer
        if not buffer:
            return
        merged.append({
            **buffer[0],
            'id': f'R{len(merged) + 1:06d}',
            'type': 'list' if any(b['type'] == 'list' for b in buffer) else 'paragraph',
            'content': buffer_text().strip(),
        })
        buffer = []

    def push_standalone(block):
        merged.append({
            **block,
            'id': f'R{len(merged) + 1:06d}',
        })

    for block in raw_blocks:
        if is_table_block(block):
            flush_buffer()
            push_standalone(block)
            continue

        if is_semantic_heading_block(block):
            if buffer and not buffer_has_only_headings() and get_content_char_count(buffer_text()) >= 100:
                flush_buffer()
            buffer.append(block)
            continue

        block_chars = get_content_char_count(block['content'])
        if not buffer and block_chars >= SEMANTIC_MERGE_TARGET_CHARS:
            push_standalone(block)
            continue

        buffer.append(block)
        if get_content_char_count(buffer_text()) >= SEMANTIC_MERGE_TARGET_CHARS:
            flush_buffer()

    flush_buffer()
    return merged


# ============================================================================
# 阶段四：块过滤 (filterBlocks)
# ============================================================================

def filter_blocks(raw_blocks: list) -> dict:
    """
    过滤无意义块。
    返回 {'blocks': 有效块列表, 'filtered_blocks': 筛除块列表}。
    """
    # 统计重复文本（用于页眉页脚检测）
    repeated_counts = Counter()
    for block in raw_blocks:
        key = normalize_repeated_text(block['content'])
        if key and len(key) <= 80:
            repeated_counts[key] += 1

    kept = []
    filtered = []

    for index, block in enumerate(raw_blocks):
        repeated_key = normalize_repeated_text(block['content'])
        repeated = repeated_key and len(repeated_key) <= 80 and repeated_counts.get(repeated_key, 0) >= 3

        # 按优先级判断过滤原因
        content = str(block.get('content', ''))
        if not content.strip():
            reason = 'empty'
        elif is_page_number_block(content):
            reason = 'page_number'
        elif get_content_char_count(content) < 100:
            reason = 'too_short'
        elif is_catalog_block(content):
            reason = 'catalog'
        elif repeated:
            reason = 'repeated_header_footer'
        elif is_cover_block(content, index):
            reason = 'cover'
        elif is_signature_block(content):
            reason = 'signature_page'
        else:
            reason = ''

        if reason:
            filtered.append({**block, 'reason': reason})
        else:
            kept.append({
                **block,
                'id': f'P{len(kept) + 1:06d}',
            })

    return {'blocks': kept, 'filtered_blocks': filtered}


# ============================================================================
# 渲染块为 AI prompt 格式
# ============================================================================

def render_blocks_for_prompt(blocks: list) -> str:
    """将块列表渲染为 AI 可读的文本格式"""
    parts = []
    for block in blocks:
        heading_path = ' > '.join(block['heading_path']) if block.get('heading_path') else '无'
        parts.append('\n'.join([
            f"[{block['id']}]",
            f"type: {block['type']}",
            f"heading_path: {heading_path}",
            'text:',
            block['content'],
        ]))
    return '\n\n'.join(parts)


# ============================================================================
# AI 相关函数（可选阶段五）
# ============================================================================

def build_initial_item_messages(document_name: str, block_text: str) -> list:
    """构建首轮条目提取的 messages"""
    return [
        {'role': 'user', 'content': (
            '以下是同一份文档的完整 block 列表。\n'
            '<document_blocks>\n'
            f'{block_text}\n'
            '</document_blocks>'
        )},
        {'role': 'user', 'content': (
            f'文档名：{document_name}\n'
            '你是投标资料知识库分析助手。你只负责从历史投标资料中提取对后续编写标书有复用价值的知识条目。\n'
            '任务：请从全文中提取有意义的知识条目数组。条目应覆盖技术方案、项目管理、质量、安全、进度、服务、应急、人员设备、类似业绩等可复用内容。\n'
            '只返回 JSON：{"items":[{"title":"","summary":""}]}\n'
            '要求：title 简洁明确；summary 说明该条目可如何用于编写投标文件；不要输出 id、content、段落编号、Markdown 或解释文字。'
        )},
    ]

def build_supplement_item_messages(document_name: str, block_text: str, first_items: list) -> list:
    """构建补充条目提取的 messages"""
    return [
        {'role': 'user', 'content': (
            '以下是同一份文档的完整 block 列表。\n'
            '<document_blocks>\n'
            f'{block_text}\n'
            '</document_blocks>'
        )},
        {'role': 'user', 'content': (
            f'文档名：{document_name}\n'
            '你是投标资料知识库补漏助手。你只判断已有知识条目是否遗漏了重要主题，并补充缺失条目。\n'
            '任务：请检查第一轮条目是否遗漏了有复用价值的重要内容。如果有遗漏，只输出新增条目；如果没有遗漏，返回空 items 数组。\n'
            '只返回 JSON：{"items":[{"title":"","summary":""}]}\n'
            '如果没有新增条目，必须返回 {"items":[]}，这属于正常结果。\n'
            '不要重复已有条目，不要输出 id、content、段落编号、Markdown 或解释文字。\n\n'
            '<first_round_items>\n'
            f'{json.dumps([{"title": i["title"], "summary": i["summary"]} for i in first_items], ensure_ascii=False, indent=2)}\n'
            '</first_round_items>'
        )},
    ]

def build_match_messages(document_name: str, block_text: str, batch_items: list) -> list:
    """构建分批匹配的 messages"""
    task_prompt = (
        f'文档名：{document_name}\n'
        '你是投标知识库段落匹配助手。你只根据知识条目的标题和摘要，为其匹配强相关 block 范围。\n'
        '你将收到同一份文档的完整 block 列表，以及本次需要匹配的一小批知识条目。\n'
        '规则：\n'
        '1. 只处理本次给出的知识条目。\n'
        '2. 只匹配与条目强相关、可直接支撑该条目的 block。\n'
        '3. 如果某些 block 更可能属于其他未提供的条目，不要强行匹配。\n'
        '4. 只返回 id 和 ranges，不要输出正文，不要解释。\n'
        '5. ranges 使用闭区间：["P000001","P000003"] 表示连续 block；单个 block 写成 ["P000001","P000001"]。\n'
        '6. 只允许使用输入中存在的 block 编号和本批条目 id。\n'
        '输出 JSON：{"matches":[{"id":"K000001","ranges":[["P000001","P000003"]]}]}\n\n'
        '以下是本次需要匹配的知识条目。只处理这些条目：\n'
        f'{json.dumps([{"id": i["id"], "title": i["title"], "summary": i["summary"]} for i in batch_items], ensure_ascii=False, indent=2)}'
    )
    return [
        {'role': 'user', 'content': (
            '以下是同一份文档的完整 block 列表。\n'
            '<document_blocks>\n'
            f'{block_text}\n'
            '</document_blocks>'
        )},
        {'role': 'user', 'content': task_prompt},
    ]

def build_recovery_messages(document_name: str, items: list, missing_blocks: list) -> list:
    """构建补漏 messages"""
    missing_text = render_blocks_for_prompt(missing_blocks)
    items_json = json.dumps(
        [{'id': i['id'], 'title': i['title'], 'summary': i['summary']} for i in items],
        ensure_ascii=False, indent=2
    )
    return [
        {'role': 'user', 'content': (
            '以下是当前尚未处理的遗漏 block。\n'
            '<missing_blocks>\n'
            f'{missing_text}\n'
            '</missing_blocks>'
        )},
        {'role': 'user', 'content': (
            f'文档名：{document_name}\n'
            '你是投标知识库遗漏段落补漏助手。必须把所有收到的遗漏 block 明确归入已有条目、新增条目或舍弃段落。\n'
            '任务：必须覆盖所有遗漏 block。每个遗漏 block 只能进入以下三类之一：\n'
            '1. matches：归入已有知识条目，只返回已有 id 和 ranges。\n'
            '2. new_items：如果没有合适的已有条目但内容有复用价值，则新增知识条目，并给出 title、summary、ranges。\n'
            '3. discarded：如果内容质量低、重复、格式残留或无投标复用价值，则推荐舍弃，并给出 reason。\n'
            '输出 JSON：{"matches":[{"id":"K000001","ranges":[["P000001","P000003"]]}],"new_items":[{"title":"","summary":"","ranges":[["P000004","P000005"]]}],"discarded":[{"ranges":[["P000006","P000006"]],"reason":""}]}\n'
            '不要输出正文、Markdown 或解释文字。\n\n'
            '<knowledge_items>\n'
            f'{items_json}\n'
            '</knowledge_items>'
        )},
    ]


def get_block_order(blocks: list) -> dict:
    """建立 block_id → 索引的映射"""
    return {b['id']: i for i, b in enumerate(blocks)}

def normalize_range_pair(rng) -> tuple | None:
    """规范化为 (start, end) 对"""
    if isinstance(rng, list):
        start = str(rng[0] or '').strip()
        end = str(rng[1] or rng[0] or '').strip()
        return (start, end) if start else None
    rng_id = str(rng or '').strip()
    return (rng_id, rng_id) if rng_id else None

def normalize_ranges(ranges: list, block_order: dict) -> list:
    """规范化 ranges 列表并排序"""
    if not isinstance(ranges, list):
        return []
    normalized = []
    for rng in ranges:
        pair = normalize_range_pair(rng)
        if not pair:
            continue
        start, end = pair
        if start not in block_order or end not in block_order:
            continue
        if block_order[start] > block_order[end]:
            start, end = end, start
        normalized.append([start, end])
    return normalized

def expand_ranges(ranges: list, blocks: list, block_order: dict) -> list:
    """将 ranges 展开为 block_id 列表"""
    ids = []
    for start, end in ranges:
        start_idx = block_order.get(start)
        end_idx = block_order.get(end)
        if start_idx is None or end_idx is None:
            continue
        for i in range(start_idx, end_idx + 1):
            ids.append(blocks[i]['id'])
    return list(dict.fromkeys(ids))  # 去重保序

def normalize_match_result(parsed: dict, item_ids: set, blocks: list, block_order: dict) -> dict:
    """规范化 AI 匹配结果"""
    matches = parsed.get('matches', []) if isinstance(parsed, dict) else []
    result_matches = []
    for match in matches:
        mid = str(match.get('id', '') or '').strip()
        ranges = normalize_ranges(match.get('ranges', match.get('paragraph_ranges', match.get('block_ranges', []))), block_order)
        if mid in item_ids and ranges:
            result_matches.append({
                'id': mid,
                'ranges': ranges,
                'block_ids': expand_ranges(ranges, blocks, block_order),
            })
    return {'matches': result_matches}

def normalize_recovery_result(parsed: dict, item_ids: set, blocks: list, block_order: dict) -> dict:
    """规范化 AI 补漏结果"""
    matches_raw = parsed.get('matches', []) if isinstance(parsed, dict) else []
    new_items_raw = parsed.get('new_items', []) if isinstance(parsed, dict) else []
    discarded_raw = parsed.get('discarded', []) if isinstance(parsed, dict) else []

    matches = []
    for m in matches_raw:
        mid = str(m.get('id', '') or '').strip()
        ranges = normalize_ranges(m.get('ranges', []), block_order)
        if mid in item_ids and ranges:
            matches.append({'id': mid, 'ranges': ranges, 'block_ids': expand_ranges(ranges, blocks, block_order)})

    new_items = []
    for item in new_items_raw:
        title = str(item.get('title', '') or '').strip()
        summary = str(item.get('summary', item.get('resume', '')) or '').strip()
        ranges = normalize_ranges(item.get('ranges', []), block_order)
        if title and summary and ranges:
            new_items.append({'title': title, 'summary': summary, 'ranges': ranges,
                              'block_ids': expand_ranges(ranges, blocks, block_order)})

    discarded = []
    for d in discarded_raw:
        ranges = normalize_ranges(d.get('ranges', []), block_order)
        if ranges:
            discarded.append({
                'ranges': ranges,
                'block_ids': expand_ranges(ranges, blocks, block_order),
                'reason': str(d.get('reason', 'AI 建议舍弃') or 'AI 建议舍弃').strip(),
            })

    return {'matches': matches, 'new_items': new_items, 'discarded': discarded}


def collect_handled_block_ids(matches: list, discarded: list, system_discarded: list) -> set:
    """收集已被处理的 block ID"""
    handled = set()
    for m in matches:
        handled.update(m.get('block_ids', []))
    for d in discarded:
        handled.update(d.get('block_ids', []))
    for sd in system_discarded:
        handled.update(sd.get('block_ids', []))
    return handled

def get_missing_blocks(blocks: list, matches: list, discarded: list, system_discarded: list) -> list:
    """获取未被处理的遗漏 block"""
    handled = collect_handled_block_ids(matches, discarded, system_discarded)
    return [b for b in blocks if b['id'] not in handled]

def next_knowledge_item_id(items: list) -> str:
    """生成下一个知识条目 ID"""
    max_n = 0
    for item in items:
        m = re.match(r'^K(\d+)$', item.get('id', '') or '')
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f'K{max_n + 1:06d}'

def merge_candidate_items(first_items: list, supplement_items: list) -> list:
    """合并去重 candidate items"""
    merged = []
    seen = set()
    for item in first_items + supplement_items:
        key = re.sub(r'\s+', '', item['title']).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append({
            'id': f'K{len(merged) + 1:06d}',
            'title': item['title'],
            'summary': item['summary'],
        })
    return merged

def create_final_items(items: list, matches: list, blocks: list, file_name: str) -> list:
    """将匹配的 block 拼接到条目中，生成最终知识条目"""
    block_map = {b['id']: b for b in blocks}
    blocks_by_item = {}
    for match in matches:
        current = blocks_by_item.get(match['id'], [])
        blocks_by_item[match['id']] = list(dict.fromkeys(current + match.get('block_ids', [])))

    final_items = []
    for item in items:
        source_ids = blocks_by_item.get(item['id'], [])
        content = '\n\n'.join(
            block_map.get(bid, {}).get('content', '') for bid in source_ids if block_map.get(bid, {}).get('content', '')
        ).strip()
        if content:
            final_items.append({
                'id': item['id'],
                'title': item['title'],
                'resume': item.get('summary', ''),
                'content': content,
                'source_block_ids': source_ids,
                'source_file': file_name,
            })
    return final_items

def create_report(blocks, filtered_blocks, candidate_items, final_items,
                  matches, discarded, system_discarded, recovery_attempts, batch_size) -> dict:
    """生成分析报告"""
    matched_ids = set()
    for m in matches:
        matched_ids.update(m.get('block_ids', []))
    discarded_ids = set()
    for d in discarded:
        discarded_ids.update(d.get('block_ids', []))
    system_ids = set()
    for sd in system_discarded:
        system_ids.update(sd.get('block_ids', []))
    handled = matched_ids | discarded_ids | system_ids
    total = len(blocks) or 1

    return {
        'total_blocks': len(blocks),
        'filtered_blocks_count': len(filtered_blocks),
        'candidate_items_count': len(candidate_items),
        'final_items_count': len(final_items),
        'matched_blocks_count': len(matched_ids),
        'discarded_blocks_count': len(discarded_ids),
        'system_discarded_after_retry_count': len(system_ids),
        'new_items_from_recovery_count': sum(len(a.get('new_items', [])) for a in recovery_attempts),
        'recovery_attempt_count': len(recovery_attempts),
        'batch_size': batch_size,
        'coverage_rate': round(len(handled) / total, 4),
        'matched_rate': round(len(matched_ids) / total, 4),
        'created_at': now(),
    }


# ============================================================================
# AI 客户端封装
# ============================================================================

class AIClient:
    """OpenAI 兼容的 AI 客户端"""

    def __init__(self, api_key: str, base_url: str = 'https://api.openai.com/v1', model: str = 'gpt-4o'):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def chat_json(self, messages: list, temperature: float = 0.1, label: str = '') -> dict:
        """发送 chat 请求并解析 JSON 返回"""
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError('请安装 openai 包：pip install openai')

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        label_prefix = f'[{label}] ' if label else ''
        print(f'{label_prefix}正在调用 AI ({self.model})...', file=sys.stderr)

        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            response_format={'type': 'json_object'},
        )
        content = response.choices[0].message.content.strip()
        print(f'{label_prefix}AI 返回 {len(content)} 字符', file=sys.stderr)

        # 尝试解析 JSON
        raw = content
        # 去除可能的 markdown fence
        raw = re.sub(r'^```(?:json)?\s*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        return json.loads(raw)


# ============================================================================
# 阶段五：AI 驱动的条目提取与匹配（可选）
# ============================================================================

def run_ai_pipeline(blocks: list, filtered_blocks: list, document_name: str,
                    ai: AIClient, batch_size: int = DEFAULT_BATCH_SIZE) -> dict:
    """
    执行完整的 AI 流水线：提取 → 匹配 → 补漏 → 生成条目
    返回 {'items': ..., 'matches': ..., 'discarded': ..., 'system_discarded': ...,
           'recovery_attempts': ..., 'report': ..., 'final_items': ...}
    """
    block_text = render_blocks_for_prompt(blocks)
    block_order = get_block_order(blocks)

    # ---- 首轮提取 ----
    print('=== 首轮提取知识条目 ===', file=sys.stderr)
    first_response = ai.chat_json(
        build_initial_item_messages(document_name, block_text),
        temperature=EXTRACT_AI_TEMPERATURE,
        label='首轮提取'
    )
    first_items = []
    items_raw = first_response.get('items', []) if isinstance(first_response, dict) else []
    for item in items_raw:
        title = str(item.get('title', '') or '').strip()
        summary = str(item.get('summary', item.get('resume', '')) or '').strip()
        if title and summary:
            first_items.append({'title': title, 'summary': summary})
    print(f'首轮提取：{len(first_items)} 条', file=sys.stderr)

    # ---- 补充提取 ----
    print('=== 补充提取知识条目 ===', file=sys.stderr)
    supplement_response = ai.chat_json(
        build_supplement_item_messages(document_name, block_text, first_items),
        temperature=EXTRACT_AI_TEMPERATURE,
        label='补充提取'
    )
    supplement_items = []
    items_raw = supplement_response.get('items', []) if isinstance(supplement_response, dict) else []
    for item in items_raw:
        title = str(item.get('title', '') or '').strip()
        summary = str(item.get('summary', item.get('resume', '')) or '').strip()
        if title and summary:
            supplement_items.append({'title': title, 'summary': summary})
    print(f'补充提取：{len(supplement_items)} 条', file=sys.stderr)

    # ---- 合并去重 ----
    candidate_items = merge_candidate_items(first_items, supplement_items)
    print(f'合并后：{len(candidate_items)} 条候选条目', file=sys.stderr)

    # ---- 分批匹配 ----
    candidate_ids = {i['id'] for i in candidate_items}
    batches = [candidate_items[i:i + batch_size] for i in range(0, len(candidate_items), batch_size)]
    print(f'=== 分批匹配：共 {len(batches)} 批 ===', file=sys.stderr)

    all_matches = []
    for idx, batch in enumerate(batches):
        batch_no = idx + 1
        print(f'  匹配第 {batch_no}/{len(batches)} 批 ({len(batch)} 条)', file=sys.stderr)
        resp = ai.chat_json(
            build_match_messages(document_name, block_text, batch),
            temperature=DEFAULT_AI_TEMPERATURE,
            label=f'匹配 batch_{batch_no}'
        )
        result = normalize_match_result(resp, candidate_ids, blocks, block_order)
        all_matches.extend(result['matches'])
        print(f'  第 {batch_no} 批匹配到 {len(result["matches"])} 条', file=sys.stderr)

    # ---- 补漏 ----
    print('=== 补漏遗漏段落 ===', file=sys.stderr)
    items = [*candidate_items]
    recovered_matches = [*all_matches]
    discarded = []
    system_discarded = []
    recovery_attempts = []

    for attempt in range(RECOVERY_MAX_ATTEMPTS):
        missing = get_missing_blocks(blocks, recovered_matches, discarded, system_discarded)
        print(f'  第 {attempt + 1} 轮：遗漏 {len(missing)} 个 block', file=sys.stderr)
        if not missing:
            break

        current_item_ids = {i['id'] for i in items}
        resp = ai.chat_json(
            build_recovery_messages(document_name, items, missing),
            temperature=DEFAULT_AI_TEMPERATURE,
            label=f'补漏 round_{attempt + 1}'
        )
        parsed = normalize_recovery_result(resp, current_item_ids, blocks, block_order)

        # 处理新增条目
        new_items_with_ids = []
        for ni in parsed['new_items']:
            nid = next_knowledge_item_id(items)
            items.append({'id': nid, 'title': ni['title'], 'summary': ni['summary']})
            recovered_matches.append({'id': nid, 'ranges': ni['ranges'], 'block_ids': ni['block_ids']})
            new_items_with_ids.append({**ni, 'id': nid})

        recovered_matches.extend(parsed['matches'])
        for d in parsed['discarded']:
            d['source'] = f'recovery_{attempt + 1}'
        discarded.extend(parsed['discarded'])

        recovery_attempts.append({
            'attempt': attempt + 1,
            'missing_before_count': len(missing),
            'matches': parsed['matches'],
            'new_items': new_items_with_ids,
            'discarded': parsed['discarded'],
        })
        print(f'  第 {attempt + 1} 轮：新增 {len(parsed["new_items"])} 条，归入 {len(parsed["matches"])} 条，舍弃 {len(parsed["discarded"])} 组',
              file=sys.stderr)

    # ---- 系统舍弃剩余 ----
    remaining = get_missing_blocks(blocks, recovered_matches, discarded, system_discarded)
    print(f'补漏后剩余未覆盖：{len(remaining)} 个 block', file=sys.stderr)
    if remaining:
        system_discarded.append({
            'block_ids': [b['id'] for b in remaining],
            'reason': 'system_discarded_after_retry',
        })

    # ---- 生成最终条目 ----
    final_items = create_final_items(items, recovered_matches, blocks, document_name)
    report = create_report(
        blocks, filtered_blocks, items, final_items,
        recovered_matches, discarded, system_discarded,
        recovery_attempts, batch_size
    )

    return {
        'items': items,
        'matches': recovered_matches,
        'discarded': discarded,
        'system_discarded': system_discarded,
        'recovery_attempts': recovery_attempts,
        'report': report,
        'final_items': final_items,
    }


# ============================================================================
# 阶段六：SQLite 存储
# ============================================================================

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS knowledge_documents (
    document_id TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    markdown_chars INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'success',
    progress INTEGER NOT NULL DEFAULT 100,
    message TEXT NOT NULL DEFAULT '',
    item_count INTEGER NOT NULL DEFAULT 0,
    block_count INTEGER NOT NULL DEFAULT 0,
    filtered_block_count INTEGER NOT NULL DEFAULT 0,
    candidate_item_count INTEGER NOT NULL DEFAULT 0,
    discarded_block_count INTEGER NOT NULL DEFAULT 0,
    system_discarded_after_retry_count INTEGER NOT NULL DEFAULT 0,
    last_batch_size INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    block_id TEXT NOT NULL,
    type TEXT NOT NULL,
    heading_path_json TEXT,
    content TEXT NOT NULL,
    content_chars INTEGER NOT NULL DEFAULT 0,
    is_filtered INTEGER NOT NULL DEFAULT 0,
    filter_reason TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (document_id) REFERENCES knowledge_documents(document_id) ON DELETE CASCADE,
    UNIQUE(document_id, block_id, is_filtered)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_blocks_document_order
ON knowledge_blocks(document_id, is_filtered, sort_order);

CREATE TABLE IF NOT EXISTS knowledge_candidate_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    source TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (document_id) REFERENCES knowledge_documents(document_id) ON DELETE CASCADE,
    UNIQUE(document_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_candidate_items_document_order
ON knowledge_candidate_items(document_id, sort_order);

CREATE TABLE IF NOT EXISTS knowledge_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    title TEXT NOT NULL,
    resume TEXT NOT NULL,
    content TEXT NOT NULL,
    source_file TEXT,
    content_chars INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (document_id) REFERENCES knowledge_documents(document_id) ON DELETE CASCADE,
    UNIQUE(document_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_items_document_order
ON knowledge_items(document_id, sort_order);

CREATE TABLE IF NOT EXISTS knowledge_item_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    block_id TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (document_id) REFERENCES knowledge_documents(document_id) ON DELETE CASCADE,
    UNIQUE(document_id, item_id, block_id)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_item_blocks_item_order
ON knowledge_item_blocks(document_id, item_id, sort_order);

CREATE TABLE IF NOT EXISTS knowledge_discarded_groups (
    group_id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    source TEXT NOT NULL,
    reason TEXT NOT NULL,
    block_ids_json TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (document_id) REFERENCES knowledge_documents(document_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_knowledge_discarded_document_order
ON knowledge_discarded_groups(document_id, source, sort_order);

CREATE TABLE IF NOT EXISTS knowledge_reports (
    document_id TEXT PRIMARY KEY,
    total_blocks INTEGER NOT NULL DEFAULT 0,
    filtered_blocks_count INTEGER NOT NULL DEFAULT 0,
    candidate_items_count INTEGER NOT NULL DEFAULT 0,
    final_items_count INTEGER NOT NULL DEFAULT 0,
    matched_blocks_count INTEGER NOT NULL DEFAULT 0,
    discarded_blocks_count INTEGER NOT NULL DEFAULT 0,
    system_discarded_after_retry_count INTEGER NOT NULL DEFAULT 0,
    new_items_from_recovery_count INTEGER NOT NULL DEFAULT 0,
    recovery_attempt_count INTEGER NOT NULL DEFAULT 0,
    batch_size INTEGER NOT NULL DEFAULT 20,
    coverage_rate REAL NOT NULL DEFAULT 0,
    matched_rate REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (document_id) REFERENCES knowledge_documents(document_id) ON DELETE CASCADE
);
"""

def init_db(db_path: str) -> sqlite3.Connection:
    """初始化 SQLite 数据库"""
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn

def save_to_db(conn: sqlite3.Connection, document_name: str, markdown: str,
               blocks: list, filtered_blocks: list, ai_result: dict | None = None):
    """将所有数据写入 SQLite"""
    document_id = create_id('doc')
    timestamp = now()

    # 写入文档元数据
    item_count = len(ai_result['final_items']) if ai_result else 0
    candidate_count = len(ai_result['items']) if ai_result else 0
    discarded_count = sum(len(d.get('block_ids', [])) for d in (ai_result.get('discarded', []) if ai_result else []))
    system_discarded_count = sum(len(d.get('block_ids', [])) for d in (ai_result.get('system_discarded', []) if ai_result else []))

    conn.execute('''
        INSERT INTO knowledge_documents (document_id, file_name, markdown_chars, status, progress,
            message, item_count, block_count, filtered_block_count, candidate_item_count,
            discarded_block_count, system_discarded_after_retry_count, last_batch_size, created_at, updated_at)
        VALUES (?, ?, ?, 'success', 100, '处理完成', ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        document_id, document_name, len(markdown), item_count,
        len(blocks), len(filtered_blocks), candidate_count,
        discarded_count, system_discarded_count,
        ai_result['report']['batch_size'] if ai_result else None,
        timestamp, timestamp
    ))

    # 写入有效块
    for sort_order, block in enumerate(blocks):
        conn.execute('''
            INSERT INTO knowledge_blocks (document_id, block_id, type, heading_path_json,
                content, content_chars, is_filtered, filter_reason, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, 0, NULL, ?)
        ''', (
            document_id, block['id'], block['type'],
            json.dumps(block.get('heading_path', []), ensure_ascii=False),
            block['content'], get_content_char_count(block['content']),
            sort_order
        ))

    # 写入筛除块
    for sort_order, block in enumerate(filtered_blocks):
        conn.execute('''
            INSERT INTO knowledge_blocks (document_id, block_id, type, heading_path_json,
                content, content_chars, is_filtered, filter_reason, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
        ''', (
            document_id, block['id'], block['type'],
            json.dumps(block.get('heading_path', []), ensure_ascii=False),
            block['content'], get_content_char_count(block['content']),
            block.get('reason', 'unknown'), sort_order
        ))

    if ai_result:
        # 写入候选条目
        for sort_order, item in enumerate(ai_result['items']):
            conn.execute('''
                INSERT INTO knowledge_candidate_items (document_id, item_id, title, summary,
                    source, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'ai', ?, ?, ?)
            ''', (document_id, item['id'], item['title'], item['summary'], sort_order, timestamp, timestamp))

        # 写入最终条目
        for sort_order, item in enumerate(ai_result['final_items']):
            conn.execute('''
                INSERT INTO knowledge_items (document_id, item_id, title, resume, content,
                    source_file, content_chars, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                document_id, item['id'], item['title'], item['resume'],
                item['content'], item['source_file'], len(item['content']),
                sort_order, timestamp, timestamp
            ))

            # 写入条目-块关联
            for bid_order, block_id in enumerate(item.get('source_block_ids', [])):
                conn.execute('''
                    INSERT INTO knowledge_item_blocks (document_id, item_id, block_id, sort_order)
                    VALUES (?, ?, ?, ?)
                ''', (document_id, item['id'], block_id, bid_order))

        # 写入 AI 舍弃组
        all_discarded = list(ai_result.get('discarded', []))
        for sort_order, d in enumerate(all_discarded):
            conn.execute('''
                INSERT INTO knowledge_discarded_groups (document_id, source, reason, block_ids_json, sort_order)
                VALUES (?, 'ai', ?, ?, ?)
            ''', (document_id, d.get('reason', 'AI 建议舍弃'), json.dumps(d.get('block_ids', []), ensure_ascii=False), sort_order))

        # 写入系统舍弃组
        for sort_order, d in enumerate(ai_result.get('system_discarded', [])):
            conn.execute('''
                INSERT INTO knowledge_discarded_groups (document_id, source, reason, block_ids_json, sort_order)
                VALUES (?, 'system', ?, ?, ?)
            ''', (document_id, d.get('reason', 'system_discarded_after_retry'), json.dumps(d.get('block_ids', []), ensure_ascii=False), sort_order))

        # 写入报告
        report = ai_result['report']
        conn.execute('''
            INSERT INTO knowledge_reports (document_id, total_blocks, filtered_blocks_count,
                candidate_items_count, final_items_count, matched_blocks_count,
                discarded_blocks_count, system_discarded_after_retry_count,
                new_items_from_recovery_count, recovery_attempt_count, batch_size,
                coverage_rate, matched_rate, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            document_id, report['total_blocks'], report['filtered_blocks_count'],
            report['candidate_items_count'], report['final_items_count'], report['matched_blocks_count'],
            report['discarded_blocks_count'], report['system_discarded_after_retry_count'],
            report['new_items_from_recovery_count'], report['recovery_attempt_count'], report['batch_size'],
            report['coverage_rate'], report['matched_rate'], report['created_at'],
        ))

    conn.commit()
    return document_id


# ============================================================================
# 主流程
# ============================================================================

def process_markdown(markdown: str, document_name: str, ai: AIClient | None = None,
                     batch_size: int = DEFAULT_BATCH_SIZE) -> dict:
    """处理 Markdown 文档的完整流水线"""
    markdown = strip_markdown_fence(markdown)

    # 阶段二：创建原始块
    print(f'=== 阶段二：创建原始块 ===', file=sys.stderr)
    raw_blocks = create_raw_blocks(markdown)
    print(f'原始块：{len(raw_blocks)} 个', file=sys.stderr)

    # 阶段三：语义合并
    print(f'=== 阶段三：语义合并 ===', file=sys.stderr)
    semantic_blocks = merge_semantic_blocks(raw_blocks)
    print(f'合并后：{len(semantic_blocks)} 个', file=sys.stderr)

    # 阶段四：块过滤
    print(f'=== 阶段四：块过滤 ===', file=sys.stderr)
    filtered = filter_blocks(semantic_blocks)
    blocks = filtered['blocks']
    filtered_out = filtered['filtered_blocks']
    print(f'有效块：{len(blocks)} 个，筛除：{len(filtered_out)} 个', file=sys.stderr)
    if filtered_out:
        reasons = Counter(b['reason'] for b in filtered_out)
        for reason, count in reasons.most_common():
            print(f'  {reason}: {count}', file=sys.stderr)

    # 阶段五（可选）：AI 流水线
    ai_result = None
    if ai:
        print(f'=== 阶段五：AI 条目提取与匹配 ===', file=sys.stderr)
        ai_result = run_ai_pipeline(blocks, filtered_out, document_name, ai, batch_size)
        print(f'=== AI 流水线完成 ===', file=sys.stderr)
        print(f'最终条目：{len(ai_result["final_items"])} 条', file=sys.stderr)
        rpt = ai_result['report']
        print(f'覆盖率：{rpt["coverage_rate"]:.2%}，匹配率：{rpt["matched_rate"]:.2%}', file=sys.stderr)
    else:
        print(f'（跳过 AI 阶段，仅输出块拆分结果）', file=sys.stderr)

    return {
        'blocks': blocks,
        'filtered_blocks': filtered_out,
        'ai_result': ai_result,
    }


def print_summary(result: dict):
    """打印处理摘要"""
    blocks = result['blocks']
    filtered_out = result['filtered_blocks']
    ai_result = result.get('ai_result')

    print()
    print('=' * 60)
    print('处理摘要')
    print('=' * 60)
    print(f'有效块数量：{len(blocks)}')
    print(f'筛除块数量：{len(filtered_out)}')
    if filtered_out:
        reasons = Counter(b['reason'] for b in filtered_out)
        print('筛除原因分布：')
        for reason, count in reasons.most_common():
            print(f'  {reason}: {count}')

    print()
    print('块类型分布：')
    types = Counter(b['type'] for b in blocks)
    for t, count in types.most_common():
        print(f'  {t}: {count}')

    char_counts = [get_content_char_count(b['content']) for b in blocks]
    if char_counts:
        print(f'\n块大小统计：')
        print(f'  最小：{min(char_counts)} 字符')
        print(f'  最大：{max(char_counts)} 字符')
        print(f'  平均：{sum(char_counts) // len(char_counts)} 字符')

    if ai_result:
        rpt = ai_result['report']
        print(f'\nAI 处理结果：')
        print(f'  候选条目：{rpt["candidate_items_count"]} 条')
        print(f'  最终条目：{rpt["final_items_count"]} 条')
        print(f'  覆盖率：{rpt["coverage_rate"]:.2%}')
        print(f'  匹配率：{rpt["matched_rate"]:.2%}')
        print(f'  补漏轮次：{rpt["recovery_attempt_count"]}')
        print(f'  新增条目（补漏）：{rpt["new_items_from_recovery_count"]} 条')


# ============================================================================
# CLI 入口
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Markdown 文档 → 知识库 SQLite 全流程处理',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('input', help='输入的 Markdown 文件路径')
    parser.add_argument('-o', '--output', default='knowledge_base.sqlite', help='输出的 SQLite 文件路径')
    parser.add_argument('--ai', action='store_true', help='启用 AI 条目提取与匹配（需要 OPENAI_API_KEY）')
    parser.add_argument('--api-key', default=os.environ.get('OPENAI_API_KEY', '1'), help='OpenAI API Key（默认取环境变量 OPENAI_API_KEY）')
    parser.add_argument('--api-base', default=os.environ.get('OPENAI_BASE_URL', 'http://192.168.2.3:42121/v1'),
                        help='API 地址（默认 http://192.168.2.3:42121/v1）')
    parser.add_argument('--model', default='Qwen3.5-122B-A10B-GPTQ-Int4', help='模型名称（默认 gpt-4o）')
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE, help=f'AI 分批匹配粒度（默认 {DEFAULT_BATCH_SIZE}）')
    parser.add_argument('--no-db', action='store_true', help='不写入数据库，仅打印摘要')
    parser.add_argument('--print-blocks', action='store_true', help='打印所有有效块到 stdout')
    parser.add_argument('--print-items', action='store_true', help='打印所有最终条目到 stdout')

    args = parser.parse_args()

    # 读取 Markdown
    if not os.path.isfile(args.input):
        print(f'错误：文件不存在：{args.input}', file=sys.stderr)
        sys.exit(1)

    with open(args.input, 'r', encoding='utf-8') as f:
        markdown = f.read()

    document_name = os.path.basename(args.input)
    print(f'输入文件：{args.input} ({len(markdown)} 字符)', file=sys.stderr)

    # 初始化 AI（可选）
    ai = None
    if args.ai:
        if not args.api_key:
            print('错误：--ai 模式需要 API Key（通过 --api-key 或环境变量 OPENAI_API_KEY 提供）', file=sys.stderr)
            sys.exit(1)
        ai = AIClient(api_key=args.api_key, base_url=args.api_base, model=args.model)
        print(f'AI 模型：{args.model}，API：{args.api_base}', file=sys.stderr)

    # 执行流水线
    result = process_markdown(markdown, document_name, ai=ai, batch_size=args.batch_size)

    # 打印摘要
    print_summary(result)

    # 打印块（可选）
    if args.print_blocks:
        print('\n' + '=' * 60)
        print('有效块列表')
        print('=' * 60)
        for block in result['blocks']:
            heading = ' > '.join(block.get('heading_path', []) or '无')
            print(f"\n[{block['id']}] type={block['type']} heading={heading}")
            print(block['content'][:200] + ('...' if len(block['content']) > 200 else ''))

    # 打印条目（可选）
    if args.print_items and result.get('ai_result'):
        print('\n' + '=' * 60)
        print('最终知识条目')
        print('=' * 60)
        for item in result['ai_result']['final_items']:
            print(f"\n[{item['id']}] {item['title']}")
            print(f"  resume: {item['resume'][:100]}...")
            print(f"  content_chars: {len(item['content'])}")
            print(f"  source_blocks: {item['source_block_ids']}")

    # 写入数据库
    if not args.no_db:
        print(f'\n写入 SQLite：{args.output}', file=sys.stderr)
        conn = init_db(args.output)
        document_id = save_to_db(
            conn, document_name, markdown,
            result['blocks'], result['filtered_blocks'],
            result.get('ai_result')
        )
        conn.close()
        print(f'完成！document_id = {document_id}', file=sys.stderr)
        print(f'数据库文件：{os.path.abspath(args.output)}', file=sys.stderr)


if __name__ == '__main__':
    main()
