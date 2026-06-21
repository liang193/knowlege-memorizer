# -*- coding: utf-8 -*-
"""大纲生成器 + QA提取"""
import json
import re
from . import deepseek_api as ds


def _salvage_raw_response(raw_text, full_text=""):
    """
    当 JSON 解析失败时，从 raw_response 中尽力提取。
    使用 JSONDecoder.raw_decode 逐个提取 JSON 对象。
    """
    kps = []
    nodes = []

    if not raw_text or not raw_text.strip():
        if full_text:
            nodes = [{
                "id": "1",
                "title": full_text[:100].strip() or "导入内容",
                "type": "chapter",
                "children": [],
            }]
        return {"nodes": nodes, "knowledge_points": kps}

    # 预处理：去掉 markdown 代码块
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', raw_text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)

    # 使用 JSONDecoder.raw_decode 逐个提取顶层 JSON 对象
    try:
        decoder = json.JSONDecoder()
        idx = 0
        while idx < len(cleaned):
            while idx < len(cleaned) and cleaned[idx] not in '{[':
                idx += 1
            if idx >= len(cleaned):
                break
            try:
                obj, end = decoder.raw_decode(cleaned, idx)
                if isinstance(obj, dict):
                    if "outline" in obj:
                        nodes = obj.get("outline", [])
                    if "knowledge_points" in obj:
                        kps.extend(obj.get("knowledge_points", []))
                    if "question" in obj and "answer" in obj:
                        kps.append(obj)
                idx = end
            except json.JSONDecodeError:
                idx += 1
    except Exception:
        pass

    # 如果还是没有，创建包含全文的节点
    if not nodes:
        nodes = [{
            "id": "1",
            "title": full_text[:100].strip() if full_text else "导入内容",
            "type": "chapter",
            "children": [],
        }]

    # 标记原文
    for kp in kps:
        if "source_text" not in kp:
            kp["source_text"] = kp.get("answer", "")

    return {"nodes": nodes, "knowledge_points": kps}


def extract_outline_from_docx(docx_data, api_key, doc_title=""):
    """
    从 Word 文档解析结果中提取大纲 + Q&A。
    优先使用文档自带标题层级构建大纲，AI 只做结构化补充。
    """
    paragraphs = docx_data.get("paragraphs", [])
    full_text = docx_data.get("full_text", "")

    # 1. 从文档标题构建基础大纲
    outline_nodes = []
    current_chapter = None
    current_section = None
    chapter_counter = 0
    section_counter = 0
    sub_counter = 0

    for para in paragraphs:
        if para["level"] == 1:
            chapter_counter += 1
            section_counter = 0
            sub_counter = 0
            current_section = None
            current_chapter = {
                "id": str(chapter_counter),
                "title": para["text"],
                "type": "chapter",
                "children": [],
            }
            outline_nodes.append(current_chapter)
        elif para["level"] == 2 and current_chapter:
            section_counter += 1
            sub_counter = 0
            current_section = {
                "id": f"{chapter_counter}-{section_counter}",
                "title": para["text"],
                "type": "section",
                "children": [],
            }
            current_chapter["children"].append(current_section)
        elif para["level"] >= 3 and current_chapter and current_section:
            sub_counter += 1
            sub_section = {
                "id": f"{chapter_counter}-{section_counter}-{sub_counter}",
                "title": para["text"],
                "type": "subsection",
                "children": [],
            }
            current_section["children"].append(sub_section)

    # 2. 如果没有标题层级，用 AI 提取大纲
    if not outline_nodes:
        return extract_outline_ai(full_text, api_key, doc_title)

    # 3. 调用 AI 提取知识要点（保留原文）
    result = ds.extract_qna_from_text(full_text, api_key, doc_title)

    if "error" in result:
        error_msg = result.get("error", "")
        if "raw_response" in result:
            salvaged = _salvage_raw_response(result["raw_response"], full_text)
            return {
                "nodes": salvaged.get("nodes", outline_nodes),
                "knowledge_points": salvaged.get("knowledge_points", []),
            }
        return {"nodes": outline_nodes, "knowledge_points": [], "error": error_msg}

    ai_kps = result.get("knowledge_points", [])

    for kp in ai_kps:
        if "source_text" not in kp:
            kp["source_text"] = kp.get("answer", "")

    return {
        "nodes": outline_nodes,
        "knowledge_points": ai_kps,
    }


def extract_outline_ai(full_text, api_key, doc_title=""):
    """纯 AI 提取（文档无标题层级时使用）。"""
    result = ds.extract_qna_from_text(full_text, api_key, doc_title)
    if "error" in result:
        error_msg = result.get("error", "")
        if "raw_response" in result:
            salvaged = _salvage_raw_response(result["raw_response"], full_text)
            return salvaged
        return {"nodes": [], "knowledge_points": [], "error": error_msg}

    ai_outline = result.get("outline", [])
    ai_kps = result.get("knowledge_points", [])

    for kp in ai_kps:
        if "source_text" not in kp:
            kp["source_text"] = kp.get("answer", "")

    flat_nodes = []
    def flatten(items, parent=None):
        for item in items:
            children = item.pop("children", [])
            node = {
                "id": item["id"],
                "title": item["title"],
                "type": item.get("type", "section"),
                "parent": parent,
                "children_ids": [c["id"] for c in children],
            }
            flat_nodes.append(node)
            flatten(children, item["id"])
    flatten(ai_outline)

    return {"nodes": flat_nodes, "knowledge_points": ai_kps}


def extract_qna_from_structured_data(rows, headers, api_key):
    """从结构化数据（Excel/JSON/CSV）中提取知识要点。"""
    q_col = a_col = None
    for h in headers:
        hl = h.lower()
        if any(kw in hl for kw in ["问题", "题目", "question", "概念", "名称"]):
            q_col = h
        if any(kw in hl for kw in ["答案", "解释", "定义", "answer", "内容"]):
            a_col = h

    results = []
    if q_col and a_col:
        for row in rows:
            q_text = str(row.get(q_col, "")).strip()
            a_text = str(row.get(a_col, "")).strip()
            if q_text and a_text:
                results.append({
                    "question": q_text,
                    "answer": a_text,
                    "source_text": a_text,
                    "tags": [],
                })
    return results


def build_kp_outline_map(knowledge_points):
    """构建知识点到大纲节点的映射。"""
    mapping = {}
    for i, kp in enumerate(knowledge_points):
        section_id = kp.get("section_id", "")
        if section_id:
            if section_id not in mapping:
                mapping[section_id] = []
            mapping[section_id].append(i)
    return mapping
