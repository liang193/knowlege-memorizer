# -*- coding: utf-8 -*-
"""大纲生成器 + QA提取"""
import json
from . import deepseek_api as ds


def extract_outline_from_docx(docx_data, api_key, doc_title=""):
    """
    从 Word 文档解析结果中提取大纲 + Q&A。
    优先使用文档自带标题层级构建大纲，AI 只做结构化补充。
    
    流程:
    1. 从文档段落中提取标题层级 → 构建基础大纲
    2. 将段落按章节分组
    3. 调用 AI 提取每个章节的 Q&A（保留原文）
    4. 返回组合结果
    """
    paragraphs = docx_data.get("paragraphs", [])
    full_text = docx_data.get("full_text", "")
    
    # 1. 从文档标题构建基础大纲
    outline_nodes = []
    current_chapter = None
    current_section = None
    chapter_counter = 0
    section_counter = 0
    
    for para in paragraphs:
        if para["level"] == 1:
            chapter_counter += 1
            section_counter = 0
            current_chapter = {
                "id": str(chapter_counter),
                "title": para["text"],
                "type": "chapter",
                "children": [],
            }
            outline_nodes.append(current_chapter)
        elif para["level"] >= 2 and current_chapter:
            section_counter += 1
            current_section = {
                "id": f"{chapter_counter}-{section_counter}",
                "title": para["text"],
                "type": "section",
                "children": [],
            }
            current_chapter["children"].append(current_section)
    
    # 2. 如果没有标题层级，用 AI 提取大纲
    if not outline_nodes:
        return extract_outline_ai(full_text, api_key, doc_title)
    
    # 3. 调用 AI 提取知识要点（保留原文）
    result = ds.extract_qna_from_text(full_text, api_key, doc_title)
    
    if "error" in result:
        return {"nodes": outline_nodes, "knowledge_points": [], "error": result["error"]}
    
    ai_kps = result.get("knowledge_points", [])
    
    # 4. 确保每个知识点的答案保留原文
    for kp in ai_kps:
        if "source_text" not in kp:
            kp["source_text"] = kp.get("answer", "")
    
    return {
        "nodes": outline_nodes,
        "knowledge_points": ai_kps,
    }


def extract_outline_ai(full_text, api_key, doc_title=""):
    """
    纯 AI 提取（文档无标题层级时使用）。
    坚持原文保留原则。
    """
    result = ds.extract_qna_from_text(full_text, api_key, doc_title)
    if "error" in result:
        return {"nodes": [], "knowledge_points": [], "error": result["error"]}
    
    ai_outline = result.get("outline", [])
    ai_kps = result.get("knowledge_points", [])
    
    # 确保原文保留
    for kp in ai_kps:
        if "source_text" not in kp:
            kp["source_text"] = kp.get("answer", "")
    
    # 扁平化大纲节点
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
    """
    从结构化数据（Excel/JSON/CSV）中提取知识要点。
    当数据有 question 和 answer 列时直接使用，否则让 AI 推断。
    
    返回: [{"question": "...", "answer": "...", "tags": [...], "source_text": "..."}]
    """
    # 检查是否有明显的问答列
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
                    "source_text": a_text,  # 原文保留
                    "tags": [],
                })
    return results


def build_kp_outline_map(knowledge_points):
    """
    构建知识点到大纲节点的映射。
    返回: {"section_id": [kp_index, ...], ...}
    """
    mapping = {}
    for i, kp in enumerate(knowledge_points):
        section_id = kp.get("section_id", "")
        if section_id:
            if section_id not in mapping:
                mapping[section_id] = []
            mapping[section_id].append(i)
    return mapping
