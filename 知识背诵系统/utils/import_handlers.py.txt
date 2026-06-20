# -*- coding: utf-8 -*-
"""文件导入处理器 — 解析 Word/Excel/JSON"""
import json
import os
import tempfile


def read_docx(file_path):
    """
    读取 Word 文档 (.docx)，返回结构化内容。
    返回: {"paragraphs": [{"text": "...", "style": "Heading 1|Normal|...", "level": 1}], "full_text": "..."}
    """
    try:
        from docx import Document
    except ImportError:
        return {"error": "缺少 python-docx 库，无法解析 Word 文档。请执行: pip install python-docx"}

    try:
        doc = Document(file_path)
        paragraphs = []
        full_text_parts = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            style_name = para.style.name if para.style else "Normal"
            # 提取标题级别
            level = 0
            if "Heading" in style_name:
                try:
                    level = int(style_name.split()[-1])
                except (ValueError, IndexError):
                    level = 1
            paragraphs.append({
                "text": text,
                "style": style_name,
                "level": level,
            })
            full_text_parts.append(text)

        return {
            "paragraphs": paragraphs,
            "full_text": "\n".join(full_text_parts),
            "file_type": "docx",
        }
    except Exception as e:
        return {"error": f"读取 Word 文档失败: {str(e)}"}


def read_xlsx(file_path):
    """
    读取 Excel 文件 (.xlsx)，返回表格数据。
    返回: {"headers": ["列1", "列2"], "rows": [{"列1": "值", "列2": "值"}, ...]}
    """
    try:
        import openpyxl
    except ImportError:
        return {"error": "缺少 openpyxl 库。请执行: pip install openpyxl"}

    try:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return {"error": "Excel 文件为空"}
        headers = [str(h) if h is not None else f"列{i}" for i, h in enumerate(rows[0])]
        data_rows = []
        for row in rows[1:]:
            if any(cell is not None for cell in row):
                row_dict = {}
                for i, val in enumerate(row):
                    col_name = headers[i] if i < len(headers) else f"列{i}"
                    row_dict[col_name] = str(val) if val is not None else ""
                data_rows.append(row_dict)
        wb.close()
        return {"headers": headers, "rows": data_rows, "file_type": "xlsx"}
    except Exception as e:
        return {"error": f"读取 Excel 文件失败: {str(e)}"}


def read_json_file(file_path):
    """
    读取 JSON 文件，支持列表和对象格式。
    返回: {"headers": [...], "rows": [...], "file_type": "json"}
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"error": f"JSON 解析失败: {str(e)}"}

    # 适配不同 JSON 结构
    rows = []
    if isinstance(data, list):
        if data and isinstance(data[0], dict):
            rows = data
        elif data and not isinstance(data[0], dict):
            rows = [{"value": str(item)} for item in data]
    elif isinstance(data, dict):
        # 尝试找列表字段
        list_fields = [k for k, v in data.items() if isinstance(v, list)]
        if list_fields:
            rows = data[list_fields[0]]
        else:
            rows = [data]

    # 提取表头
    headers = []
    if rows and isinstance(rows[0], dict):
        headers = list(rows[0].keys())

    return {"headers": headers, "rows": rows, "file_type": "json"}


def detect_file_type(filename):
    """根据扩展名检测文件类型"""
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".docx",):
        return "docx"
    elif ext in (".xlsx", ".xls"):
        return "xlsx"
    elif ext in (".json",):
        return "json"
    elif ext in (".csv",):
        return "csv"
    return None


def read_file(file_path):
    """统一文件读取接口"""
    ftype = detect_file_type(file_path)
    if ftype == "docx":
        return read_docx(file_path)
    elif ftype == "xlsx":
        return read_xlsx(file_path)
    elif ftype == "json":
        return read_json_file(file_path)
    elif ftype == "csv":
        return read_csv(file_path)
    return {"error": f"不支持的文件格式: {ftype}"}


def read_csv(file_path):
    """读取 CSV 文件"""
    import csv as csv_module
    try:
        rows = []
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv_module.DictReader(f)
            headers = reader.fieldnames
            for row in reader:
                rows.append(row)
        return {"headers": headers, "rows": rows, "file_type": "csv"}
    except Exception as e:
        return {"error": f"读取 CSV 文件失败: {str(e)}"}


def apply_mapping(rows, mapping):
    """
    根据字段映射转换数据行。
    mapping: [{"header": "原始列名", "mapped_to": "question|answer|tags|notes|null"}]
    返回: [{"question": "...", "answer": "...", "tags": [...], "notes": "..."}]
    """
    mapped_kps = []
    # 找出有效映射
    valid_mappings = [m for m in mapping if m.get("mapped_to") and m["mapped_to"] != "null"]

    for row in rows:
        kp = {"question": "", "answer": "", "tags": [], "notes": ""}
        has_content = False
        for m in valid_mappings:
            header = m["header"]
            target = m["mapped_to"]
            value = row.get(header, "")
            if not value:
                continue
            value = str(value).strip()
            if target == "tags":
                # 支持逗号/分号/空格分隔的标签
                import re
                kp["tags"] = [t.strip() for t in re.split(r'[,;，；、\s]+', value) if t.strip()]
            elif target in kp:
                kp[target] = value
            has_content = True
        if has_content:
            mapped_kps.append(kp)
    return mapped_kps
