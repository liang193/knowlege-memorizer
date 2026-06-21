# -*- coding: utf-8 -*-
"""数据管理器 — JSON 文件读写"""
import json
import os
import shutil
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def load_json(filepath):
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return None


def save_json(filepath, data):
    ensure_dir(os.path.dirname(filepath))
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_data_dir():
    ensure_dir(DATA_DIR)
    return str(DATA_DIR)


def get_kb_dir(kb_name):
    safe_name = kb_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    return DATA_DIR / f"kb_{safe_name}"


def load_kb_index():
    path = DATA_DIR / "kb_index.json"
    return load_json(path) or []


def save_kb_index(index):
    save_json(DATA_DIR / "kb_index.json", index)


def load_knowledge_base(kb_name):
    path = get_kb_dir(kb_name) / "knowledge_base.json"
    return load_json(path) or []


def save_knowledge_base(kb_name, data):
    save_json(get_kb_dir(kb_name) / "knowledge_base.json", data)


def load_outline(kb_name):
    path = get_kb_dir(kb_name) / "outline.json"
    return load_json(path) or {"nodes": [], "kp_outline_map": {}}


def save_outline(kb_name, data):
    save_json(get_kb_dir(kb_name) / "outline.json", data)


def load_stats(kb_name):
    path = get_kb_dir(kb_name) / "stats.json"
    return load_json(path) or {}


def save_stats(kb_name, data):
    save_json(get_kb_dir(kb_name) / "stats.json", data)


def load_api_key():
    path = DATA_DIR / "settings.json"
    settings = load_json(path) or {}
    return settings.get("deepseek_api_key", "")


def save_api_key(api_key):
    path = DATA_DIR / "settings.json"
    settings = load_json(path) or {}
    settings["deepseek_api_key"] = api_key
    save_json(path, settings)


def load_field_templates(kb_name):
    path = get_kb_dir(kb_name) / "field_templates.json"
    return load_json(path) or []


def save_field_templates(kb_name, templates):
    save_json(get_kb_dir(kb_name) / "field_templates.json", templates)


def export_knowledge_base(kb_name, output_path):
    kb = load_knowledge_base(kb_name)
    outline = load_outline(kb_name)
    import datetime
    export_data = {
        "kb_name": kb_name,
        "export_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "knowledge_base": kb, "outline": outline,
    }
    save_json(output_path, export_data)
    return len(kb)


def delete_knowledge_base(kb_name):
    kb_dir = get_kb_dir(kb_name)
    if os.path.exists(kb_dir):
        shutil.rmtree(kb_dir)
    index = load_kb_index()
    index = [kb for kb in index if kb.get("name") != kb_name]
    save_kb_index(index)
