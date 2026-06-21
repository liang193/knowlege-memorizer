# -*- coding: utf-8 -*-
"""知识库管理器"""
from . import data_manager as dm


def list_knowledge_bases():
    """列出所有知识库"""
    return dm.load_kb_index()


def create_knowledge_base(name, description=""):
    """创建新知识库"""
    index = dm.load_kb_index()
    # 检查重名
    if any(kb.get("name") == name for kb in index):
        return False, "知识库名称已存在"
    kb_dir = dm.get_kb_dir(name)
    dm.ensure_dir(kb_dir)
    import datetime
    entry = {
        "name": name,
        "description": description,
        "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "card_count": 0,
    }
    index.append(entry)
    dm.save_kb_index(index)
    # 初始化空数据文件
    dm.save_knowledge_base(name, [])
    dm.save_outline(name, {"nodes": [], "kp_outline_map": {}})
    dm.save_stats(name, {})
    return True, "知识库创建成功"


def rename_knowledge_base(old_name, new_name):
    """重命名知识库"""
    index = dm.load_kb_index()
    for kb in index:
        if kb.get("name") == old_name:
            kb["name"] = new_name
            dm.save_kb_index(index)
            # 移动数据目录
            old_dir = dm.get_kb_dir(old_name)
            new_dir = dm.get_kb_dir(new_name)
            if old_dir.exists():
                import shutil
                shutil.move(str(old_dir), str(new_dir))
            return True, "重命名成功"
    return False, "知识库不存在"


def delete_knowledge_base(name):
    """删除知识库"""
    dm.delete_knowledge_base(name)


def get_knowledge_base_info(name):
    """获取知识库信息"""
    index = dm.load_kb_index()
    for kb in index:
        if kb.get("name") == name:
            kps = dm.load_knowledge_base(name)
            kb["card_count"] = len(kps)
            return kb
    return None


def update_kb_card_count(name):
    """更新知识库卡片数量"""
    index = dm.load_kb_index()
    kps = dm.load_knowledge_base(name)
    for kb in index:
        if kb.get("name") == name:
            kb["card_count"] = len(kps)
            break
    dm.save_kb_index(index)


def add_knowledge_point(kb_name, kp):
    """添加知识点"""
    kps = dm.load_knowledge_base(kb_name)
    kps.append(kp)
    dm.save_knowledge_base(kb_name, kps)
    update_kb_card_count(kb_name)


def add_knowledge_points_batch(kb_name, new_kps):
    """批量添加知识点"""
    kps = dm.load_knowledge_base(kb_name)
    kps.extend(new_kps)
    dm.save_knowledge_base(kb_name, kps)
    update_kb_card_count(kb_name)


def update_knowledge_point(kb_name, kp_id, updates):
    """更新知识点"""
    kps = dm.load_knowledge_base(kb_name)
    for i, kp in enumerate(kps):
        if kp.get("id") == kp_id:
            kps[i].update(updates)
            break
    dm.save_knowledge_base(kb_name, kps)


def delete_knowledge_point(kb_name, kp_id):
    """删除知识点"""
    kps = dm.load_knowledge_base(kb_name)
    kps = [kp for kp in kps if kp.get("id") != kp_id]
    dm.save_knowledge_base(kb_name, kps)
    update_kb_card_count(kb_name)


def search_knowledge_points(kb_name, keyword):
    """搜索知识点（问题/答案/标签）"""
    kps = dm.load_knowledge_base(kb_name)
    if not keyword:
        return kps
    keyword = keyword.lower()
    results = []
    for kp in kps:
        q = kp.get("question", "").lower()
        a = kp.get("answer", "").lower()
        tags = " ".join(kp.get("tags", [])).lower()
        if keyword in q or keyword in a or keyword in tags:
            results.append(kp)
    return results


def get_kps_by_outline_ref(kb_name, outline_id):
    """按大纲节点过滤知识点"""
    kps = dm.load_knowledge_base(kb_name)
    return [kp for kp in kps if outline_id in kp.get("outline_ref", [])]


def get_kps_by_tag(kb_name, tag):
    """按标签过滤知识点"""
    kps = dm.load_knowledge_base(kb_name)
    return [kp for kp in kps if tag in kp.get("tags", [])]
