# -*- coding: utf-8 -*-
"""DeepSeek API 封装 — OpenAI 兼容接口"""
import json


def get_client(api_key):
    from openai import OpenAI
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")


def call_deepseek(messages, api_key, model="deepseek-chat", temperature=0.3, max_tokens=4096):
    try:
        client = get_client(api_key)
        response = client.chat.completions.create(
            model=model, messages=messages,
            temperature=temperature, max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"error": str(e)}


def extract_qna_from_text(text, api_key, doc_title=""):
    """从文档正文提取Q&A对+大纲。答案保留原文，不可改写。"""
    system_prompt = """你是一个知识提取助手。请从给定的文本中：
1. 提取层级大纲结构（章节/小节），保留原文标题文字
2. 为每个章节提取知识点（问题+答案），答案必须使用原文表述，不可改写
3. 每个知识点标注所属的章节ID

返回JSON格式：
{
  "outline": [{"id": "1", "title": "原文标题", "type": "chapter", "children": [...]}],
  "knowledge_points": [{"question": "问题", "answer": "原文（不可改写）", "section_id": "1-1", "tags": []}]
}
重要约束：答案必须使用原文表述，不允许改写、概括、润色"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"标题：{doc_title}\n\n正文内容：\n{text[:30000]}"}
    ]
    return call_deepseek(messages, api_key, temperature=0.2)


def smart_field_mapping(headers, api_key):
    """智能字段映射：分析表头推荐映射到内部字段"""
    system_prompt = """分析表头列表，映射到以下字段：
- question: 问题/题目/概念名称
- answer: 答案/定义/解释内容
- tags: 标签/分类/类别
- notes: 笔记/备注
- null: 不需要导入
返回JSON: {"mappings": [{"header": "列名", "mapped_to": "字段名"}]}"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps({"headers": headers})}
    ]
    return call_deepseek(messages, api_key, temperature=0.1)


def generate_distractors(question, correct_answer, all_kps_from_section, api_key):
    """生成选择题干扰项"""
    distractors = []
    for kp in all_kps_from_section:
        ans = kp.get("answer", "")
        if ans != correct_answer and ans not in distractors:
            distractors.append(ans)
        if len(distractors) >= 3:
            break
    if len(distractors) < 3:
        try:
            result = call_deepseek([
                {"role": "system", "content": f"生成{3 - len(distractors)}个干扰项。返回JSON: {{\"distractors\": [...]}}"},
                {"role": "user", "content": f"题目：{question}\n正确答案：{correct_answer}"}
            ], api_key, temperature=0.7, max_tokens=512)
            distractors.extend(result.get("distractors", []))
        except Exception:
            while len(distractors) < 3:
                distractors.append("以上都不对")
    return distractors[:3]


def generate_true_false_pairs(question, answer, api_key):
    """生成判断题正误版本，保留原文关键表述"""
    system_prompt = """将以下知识点转换为判断题正误两个版本。
正确版本基于原文，错误版本修改关键细节但保持可信。
保留原文关键表述，只改动关键判断点。
返回JSON: {"true_statement": "正确陈述", "false_statement": "错误陈述"}"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"问题：{question}\n答案：{answer}"}
    ]
    try:
        return call_deepseek(messages, api_key, temperature=0.3, max_tokens=512)
    except Exception:
        return {"true_statement": f"{question} {answer[:50]}",
                "false_statement": f"关于{question[:20]}的说法是错误的"}
