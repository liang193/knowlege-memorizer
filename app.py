# -*- coding: utf-8 -*-
"""知识背诵系统 - 主入口"""
import sys as _sys, os as _os
_extra_pkgs = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "Documents", "Codex", "python_pkgs")
_extra_pkgs = _os.path.abspath(_extra_pkgs)
if _os.path.isdir(_extra_pkgs) and _extra_pkgs not in _sys.path:
    _sys.path.insert(0, _extra_pkgs)
import streamlit as st
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import data_manager as dm
from utils import kb_manager as kbm
from utils import sm2
from utils import import_handlers as ih
from utils import outline_generator as og
from utils import quiz_engine as qe
from utils import deepseek_api as ds

st.set_page_config(page_title="知识背诵系统", layout="wide")

# ====== 大纲辅助函数 ======

def _normalize_outline_nodes(nodes):
    """将嵌套 children 格式转换为扁平 parent + children_ids 格式，统一渲染。"""
    if not nodes:
        return []
    # 已经是扁平格式（有 parent/children_ids），直接返回
    sample = nodes[0]
    if isinstance(sample, dict) and "parent" in sample and "children_ids" in sample:
        return nodes
    # 嵌套格式：children 是对象数组，需要展开
    flat = []
    def walk(items, parent_id=None):
        for item in items:
            child_objs = item.pop("children", [])
            child_ids = [c["id"] for c in child_objs]
            flat_item = {
                "id": item["id"],
                "title": item["title"],
                "type": item.get("type", "section"),
                "parent": parent_id,
                "children_ids": child_ids,
            }
            flat.append(flat_item)
            walk(child_objs, item["id"])
    walk(nodes)
    return flat


def _get_descendant_ids(outline_nodes, node_id):
    """递归获取某节点及其所有子孙节点的 id 列表。"""
    result = {node_id}
    for node in outline_nodes:
        if node.get("id") == node_id:
            for child_id in node.get("children_ids", []):
                result.update(_get_descendant_ids(outline_nodes, child_id))
            break
    return result


# ====== 大纲渲染 ======

def render_outline_tree(outline_data, kb_name):
    nodes = outline_data.get("nodes", [])
    if not nodes:
        st.sidebar.caption("暂无大纲，请先导入知识")
        return

    # 构建 id -> node 的快速索引
    node_map = {n["id"]: n for n in nodes}

    def _render_node(node_id, indent=0):
        node = node_map.get(node_id)
        if not node:
            return
        prefix = "  " * indent
        icon = "📁" if node.get("type") in ("chapter",) else "📄"
        label = f"{prefix}{icon} {node['title']}"
        if st.sidebar.button(label, key=f"outline_{node_id}", use_container_width=True, help="点击查看该章节知识点"):
            st.session_state.selected_outline_id = node_id
            st.rerun()
        for child_id in node.get("children_ids", []):
            _render_node(child_id, indent + 1)

    root_ids = [n["id"] for n in nodes if not n.get("parent")]
    for rid in root_ids:
        _render_node(rid)


# ====== 状态初始化 ======

def init_state():
    if "kb_list" not in st.session_state:
        st.session_state.kb_list = kbm.list_knowledge_bases()
    if "current_kb" not in st.session_state:
        st.session_state.current_kb = st.session_state.kb_list[0]["name"] if st.session_state.kb_list else ""
    if "selected_outline_id" not in st.session_state:
        st.session_state.selected_outline_id = None
    if "quiz_items" not in st.session_state:
        st.session_state.quiz_items = []
    if "quiz_index" not in st.session_state:
        st.session_state.quiz_index = 0
    if "quiz_answers" not in st.session_state:
        st.session_state.quiz_answers = {}
    if "quiz_mode" not in st.session_state:
        st.session_state.quiz_mode = "选择题"
    if "flashcard_index" not in st.session_state:
        st.session_state.flashcard_index = 0
    if "flashcard_revealed" not in st.session_state:
        st.session_state.flashcard_revealed = False
    if "import_file_data" not in st.session_state:
        st.session_state.import_file_data = None
    if "import_mapping" not in st.session_state:
        st.session_state.import_mapping = None

init_state()


def refresh_kb_list():
    st.session_state.kb_list = kbm.list_knowledge_bases()


# ====== 主布局 ======

def main():
    st.title("📚 知识背诵系统")

    with st.sidebar:
        st.header("📂 知识库")
        kb_names = [kb["name"] for kb in st.session_state.kb_list]

        if not kb_names:
            st.warning("暂无知识库，请先创建")
            new_name = st.text_input("新知识库名称", key="new_kb_name")
            new_desc = st.text_input("描述（可选）", key="new_kb_desc")
            if st.button("创建", use_container_width=True):
                ok, msg = kbm.create_knowledge_base(new_name, new_desc)
                if ok:
                    st.success(msg)
                    refresh_kb_list()
                    st.rerun()
                else:
                    st.error(msg)
            return

        selected_kb = st.selectbox(
            "选择知识库", kb_names,
            index=kb_names.index(st.session_state.current_kb) if st.session_state.current_kb in kb_names else 0,
            key="kb_selector"
        )
        if selected_kb != st.session_state.current_kb:
            st.session_state.current_kb = selected_kb
            st.session_state.selected_outline_id = None
            st.rerun()

        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ 新建", use_container_width=True):
                st.session_state.show_new_kb = True
        with col2:
            if st.button("🗑️ 删除", use_container_width=True):
                kbm.delete_knowledge_base(st.session_state.current_kb)
                refresh_kb_list()
                st.rerun()

        if st.session_state.get("show_new_kb"):
            with st.form("new_kb_form"):
                nk_name = st.text_input("名称")
                nk_desc = st.text_input("描述")
                if st.form_submit_button("确认创建"):
                    ok, msg = kbm.create_knowledge_base(nk_name, nk_desc)
                    if ok:
                        refresh_kb_list()
                        st.session_state.show_new_kb = False
                        st.rerun()
                    else:
                        st.error(msg)
                if st.form_submit_button("取消"):
                    st.session_state.show_new_kb = False
                    st.rerun()

        st.divider()
        st.markdown("### 📋 大纲目录")
        kb_name = st.session_state.current_kb
    if kb_name:
        outline_data = dm.load_outline(kb_name)
        # 兼容旧数据：将嵌套格式实时转为扁平
        nodes = outline_data.get("nodes", [])
        if nodes and not ("parent" in nodes[0] and "children_ids" in nodes[0]):
            outline_data["nodes"] = _normalize_outline_nodes(nodes)
            dm.save_outline(kb_name, outline_data)
        render_outline_tree(outline_data, kb_name)

        st.divider()
        st.text_input("🔍 搜索知识点", key="search_keyword")

    # Main area tabs
    kb_name = st.session_state.current_kb
    if not kb_name:
        return

    tabs = st.tabs(["📚 知识点", "📥 导入", "✏️ 刷题", "🎯 闪卡", "📊 统计", "⚙️ 设置"])
    with tabs[0]:
        tab_knowledge(kb_name)
    with tabs[1]:
        tab_import(kb_name)
    with tabs[2]:
        tab_quiz(kb_name)
    with tabs[3]:
        tab_flashcard(kb_name)
    with tabs[4]:
        tab_stats(kb_name)
    with tabs[5]:
        tab_settings()


# ====== 知识点页 ======

def tab_knowledge(kb_name):
    st.subheader("知识点列表")
    outline_id = st.session_state.selected_outline_id
    keyword = st.session_state.get("search_keyword", "")
    kps = kbm.search_knowledge_points(kb_name, keyword)
    outline_nodes = dm.load_outline(kb_name).get("nodes", [])

    # 大纲过滤：支持层级匹配
    if outline_id:
        matched_ids = _get_descendant_ids(outline_nodes, outline_id)
        kps = [kp for kp in kps if any(
            ref in matched_ids or
            str(ref).startswith(f"{outline_id}-") or
            str(ref).startswith(f"{outline_id}.")
            for ref in kp.get("outline_ref", [])
        )]

    if not kps:
        if outline_id:
            st.info(f"该章节暂无知识点")
        else:
            st.info("暂无知识点，请先导入或手动添加")
    else:
        st.caption(f"共 {len(kps)} 条知识点")

    # 手动添加
    with st.expander("➕ 手动添加知识点"):
        with st.form("add_kp_form"):
            q = st.text_area("问题 *", height=80)
            a = st.text_area("答案 *", height=120)
            tags = st.text_input("标签（逗号分隔）")
            notes = st.text_area("笔记（可选）", height=60)
            if st.form_submit_button("添加", use_container_width=True) and q and a:
                card = sm2.init_card(q, a, tags=[t.strip() for t in tags.split(",") if t.strip()], notes=notes)
                if outline_id:
                    card["outline_ref"] = [outline_id]
                kbm.add_knowledge_point(kb_name, card)
                st.success("添加成功")
                st.rerun()

    for i, kp in enumerate(kps):
        with st.expander(f"{kp.get('question', '无题')[:60]}", expanded=False):
            st.markdown(f"**答案：** {kp.get('answer', '')}")
            if kp.get("source_text"):
                st.caption(f"📝 原文：{kp['source_text'][:200]}")
            st.markdown("**标签：** " + ", ".join([f"{t}" for t in kp.get("tags", [])]))
            st.caption(f"状态：{kp.get('status', 'new')} | 复习间隔：{kp.get('interval', 0)}天 | 正确率：{_calc_correct_rate(kp)}")
            col1, col2, col3 = st.columns([1, 1, 3])
            with col1:
                if st.button("✏️ 编辑", key=f"edit_{kp['id']}", use_container_width=True):
                    st.session_state[f"editing_{kp['id']}"] = True
            with col2:
                if st.button("🗑️ 删除", key=f"del_{kp['id']}", use_container_width=True):
                    kbm.delete_knowledge_point(kb_name, kp["id"])
                    st.rerun()
            if st.session_state.get(f"editing_{kp['id']}"):
                with st.form(f"edit_form_{kp['id']}"):
                    eq = st.text_area("问题", value=kp["question"], height=80)
                    ea = st.text_area("答案", value=kp["answer"], height=120)
                    et = st.text_input("标签", value=", ".join(kp.get("tags", [])))
                    if st.form_submit_button("保存"):
                        kbm.update_knowledge_point(kb_name, kp["id"], {
                            "question": eq, "answer": ea,
                            "tags": [t.strip() for t in et.split(",") if t.strip()]
                        })
                        st.session_state[f"editing_{kp['id']}"] = False
                        st.rerun()
                    if st.form_submit_button("取消"):
                        st.session_state[f"editing_{kp['id']}"] = False
                        st.rerun()


def _calc_correct_rate(kp):
    total = kp.get("quiz_count", 0)
    correct = kp.get("correct_count", 0)
    if total == 0:
        return "暂无"
    return f"{correct}/{total} ({correct/total*100:.0f}%)"


# ====== 导入页 ======

def tab_import(kb_name):
    st.subheader("📥 导入知识")
    api_key = dm.load_api_key()
    if not api_key:
        st.warning("⚠️ 请先在「设置」中填入 DeepSeek API Key，AI 智能解析需要 API Key")

    uploaded_file = st.file_uploader(
        "上传文件（支持 .docx / .xlsx / .json / .csv）",
        type=["docx", "xlsx", "json", "csv"]
    )

    if uploaded_file is None:
        st.session_state.import_file_data = None
        st.session_state.import_mapping = None
        st.info("请上传文件开始导入")
        return

    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{uploaded_file.name}") as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name

    file_data = ih.read_file(tmp_path)
    if "error" in file_data:
        st.error(file_data["error"])
        os.unlink(tmp_path)
        return

    st.success(f"文件读取成功：{uploaded_file.name}")
    st.session_state.import_file_data = {"path": tmp_path, "data": file_data}

    ftype = file_data.get("file_type", "")
    rows = file_data.get("rows", [])
    headers = file_data.get("headers", [])

    # 预览
    if rows:
        st.subheader("预览")
        preview_rows = rows[:5]
        if headers:
            preview = [{h: r.get(h, "") for h in headers} for r in preview_rows]
            st.dataframe(preview, use_container_width=True)
        else:
            st.json(preview_rows)
        st.caption(f"共 {len(rows)} 行数据")

    # 结构化文件（Excel/JSON/CSV）
    if ftype in ("xlsx", "json", "csv") and headers:
        st.subheader("字段映射")
        st.caption("将文件列映射到知识库字段。系统已自动识别，可手动调整。")
        if api_key and not st.session_state.import_mapping:
            auto_result = ds.smart_field_mapping(headers, api_key)
            if "error" not in auto_result:
                st.session_state.import_mapping = auto_result.get("mappings", [])

        mapping = st.session_state.import_mapping or [{"header": h, "mapped_to": "null"} for h in headers]
        new_mapping = []
        for i, h in enumerate(headers):
            current_map = "null"
            for m in mapping:
                if m.get("header") == h:
                    current_map = m.get("mapped_to", "null")
                    break
            cols = st.columns([2, 2])
            with cols[0]:
                st.text(h)
            with cols[1]:
                mapped = st.selectbox(
                    "映射到", ["null", "question", "answer", "tags", "notes"],
                    index=["null", "question", "answer", "tags", "notes"].index(current_map)
                    if current_map in ["null", "question", "answer", "tags", "notes"] else 0,
                    key=f"map_{i}", label_visibility="collapsed"
                )
            new_mapping.append({"header": h, "mapped_to": mapped})
        st.session_state.import_mapping = new_mapping

        if st.button("确认映射并导入", use_container_width=True, type="primary"):
            mapped_kps = ih.apply_mapping(rows, new_mapping)
            if mapped_kps:
                cards = []
                for mkp in mapped_kps:
                    card = sm2.init_card(
                        mkp.get("question", ""), mkp.get("answer", ""),
                        tags=mkp.get("tags", []), notes=mkp.get("notes", ""),
                        source_text=mkp.get("answer", "")
                    )
                    cards.append(card)
                kbm.add_knowledge_points_batch(kb_name, cards)
                st.success(f"成功导入 {len(cards)} 条知识点")
                os.unlink(tmp_path)
                st.rerun()
            else:
                st.error("没有可导入的数据，请检查字段映射")

    # Word 文档
    elif ftype == "docx":
        st.subheader("Word 文档智能提取")
        st.caption("系统将自动提取章节大纲和知识点，原文内容保留不变")
        if st.button("开始智能提取", use_container_width=True, type="primary"):
            with st.spinner("正在分析文档，请稍候..."):
                if api_key:
                    result = og.extract_outline_from_docx(file_data, api_key, uploaded_file.name)
                else:
                    result = {"nodes": [], "knowledge_points": []}

                if "error" in result:
                    st.warning(f"AI 提取异常：{result.get('error')}，将使用纯文本导入")

                nodes = result.get("nodes", [])
                kps_list = result.get("knowledge_points", [])

                if nodes or kps_list:
                    # 规范化大纲节点（嵌套 → 扁平）
                    flat_nodes = _normalize_outline_nodes(nodes)
                    # 构建 kp_outline_map
                    kp_map = {}
                    for kp_item in kps_list:
                        sid = kp_item.get("section_id", "")
                        if sid:
                            if sid not in kp_map:
                                kp_map[sid] = []
                            kp_map[sid].append(len(kps_list))

                    dm.save_outline(kb_name, {"nodes": flat_nodes, "kp_outline_map": kp_map})

                    if kps_list:
                        cards = []
                        for kp_item in kps_list:
                            sid = kp_item.get("section_id", "")
                            if sid:
                                parts = sid.split("-")
                                if parts and parts[0].isdigit():
                                    parts[0] = str(int(parts[0]) + 1)
                                    sid = "-".join(parts)
                            card = sm2.init_card(
                                kp_item.get("question", ""), kp_item.get("answer", ""),
                                tags=kp_item.get("tags", []),
                                source_text=kp_item.get("source_text", kp_item.get("answer", "")),
                                outline_ref=[sid] if sid else []
                            )
                            cards.append(card)
                        kbm.add_knowledge_points_batch(kb_name, cards)
                        st.success(f"成功导入 {len(cards)} 条知识点，{len(flat_nodes)} 个大纲节点")
                    else:
                        st.info(f"已生成 {len(flat_nodes)} 个大纲节点，请手动添加知识点")
                    os.unlink(tmp_path)
                    st.rerun()
                else:
                    full_text = file_data.get("full_text", "")
                    if full_text:
                        para_cards = []
                        for p in file_data.get("paragraphs", []):
                            txt = p.get("text", "").strip()
                            if txt and len(txt) > 10:
                                card = sm2.init_card(txt[:60], txt, source_text=txt)
                                para_cards.append(card)
                        if para_cards:
                            kbm.add_knowledge_points_batch(kb_name, para_cards)
                            st.info(f"已导入 {len(para_cards)} 个段落作为知识点")
                            os.unlink(tmp_path)
                            st.rerun()
                    st.error("未能提取到有效内容")



# ====== 刷题页 ======

def tab_quiz(kb_name):
    st.subheader("✏️ 刷题模式")
    kps = dm.load_knowledge_base(kb_name)
    outline_nodes = dm.load_outline(kb_name).get("nodes", [])

    if not kps:
        st.info("知识库为空，请先导入知识点")
        return

    q_type = st.radio("选择题型", ["选择题", "判断题", "简答题", "论述题", "混合"], horizontal=True, key="quiz_type_selector")
    st.session_state.quiz_mode = q_type

    col1, col2 = st.columns(2)
    with col1:
        q_range = st.selectbox("出题范围", ["全部", "当前章节", "待复习（到期）"])
    with col2:
        q_count = st.number_input("题目数量", min_value=1, max_value=len(kps), value=min(10, len(kps)))

    if q_range == "当前章节" and st.session_state.selected_outline_id:
        outline_id = st.session_state.selected_outline_id
        matched_ids = _get_descendant_ids(outline_nodes, outline_id) if outline_nodes else {outline_id}
        selected_kps = [
            kp for kp in kps if any(
                ref in matched_ids or str(ref).startswith(f"{outline_id}-")
                for ref in kp.get("outline_ref", [])
            )
        ]
        if not selected_kps:
            st.info("当前章节暂无知识点")
            return
    elif q_range == "待复习（到期）":
        selected_kps = sm2.get_due_cards(kps)
        if not selected_kps:
            st.info("暂无待复习的卡片")
            return
    else:
        selected_kps = kps

    if st.button("生成题目", use_container_width=True, type="primary") or st.session_state.quiz_items:
        if not st.session_state.quiz_items:
            api_key = dm.load_api_key()
            items = qe.get_quiz_items_batch(selected_kps, q_type, q_count, api_key)
            if not items:
                st.warning("未能生成题目")
                return
            st.session_state.quiz_items = items
            st.session_state.quiz_index = 0
            st.session_state.quiz_answers = {}
            st.rerun()

        items = st.session_state.quiz_items
        total = len(items)
        idx = st.session_state.quiz_index

        if idx >= total:
            st.success("🎉 全部完成！")
            score = sum(1 for v in st.session_state.quiz_answers.values() if v.get("correct") is True)
            total_ans = sum(1 for v in st.session_state.quiz_answers.values() if v.get("correct") is not None)
            if total_ans > 0:
                st.metric("正确率", f"{score}/{total_ans} ({score/total_ans*100:.0f}%)")
            if st.button("重新开始", use_container_width=True):
                st.session_state.quiz_items = []
                st.session_state.quiz_index = 0
                st.session_state.quiz_answers = {}
                st.rerun()
            return

        item = items[idx]
        st.progress((idx) / total, text=f"{idx + 1}/{total}")
        st.markdown("---")
        st.markdown(f"### {item['type']}")
        st.markdown(f"**{item['question']}**")

        user_answered = idx in st.session_state.quiz_answers

        if item["type"] == "选择题":
            opts = item.get("options", [])
            selected = st.radio("选择答案", opts, index=None, key=f"quiz_{idx}", disabled=user_answered)
            if st.button("提交", key=f"submit_{idx}", disabled=user_answered, use_container_width=True):
                if selected is not None:
                    sel_idx = opts.index(selected)
                    result = qe.check_answer(item, sel_idx)
                    st.session_state.quiz_answers[idx] = result
                    st.rerun()

        elif item["type"] == "判断题":
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("✅ 正确", key=f"tf_true_{idx}", disabled=user_answered, use_container_width=True):
                    result = qe.check_answer(item, True)
                    st.session_state.quiz_answers[idx] = result
                    st.rerun()
            with col_b:
                if st.button("❌ 错误", key=f"tf_false_{idx}", disabled=user_answered, use_container_width=True):
                    result = qe.check_answer(item, False)
                    st.session_state.quiz_answers[idx] = result
                    st.rerun()

        elif item["type"] == "简答题":
            if st.button("📖 显示答案", key=f"reveal_{idx}", use_container_width=True):
                st.session_state.quiz_answers[idx] = {"correct": None, "correct_answer": item["answer"]}
                st.rerun()

        elif item["type"] == "论述题":
            st.markdown(f"**答案：**\n\n{item['answer']}")
            rating = st.slider("掌握程度", 1, 5, 3, key=f"rating_{idx}")
            if st.button("记录", key=f"rate_{idx}", use_container_width=True):
                card = next((kp for kp in kps if kp.get("id") == item.get("kp_id")), None)
                if card:
                    new_rep, new_ef, new_interval = sm2.calculate_sm2(
                        rating, card.get("repetitions", 0),
                        card.get("ease_factor", 2.5), card.get("interval", 0)
                    )
                    next_review = sm2.get_next_review_date(card.get("last_review", ""), new_interval)
                    status = sm2.get_status_by_sm2(new_rep, new_ef, new_interval)
                    import datetime
                    kbm.update_knowledge_point(kb_name, card["id"], {
                        "repetitions": new_rep, "ease_factor": new_ef,
                        "interval": new_interval, "next_review": next_review,
                        "last_review": datetime.date.today().strftime("%Y-%m-%d"),
                        "status": status
                    })
                st.session_state.quiz_answers[idx] = {"correct": None}
                st.rerun()

        if user_answered:
            ans = st.session_state.quiz_answers[idx]
            if ans.get("correct") is True:
                st.success("✅ 正确！")
            elif ans.get("correct") is False:
                st.error(f"❌ 错误！正确答案：{ans.get('correct_answer', '')}")
                if ans.get("explanation"):
                    st.info(f"解析：{ans['explanation']}")
            elif item["type"] == "简答题":
                st.info(f"**参考答案：**\n{ans.get('correct_answer', '')}")
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    if st.button("😞 忘了", key=f"forget_{idx}", use_container_width=True):
                        _update_sm2(kb_name, kps, item, 1)
                        st.session_state.quiz_index = idx + 1
                        st.rerun()
                with col_b:
                    if st.button("🤔 有点印象", key=f"partial_{idx}", use_container_width=True):
                        _update_sm2(kb_name, kps, item, 3)
                        st.session_state.quiz_index = idx + 1
                        st.rerun()
                with col_c:
                    if st.button("😊 记住了", key=f"remember_{idx}", use_container_width=True):
                        _update_sm2(kb_name, kps, item, 5)
                        st.session_state.quiz_index = idx + 1
                        st.rerun()

            st.markdown("---")
            if st.button("下一题 →", key=f"next_{idx}", use_container_width=True):
                st.session_state.quiz_index = idx + 1
                st.rerun()

        if st.button("重新出题", use_container_width=True):
            st.session_state.quiz_items = []
            st.session_state.quiz_index = 0
            st.session_state.quiz_answers = {}
            st.rerun()


def _update_sm2(kb_name, kps, item, rating):
    card = next((kp for kp in kps if kp.get("id") == item.get("kp_id")), None)
    if card:
        new_rep, new_ef, new_interval = sm2.calculate_sm2(
            rating, card.get("repetitions", 0),
            card.get("ease_factor", 2.5), card.get("interval", 0)
        )
        kbm.update_knowledge_point(kb_name, card["id"], {
            "repetitions": new_rep, "ease_factor": new_ef,
            "interval": new_interval,
            "next_review": sm2.get_next_review_date("", new_interval),
            "status": sm2.get_status_by_sm2(new_rep, new_ef, new_interval)
        })


# ====== 闪卡页 ======

def tab_flashcard(kb_name):
    st.subheader("🎯 闪卡背诵")
    kps = dm.load_knowledge_base(kb_name)
    if not kps:
        st.info("知识库为空")
        return

    due_kps = sm2.get_due_cards(kps)
    if not due_kps:
        st.success("🎉 所有卡片已复习完！今天暂无待复习卡片。")
        due_kps = kps

    idx = st.session_state.flashcard_index
    if idx >= len(due_kps):
        idx = 0
        st.session_state.flashcard_index = 0

    card = due_kps[idx]
    st.progress((idx + 1) / len(due_kps), text=f"{idx + 1}/{len(due_kps)}")
    st.markdown("---")
    st.markdown(f"### ❓ {card.get('question', '')}")
    st.markdown("---")

    if st.session_state.flashcard_revealed:
        st.markdown(f"**📖 答案：**\n\n{card.get('answer', '')}")
        if card.get("source_text"):
            st.caption(f"📝 原文引用：{card['source_text'][:200]}")
        st.markdown("**你记住了吗？**")
        cols = st.columns(6)
        ratings = [
            (0, "😞", "完全忘记"), (1, "😰", "很模糊"), (2, "🤔", "不太熟"),
            (3, "🙂", "还可以"), (4, "😊", "记住了"), (5, "🌟", "非常熟")
        ]
        for col, (r, emoji, label) in zip(cols, ratings):
            with col:
                if st.button(f"{emoji}\n{r}", key=f"flash_rating_{r}_{idx}", use_container_width=True):
                    new_rep, new_ef, new_interval = sm2.calculate_sm2(
                        r, card.get("repetitions", 0),
                        card.get("ease_factor", 2.5), card.get("interval", 0)
                    )
                    next_review = sm2.get_next_review_date(card.get("last_review", ""), new_interval)
                    status = sm2.get_status_by_sm2(new_rep, new_ef, new_interval)
                    import datetime
                    kbm.update_knowledge_point(kb_name, card["id"], {
                        "repetitions": new_rep, "ease_factor": new_ef,
                        "interval": new_interval, "next_review": next_review,
                        "last_review": datetime.date.today().strftime("%Y-%m-%d"),
                        "status": status
                    })
                    st.session_state.flashcard_index = idx + 1
                    st.session_state.flashcard_revealed = False
                    st.rerun()
    else:
        if st.button("👆 显示答案", use_container_width=True, type="primary"):
            st.session_state.flashcard_revealed = True
            st.rerun()


# ====== 统计页 ======

def tab_stats(kb_name):
    st.subheader("📊 学习统计")
    kps = dm.load_knowledge_base(kb_name)
    stats = sm2.get_stats(kps)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("总知识点", stats["total"])
    with col2:
        st.metric("待复习", stats["due"])
    with col3:
        st.metric("学习中", stats["learning"])
    with col4:
        st.metric("已掌握", stats["mastered"])

    outline_data = dm.load_outline(kb_name)
    nodes = outline_data.get("nodes", [])
    if nodes:
        st.subheader("📋 各章节进度")
        for node in nodes:
            outline_id = node["id"]
            matched_ids = _get_descendant_ids(nodes, outline_id)
            node_kps = [
                kp for kp in kps if any(
                    ref in matched_ids or str(ref).startswith(f"{outline_id}-")
                    for ref in kp.get("outline_ref", [])
                )
            ]
            if node_kps:
                mastered = sum(1 for kp in node_kps if kp.get("status") == "mastered")
                progress = mastered / len(node_kps)
                st.progress(progress, text=f"{node['title']} ({mastered}/{len(node_kps)})")


# ====== 设置页 ======

def tab_settings():
    st.subheader("⚙️ 设置")

    st.markdown("### 🤖 DeepSeek API 配置")
    api_key = dm.load_api_key()
    new_key = st.text_input("API Key", value=api_key, type="password",
                            help="填入 DeepSeek API Key 以启用智能解析功能")
    if st.button("保存 API Key", use_container_width=True):
        dm.save_api_key(new_key)
        st.success("API Key 已保存")

    st.divider()
    st.markdown("### 💾 导出数据")
    kb_name = st.session_state.current_kb
    if st.button("导出当前知识库为 JSON", use_container_width=True):
        import datetime, tempfile
        export_path = os.path.join(tempfile.gettempdir(), f"{kb_name}_export_{datetime.date.today()}.json")
        count = dm.export_knowledge_base(kb_name, export_path)
        st.success(f"导出成功！共 {count} 条知识点")
        st.info(f"文件位置：{export_path}")

    st.divider()
    st.markdown("### ℹ️ 关于")
    st.caption("知识背诵系统 v1.0 — 基于 Streamlit + SM-2 间隔重复算法 + DeepSeek API")


if __name__ == "__main__":
    main()
