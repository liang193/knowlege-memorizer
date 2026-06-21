# -*- coding: utf-8 -*-
"""DeepSeek API 封装 - OpenAI 兼容接口"""
import json
import re


def get_client(api_key):
    from openai import OpenAI
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")


def _repair_truncated_json(text):
    """尝试修复被截断的 JSON：补齐缺失的括号和引号。"""
    if not text or not text.strip():
        return text
    s = text.strip()

    # 去掉末尾可能的不完整字段
    # 找到最后一个完整的结构边界
    # 计算未闭合的括号
    stack = []
    in_string = False
    escape = False
    for ch in s:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in '{[':
            stack.append(ch)
        elif ch == '}':
            if stack and stack[-1] == '{':
                stack.pop()
        elif ch == ']':
            if stack and stack[-1] == '[':
                stack.pop()

    # 补齐缺失的闭合符号
    closing = {'{': '}', '[': ']'}
    suffix = ''
    for bracket in reversed(stack):
        if bracket in closing:
            suffix += closing[bracket]

    if suffix:
        # 如果最后是逗号或冒号，先去掉
        s = s.rstrip(', \t\n\r')
        # 如果最后是不完整的字符串值（引号中间断了），补一个空字符串
        if in_string:
            s = s.rstrip() + '...'
            if not s.endswith('"'):
                s += '"'
        s = s + suffix

    return s


def _parse_json_lenient(text):
    """宽松 JSON 解析：处理 markdown 代码块包裹、截断、多余空白等。"""
    if not text or not text.strip():
        return {"error": "empty response", "raw_response": ""}
    text = text.strip()

    # 1. 直接解析
    try:
        return json.loads(text)
    except Exception:
        pass

    # 2. 去掉 markdown 代码块包裹
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', text, flags=re.IGNORECASE)
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)

    try:
        return json.loads(cleaned.strip())
    except Exception:
        pass

    # 3. 尝试寻找第一个 { 到最后一个 }
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except Exception:
            pass

    # 4. 尝试修复截断的 JSON（补齐缺失括号）
    fixed = _repair_truncated_json(cleaned)
    if fixed != cleaned:
        try:
            return json.loads(fixed)
        except Exception:
            pass

    # 5. 用 JSONDecoder 逐个提取 JSON 对象
    try:
        decoder = json.JSONDecoder()
        idx = 0
        objs = []
        s = cleaned.strip()
        while idx < len(s):
            # 跳过非 JSON 内容
            while idx < len(s) and s[idx] not in '{[':
                idx += 1
            if idx >= len(s):
                break
            try:
                obj, end_idx = decoder.raw_decode(s, idx)
                objs.append(obj)
                idx = end_idx
            except json.JSONDecodeError:
                # 尝试在上面提到的位置修复并解析
                idx += 1
        if objs:
            # 合并：如果第一个对象包含 outline/knowledge_points，返回它
            for obj in objs:
                if isinstance(obj, dict) and ("outline" in obj or "knowledge_points" in obj):
                    return obj
            # 否则尝试构建一个结果
            result = {"outline": [], "knowledge_points": []}
            for obj in objs:
                if isinstance(obj, dict):
                    if "question" in obj and "answer" in obj:
                        result["knowledge_points"].append(obj)
                    if "outline" in obj:
                        result["outline"] = obj["outline"]
                    if "knowledge_points" in obj:
                        result["knowledge_points"].extend(obj["knowledge_points"])
            if result["knowledge_points"]:
                return result
    except Exception:
        pass

    # 6. 返回原始文本让上游兜底
    return {"error": "JSON parse failed", "raw_response": text[:5000]}


def call_deepseek(messages, api_key, model="deepseek-chat", temperature=0.3, max_tokens=16384):
    """调用 DeepSeek API，返回解析后的 JSON 对象。"""
    try:
        client = get_client(api_key)
        # 第一次尝试：不强制 JSON 格式，用 prompt 引导
        response = client.chat.completions.create(
            model=model, messages=messages,
            temperature=temperature, max_tokens=max_tokens,
        )
        content = response.choices[0].message.content
        finish_reason = response.choices[0].finish_reason

        parsed = _parse_json_lenient(content)

        if "error" in parsed and "JSON parse failed" in parsed.get("error", ""):
            # 如果是被截断了且没强制 json_object，尝试用 response_format 重试
            if finish_reason == "length" or "truncat" in parsed.get("error", "").lower():
                try:
                    response2 = client.chat.completions.create(
                        model=model, messages=messages,
                        temperature=temperature, max_tokens=32768,
                        response_format={"type": "json_object"},
                    )
                    parsed = _parse_json_lenient(response2.choices[0].message.content)
                except Exception:
                    pass
            else:
                # 第二次尝试：强制 JSON 格式
                try:
                    response2 = client.chat.completions.create(
                        model=model, messages=messages,
                        temperature=temperature, max_tokens=max_tokens,
                        response_format={"type": "json_object"},
                    )
                    parsed = _parse_json_lenient(response2.choices[0].message.content)
                except Exception:
                    pass
        return parsed
    except Exception as e:
        return {"error": str(e)}


def extract_qna_from_text(text, api_key, doc_title=""):
    """从文档正文提取Q&A对+大纲。答案保留原文，不可改写。"""
    system_prompt = """你是一个知识提取助手。请从给定的文本中：
1. 提取层级大纲结构（章节/小节），保留原文标题文字
2. 为每个章节提取知识点（问题+答案），答案必须使用原文表述，不可改写
3. 每个知识点标注所属的章节ID

返回纯JSON（不要用```包裹），格式：
{
  "outline": [{"id": "1", "title": "原文标题", "type": "chapter", "children": [...]}],
  "knowledge_points": [{"question": "问题", "answer": "原文（不可改写）", "section_id": "1-1", "tags": []}]
}
重要约束：答案必须使用原文表述，不允许改写、概括、润色"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"标题：{doc_title}\n\n正文内容：\n{text[:30000]}"}
    ]
    return call_deepseek(messages, api_key, temperature=0.2, max_tokens=16384)


def smart_field_mapping(headers, api_key):
    """智能字段映射：分析表头推荐映射到内部字段"""
    system_prompt = """分析表头列表，映射到以下字段：
- question: 问题/题目/概念名称
- answer: 答案/定义/解释内容
- tags: 标签/分类/类别
- notes: 笔记/备注
- null: 不需要导入
返回纯JSON（不要用```包裹）: {"mappings": [{"header": "列名", "mapped_to": "字段名"}]}"""
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
                {"role": "system", "content": f"生成{3 - len(distractors)}个干扰项。返回纯JSON（不要用```包裹）: {{\"distractors\": [...]}}"},
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
返回纯JSON（不要用```包裹）: {"true_statement": "正确陈述", "false_statement": "错误陈述"}"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"问题：{question}\n答案：{answer}"}
    ]
    try:
        return call_deepseek(messages, api_key, temperature=0.3, max_tokens=512)
    except Exception:
        return {"true_statement": f"{question} {answer[:50]}",
                "false_statement": f"关于{question[:20]}的说法是错误的"}
