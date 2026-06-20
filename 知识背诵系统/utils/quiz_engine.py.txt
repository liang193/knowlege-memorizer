# -*- coding: utf-8 -*-
"""刷题引擎 — 选择题/判断题/简答题/论述题"""
import random
from . import deepseek_api as ds
from . import kb_manager as kbm
from .sm2 import init_card


def get_quiz_item(kp, q_type, all_kps_in_range, api_key=None):
    """
    根据题型生成一道题目。
    
    参数:
        kp: 当前知识点
        q_type: "选择题"|"判断题"|"简答题"|"论述题"|"混合"
        all_kps_in_range: 当前范围的同组知识点（用于取干扰项）
        api_key: DeepSeek API Key（可选，用于生成干扰项）
    
    返回:
        {"type": "选择题", "question": "...", "options": [...], "answer": "正确选项", 
         "explanation": "...", "kp_id": "..."}
    """
    q = kp.get("question", "")
    a = kp.get("answer", "")
    kp_id = kp.get("id", "")
    
    # 混合模式随机选一种
    if q_type == "混合":
        q_type = random.choice(["选择题", "判断题", "简答题", "论述题"])
    
    if q_type == "选择题":
        return _gen_mcq(q, a, kp_id, all_kps_in_range, api_key)
    elif q_type == "判断题":
        return _gen_tf(q, a, kp_id, api_key)
    elif q_type == "简答题":
        return _gen_short_answer(q, a, kp_id)
    elif q_type == "论述题":
        return _gen_essay(q, a, kp_id)
    return _gen_short_answer(q, a, kp_id)


def _gen_mcq(question, answer, kp_id, all_kps_in_range, api_key):
    """生成选择题"""
    # 生成 3 个干扰项
    distractors = _get_distractors(answer, all_kps_in_range, api_key)
    options = distractors[:3] + [answer]
    random.shuffle(options)
    
    correct_index = options.index(answer)
    labels = ["A", "B", "C", "D"]
    options_display = [f"{labels[i]}. {opt}" for i, opt in enumerate(options)]
    
    return {
        "type": "选择题",
        "question": question,
        "options": options_display,
        "options_raw": options,
        "correct_index": correct_index,
        "answer": answer,
        "kp_id": kp_id,
    }


def _get_distractors(correct_answer, all_kps_in_range, api_key=None):
    """获取干扰项"""
    distractors = []
    for kp in all_kps_in_range:
        ans = kp.get("answer", "")
        if ans and ans != correct_answer and ans not in distractors:
            distractors.append(ans)
        if len(distractors) >= 3:
            break
    # 用简单补位
    while len(distractors) < 3:
        distractors.append(f"以上描述均不正确（{len(distractors)+1}）")
    return distractors


def _gen_tf(question, answer, kp_id, api_key=None):
    """生成判断题"""
    # 如果有 API Key 且知识点有内容，尝试 AI 生成
    true_statement = f"{question} {answer[:80]}" if len(question + answer) > 20 else answer
    
    # 随机决定对错
    is_true = random.choice([True, False])
    
    if is_true:
        statement = true_statement
    else:
        # 伪造一个错误版本
        statement = f"{question} 上述说法是错误的"
    
    return {
        "type": "判断题",
        "question": statement,
        "is_true": is_true,
        "answer": "正确" if is_true else "错误",
        "explanation": true_statement,
        "kp_id": kp_id,
    }


def _gen_short_answer(question, answer, kp_id):
    """生成简答题（翻卡模式）"""
    return {
        "type": "简答题",
        "question": question,
        "answer": answer,
        "hidden": True,  # 初始隐藏答案
        "kp_id": kp_id,
    }


def _gen_essay(question, answer, kp_id):
    """生成论述题（直接展示知识点内容）"""
    return {
        "type": "论述题",
        "question": question,
        "answer": answer,
        "show_full": True,  # 直接展示
        "kp_id": kp_id,
    }


def get_quiz_items_batch(kps, q_type, count=10, api_key=None):
    """
    批量生成题目。
    
    参数:
        kps: 知识点列表
        q_type: 题型
        count: 题目数量（-1 表示全部）
        api_key: DeepSeek API Key
    
    返回: [quiz_item, ...]
    """
    if count == -1 or count > len(kps):
        count = len(kps)
    
    selected = random.sample(kps, min(count, len(kps)))
    items = []
    for kp in selected:
        item = get_quiz_item(kp, q_type, kps, api_key)
        items.append(item)
    return items


def check_answer(quiz_item, user_answer):
    """
    检查用户答案是否正确。
    
    参数:
        quiz_item: 题目对象
        user_answer: 用户选择的答案（选择题：索引，判断题：True/False，简答/论述：不需要）
    
    返回: {"correct": True/False, "explanation": "..."}
    """
    q_type = quiz_item["type"]
    
    if q_type == "选择题":
        correct = user_answer == quiz_item["correct_index"]
        return {
            "correct": correct,
            "correct_answer": quiz_item["options_raw"][quiz_item["correct_index"]],
            "explanation": quiz_item["answer"],
        }
    elif q_type == "判断题":
        correct = user_answer == quiz_item["is_true"]
        return {
            "correct": correct,
            "correct_answer": "正确" if quiz_item["is_true"] else "错误",
            "explanation": quiz_item.get("explanation", ""),
        }
    elif q_type == "简答题":
        # 简答题由用户自评
        return {"correct": None, "correct_answer": quiz_item["answer"], "explanation": ""}
    elif q_type == "论述题":
        return {"correct": None, "correct_answer": "", "explanation": ""}
    return {"correct": False, "correct_answer": "", "explanation": ""}
