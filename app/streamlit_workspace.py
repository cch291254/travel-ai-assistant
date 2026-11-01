"""旅行社 Copilot 工作台（下一阶段前端原型）。

与 app/streamlit.py 并存，可分别启动比较：
    streamlit run app/streamlit_workspace.py --server.port 8502

真实接口：聊天、会话、草稿、生成草案、方案和费用核算（见 workspace_api）。
"""
from datetime import datetime, timedelta
from decimal import Decimal

import streamlit as st

from app import workspace_api as api
from app.workspace_plan import (
    LODGING_MODES,
    PLAN_STATUSES,
    PRICE_CATEGORIES,
    STATUS_BADGE_COLORS,
    build_quote_input,
    draft_from_plan,
    draft_to_json,
    empty_draft,
    find_missing_prices,
    find_route_items,
    new_day,
    new_room,
    new_spot,
    restore_draft,
    serialize,
)



st.set_page_config(
    page_title="旅行社 Copilot 工作台",
    page_icon=":material/travel_explore:",
    layout="wide",
    initial_sidebar_state="auto",
)

# 统一样式：只调整间距、字号和聊天气泡，颜色跟随 Streamlit 明暗主题。
st.markdown(
    """
    <style>
    .block-container { max-width: 96rem; padding-top: 1.5rem; padding-bottom: 3rem; }
    [data-testid="stMainBlockContainer"] h1 { font-size: 1.6rem; letter-spacing: -0.02em; }
    [data-testid="stMainBlockContainer"] h5 { font-size: 1rem; margin-top: 0.6rem; }
    [data-testid="stChatMessage"] { border-radius: 0.8rem; padding: 0.9rem 1rem; }
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
        background: color-mix(in srgb, currentColor 5%, transparent);
    }
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
        background: transparent;
    }
    [data-testid="stChatMessage"] p,
    [data-testid="stChatMessage"] li { line-height: 1.75; }
    [data-testid="stChatMessage"] table { width: 100%; font-size: 0.95rem; }
    [data-testid="stChatMessage"] th,
    [data-testid="stChatMessage"] td { padding: 0.55rem 0.75rem; vertical-align: top; }
    [data-testid="stText"] { font-family: inherit; line-height: 1.65; overflow-wrap: anywhere; }
    [data-testid="stMetricValue"] { font-size: 1.3rem; }
    [data-testid="stSidebar"] button[kind="tertiary"] > div { justify-content: flex-start; }
    [data-testid="stSidebar"] button[kind="tertiary"] p { text-align: left; }
    @media (max-width: 768px) {
        .block-container { padding-top: 1rem; padding-inline: 1rem; }
        [data-testid="stChatMessage"] { padding: 0.75rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

USER_AVATAR = ":material/person:"
ASSISTANT_AVATAR = ":material/travel_explore:"
WEEKDAYS = "一二三四五六日"
# 每个状态能做的操作：(目标状态, 按钮文字, 图标, 成功提示)。流转是否合法仍由后端判断。
STATUS_ACTIONS = {
    "draft": [("pending", "标记为待确认", ":material/send:", "已标记为待确认")],
    "pending": [
        ("confirmed", "标记为已确认", ":material/check_circle:", "方案已确认"),
        ("draft", "退回草案", ":material/undo:", "已退回草案，可以继续修改"),
    ],
    "confirmed": [],
}
ss = st.session_state


# ---------- 通用小工具 ----------

def md_escape(text):
    """员工输入、网页标题放进 Markdown 前转义，避免被当成格式或指令渲染。"""
    special = set("\\`*_{}[]()#+-.!|~<>:$")
    return "".join("\\" + char if char in special else char for char in str(text))


def money(value):
    return "未提供" if value is None else f"¥{Decimal(str(value)):,.2f}"


def status_badge(status):
    return f":{STATUS_BADGE_COLORS[status]}-badge[{PLAN_STATUSES[status]}]"


def display_time(utc_text):
    """数据库保存的是 UTC 时间，显示时换算成北京时间。"""
    return (datetime.fromisoformat(utc_text) + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")


def day_label(draft, day_index):
    if draft["start_date"] is None:
        return ""
    day = draft["start_date"] + timedelta(days=day_index)
    return f" · {day.month}月{day.day}日 周{WEEKDAYS[day.weekday()]}"


# ---------- 页面状态 ----------
#这进行了页面统一展示
def init_state():
    defaults = {
        "user_select": next(iter(api.DEMO_USERS)),
        "conversation_id": None,
        "messages": [],
        "history_loaded": False,
        "chat_error": None,
        "draft": None,
        "baseline": None,
        "draft_origin": None,
        "draft_rev": 0,
        "quote_result": None,
        "quote_error": None,
        "preview_plan_id": None,
        "pending_action": None,
        "reopened": False,
        "sidebar_error": None,
        "autosaved": None,
        "autosave_error": None,
    }
    for key, value in defaults.items():
        ss.setdefault(key, value)
    


def wkey(*parts):
    """控件键带上草案版本号：换一份草案时自动换一组控件，旧值不会串到新草案。"""
    return f"w{ss.draft_rev}_" + "_".join(str(part) for part in parts)


def bind(key, value):
    """首次渲染或控件状态被清理后，用草案中的值初始化控件。"""
    if key not in ss:
        ss[key] = value
    return key

#传入令牌
def current_token():
    return api.DEMO_USERS[ss.user_select]


def load_draft(draft, origin):
    ss.draft = draft
    ss.baseline = serialize(draft)
    ss.draft_origin = origin
    ss.draft_rev += 1
    ss.quote_result = None
    ss.quote_error = None


def draft_changed():
    return ss.draft is not None and serialize(ss.draft) != ss.baseline


def needs_discard_confirmation():
    """有修改，或已打开的草案尚未保存时，离开前需要确认；生成的草案会自动保存到会话。"""
    if ss.draft is None:
        return False
    return draft_changed() or (ss.draft["plan_id"] is None and ss.draft_origin not in {"blank", "autosaved", "generated"})


def quote_state():
    if ss.quote_result is None:
        return "none"
    if ss.quote_result["signature"] != serialize(build_quote_input(ss.draft)):
        return "stale"
    return "fresh"


def reset_conversation():
    """新建对话、切换用户、打开其他会话时调用：清空聊天、草案和选中的方案。"""
    ss.conversation_id = None
    ss.messages = []
    ss.history_loaded = False
    ss.chat_error = None
    ss.draft = None
    ss.baseline = None
    ss.draft_origin = None
    ss.draft_rev += 1
    ss.quote_result = None
    ss.quote_error = None
    ss.preview_plan_id = None
    ss.pending_action = None
    ss.reopened = False
    ss.sidebar_error = None
    ss.autosaved = None
    ss.autosave_error = None


def notify(kind, text):
    ss.notice = (kind, text)


# ---------- 需要确认的操作（会放弃当前草案） ----------

def request_action(action):
    if needs_discard_confirmation():
        ss.pending_action = action
    else:
        run_action(action)


def run_action(action):
    ss.pending_action = None
    kind = action["type"]

    if kind == "new_conversation":
        reset_conversation()
        notify("info", "已新建对话")

    elif kind == "open_conversation":
        reset_conversation()
        ss.conversation_id = action["conversation_id"]
        ss.messages = action["messages"]
        ss.history_loaded = True
        restore_conversation_draft(action["conversation_id"])
        notify("success", f"已打开会话 #{action['conversation_id']}")

    elif kind == "continue_plan":
        result = api.fetch_plan(action["plan_id"], current_token())
        if not result["ok"]:
            notify("error", result["error"])
            return
        load_draft(draft_from_plan(result["data"]), origin="plan")
        ss.preview_plan_id = None
        ss.reopened = True
        notify("success", f"已打开方案 #{action['plan_id']} 继续编辑")

    elif kind == "generate_draft":
        generate_draft_from_chat()

    elif kind == "apply_generated":
        apply_generated_draft(action["draft"])


def generate_draft_from_chat():
    """读取这个会话的全部聊天记录，由模型整理成草案；员工核对后才保存。"""
    with st.spinner("正在整理聊天内容……"):
        result = api.generate_draft(ss.conversation_id, current_token())
    if not result["ok"]:
        notify("error", result["error"])
        return
    apply_generated_draft(result["data"]["draft"])


def apply_generated_draft(generated):
    current = ss.draft
    draft = restore_draft(generated)
    if current is None:
        load_draft(draft, origin="generated")
    else:
        # 重新生成不换方案：保留编号和版本，保存时才能生成新版本；旧基线用来显示“有未保存修改”。
        baseline = ss.baseline
        origin = ss.draft_origin
        for key in ("plan_id", "version", "status"):
            draft[key] = current[key]
        load_draft(draft, origin=origin)
        ss.baseline = baseline
    notify("success", "已整理成草案，请核对内容；空着的价格是聊天里没有确定的")


ACTION_TEXT = {
    "new_conversation": "新建对话",
    "open_conversation": "打开其他会话",
    "continue_plan": "打开另一份方案",
}


def render_pending_action():
    action = ss.pending_action
    if action is None:
        return
    with st.container(border=True):
        if action["type"] in {"generate_draft", "apply_generated"}:
            st.markdown(":orange[**重新生成会覆盖当前页面的内容**] · 你的手动修改会被替换，确认后才生效。")
        else:
            st.markdown(
                f":orange[**当前方案尚未保存**] · {ACTION_TEXT[action['type']]}将放弃这些修改。"
                "如需保留，请先取消并点击“保存方案”。"
            )
        with st.container(horizontal=True):
            st.button("放弃修改并继续", type="primary", on_click=run_action, args=(action,))
            st.button("取消", on_click=lambda: ss.update(pending_action=None))


# ---------- 方案结构编辑（回调里只调整结构，文字内容由控件写回） ----------

def find_day(day_id):
    return next(day for day in ss.draft["days"] if day["id"] == day_id)


def add_day():
    ss.draft["days"].append(new_day())


def remove_day(day_id):
    ss.draft["days"] = [day for day in ss.draft["days"] if day["id"] != day_id]


def add_spot(day_id):
    find_day(day_id)["spots"].append(new_spot())


def remove_spot(day_id, spot_id):
    day = find_day(day_id)
    day["spots"] = [spot for spot in day["spots"] if spot["id"] != spot_id]


def move_spot(day_id, spot_id, offset):
    spots = find_day(day_id)["spots"]
    index = next(i for i, spot in enumerate(spots) if spot["id"] == spot_id)
    target = index + offset
    if 0 <= target < len(spots):
        spots[index], spots[target] = spots[target], spots[index]


def add_room():
    nights = max(len(ss.draft["days"]) - 1, 1)
    ss.draft["rooms"].append(new_room(nights=nights))


def remove_room(room_id):
    ss.draft["rooms"] = [room for room in ss.draft["rooms"] if room["id"] != room_id]


def add_manual_item(input_key):
    text = ss.get(input_key, "").strip()
    if text:
        ss.draft["manual_items"].append(text)
    ss[input_key] = ""


def remove_manual_item(index):
    ss.draft["manual_items"].pop(index)


def create_blank_draft():
    draft = empty_draft()
    draft["conversation_id"] = ss.conversation_id
    load_draft(draft, origin="blank")


def save_current_plan():
    """只在员工点击“保存方案”时执行；聊天不会自动生成方案记录。"""
    draft = ss.draft
    if not draft["name"].strip():
        notify("error", "请先填写方案名称，再保存")
        return
    if draft["plan_id"] is not None and not draft_changed():
        notify("info", "方案没有修改，不需要保存")
        return
    if ss.conversation_id is not None:
        draft["conversation_id"] = ss.conversation_id

    payload = draft_to_json(draft)
    if draft["plan_id"] is None:
        result = api.create_plan(draft["name"].strip(), payload, draft["conversation_id"], current_token())
    else:
        result = api.save_plan_version(
            draft["plan_id"], draft["name"].strip(), payload, draft["version"], current_token(),
        )
    if not result["ok"]:
        notify("error", result["error"])
        return

    # 版本号以后端返回为准，下一次保存要用它作为 base_version。新版本的状态都是 draft。
    draft["plan_id"] = result["data"]["plan_id"]
    draft["version"] = result["data"]["version"]
    draft["status"] = "draft"
    ss.baseline = serialize(draft)
    ss.draft_origin = "plan"
    notify("success", f"已保存方案 #{draft['plan_id']} · v{draft['version']}")

def change_status(new_status, success_text):
    """状态改在当前版本上，不生成新版本；版本号过期或价格不全时由后端拒绝。"""
    draft = ss.draft
    result = api.change_plan_status(draft["plan_id"], new_status, draft["version"], current_token())
    if not result["ok"]:
        notify("error", result["error"])
        return
    draft["status"] = result["data"]["status"]
    ss.baseline = serialize(draft)
    notify("success", success_text)


def render_status_actions(draft):
    """方案保存后才有状态流转；有未保存修改时先保存，避免确认的内容和页面不一致。"""
    if draft is None or draft["plan_id"] is None or not STATUS_ACTIONS[draft["status"]]:
        return
    if draft_changed():
        st.caption("有未保存修改，保存后才能更改状态。")
        return
    with st.container(horizontal=True):
        for new_status, label, icon, success_text in STATUS_ACTIONS[draft["status"]]:
            st.button(
                label, key=f"status_{new_status}", icon=icon,
                on_click=change_status, args=(new_status, success_text),
            )


def detach_plan(draft):
    """方案已被删除时，页面内容保留下来，再次保存会新建方案。"""
    draft.update(plan_id=None, version=0, status="draft")


def delete_plan(plan_id):
    result = api.delete_plan(plan_id, current_token())
    if not result["ok"]:
        notify("error", result["error"])
        return
    ss.preview_plan_id = None
    if ss.draft is not None and ss.draft["plan_id"] == plan_id:
        detach_plan(ss.draft)
        ss.baseline = serialize(ss.draft)
    notify("success", f"已删除方案 #{plan_id}")


def copy_plan(plan_id):
    result = api.copy_plan(plan_id, current_token())
    if not result["ok"]:
        notify("error", result["error"])
        return
    ss.preview_plan_id = result["data"]["plan_id"]
    notify("success", f"已复制为方案 #{result['data']['plan_id']}")


def restore_conversation_draft(conversation_id):
    """打开会话时取回自动保存的草稿；关联方案还在时，用方案内容判断有没有未保存修改。"""
    result = api.fetch_draft(conversation_id, current_token())
    if not result["ok"]:
        notify("error", result["error"])
        return
    saved = result["data"]["draft"]
    if saved is None:
        return

    draft = restore_draft(saved)
    plan_baseline = None
    if draft["plan_id"] is not None:
        plan_result = api.fetch_plan(draft["plan_id"], current_token())
        if plan_result["ok"]:
            plan_baseline = serialize(draft_from_plan(plan_result["data"]))
        else:
            detach_plan(draft)

    load_draft(draft, origin="autosaved")
    if plan_baseline is not None:
        ss.baseline = plan_baseline
    ss.autosaved = serialize(draft)


def autosave_draft():
    """有会话时把草案存到这个会话；内容没变不发请求。放在页面最后，能拿到本次所有输入。"""
    if ss.conversation_id is None or ss.draft is None:
        return
    snapshot = serialize(ss.draft)
    if snapshot == ss.autosaved:
        return
    result = api.save_draft(ss.conversation_id, draft_to_json(ss.draft), current_token())
    ss.autosave_error = None if result["ok"] else result["error"]
    if result["ok"]:
        ss.autosaved = snapshot


# ---------- 聊天区域（真实接口） ----------

def render_sources(message):
    """只展示接口返回的引用：标题、来源类型、链接和原文。"""
    citations = message.get("citations") or []
    if not citations:
        return

    evidence = {item.get("chunk_id"): item for item in message.get("evidence") or []}
    st.caption(f"参考来源 · {len(citations)} 条")

    for citation in citations:
        metadata = citation.get("metadata") or {}
        title = metadata.get("source_title") or "未提供资料标题"
        is_web = metadata.get("source_type") == "web"
        source_kind = "网页资料" if is_web else "内部资料"
        short_title = title if len(title) <= 40 else title[:40] + "…"

        with st.expander(f"\\[{citation.get('citation_id')}\\] {md_escape(short_title)} · {source_kind}"):
            st.markdown(f"**{md_escape(title)}**")
            if is_web:
                st.caption(f"网页资料 · {md_escape(metadata.get('content_type', '网页内容'))}")
                if metadata.get("url"):
                    st.link_button("打开原网页", metadata["url"], icon=":material/open_in_new:")
            else:
                details = [f"来源编号 {metadata.get('source_id', '未提供')}"]
                if metadata.get("section_path"):
                    details.append(f"章节 {metadata['section_path']}")
                if metadata.get("valid_from") or metadata.get("valid_until"):
                    details.append(
                        f"有效期 {metadata.get('valid_from', '未提供')} 至 {metadata.get('valid_until', '未提供')}"
                    )
                st.caption(md_escape(" · ".join(details)))

            chunk = evidence.get(citation.get("chunk_id"))
            if chunk is None:
                st.caption("接口未返回该引用的原文。")
                continue
            content = chunk.get("content", "")
            is_long = len(content) > 600 or content.count("\n") > 10
            st.caption(f"原文 · {len(content)} 字符")
            # 长原文限制高度，在框内滚动查看；st.text 不会执行网页中的 HTML。
            with st.container(height=260 if is_long else "content", border=is_long):
                st.text(content)


def render_message(message):
    avatar = USER_AVATAR if message["role"] == "user" else ASSISTANT_AVATAR
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])
        if message.get("needs_clarification"):
            st.caption("需要补充信息，请在下方继续输入。")
        render_sources(message)


def clear_chat_error():
    ss.chat_error = None


def retry_failed_question():
    ss.retry_question = ss.chat_error["question"]
    ss.chat_error = None


def submit_question(question, box):
    """提问成功后才把一问一答写入历史；失败只记录错误，不累积用户提问。"""
    with box:
        with st.chat_message("user", avatar=USER_AVATAR):
            st.markdown(question)
        with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
            with st.spinner("正在查询资料并整理回答…"):
                result = api.send_chat(question, ss.conversation_id, current_token())

    if result["ok"]:
        data = result["data"]
        ss.conversation_id = data["conversation_id"]
        ss.messages.append({"role": "user", "content": question})
        ss.messages.append({
            "role": "assistant",
            "content": data["answer"],
            "citations": data["citations"],
            "evidence": data["evidence"],
            "needs_clarification": data["needs_clarification"],
        })
        # 聊天里要求整理草案：页面有未保存修改时先确认，不直接覆盖。
        if data["generated_draft"]:
            if draft_changed():
                ss.pending_action = {"type": "apply_generated", "draft": data["generated_draft"]}
            else:
                apply_generated_draft(data["generated_draft"])
        elif data["draft_error"]:
            notify("error", f"草案没有整理成功：{data['draft_error']}")
    else:
        ss.chat_error = {"question": question, "message": result["error"]}
    st.rerun()


def render_chat():
    title = "新对话" if ss.conversation_id is None else f"会话 #{ss.conversation_id}"
    st.markdown(f"##### 对话 · {title}")

    box = st.container(height=600, border=True, autoscroll=True)
    with box:
        if ss.history_loaded:
            st.caption("已从后端读取历史消息；历史消息不包含引用原文。")
        if not ss.messages and ss.chat_error is None:
            st.markdown("**从一条旅行需求开始**")
            st.caption("查资料：杭州有哪些适合三天两晚的路线？")
            st.caption("算费用：2位成人、1位儿童，成人餐费每人300元，儿童150元，帮我核算。")
        for message in ss.messages:
            render_message(message)

        if ss.chat_error is not None:
            st.error(f"本次请求未完成：{ss.chat_error['message']}", icon=":material/error:")
            st.caption(f"未加入对话历史的提问：{md_escape(ss.chat_error['question'][:80])}")
            st.button(
                "重新发送", icon=":material/refresh:", on_click=retry_failed_question,
                key="retry_question_button",
            )

    question = st.chat_input(
        "输入旅行需求，或继续补充、调整条件…",
        max_chars=1000,  # 与后端 1000 字符限制一致
        key="chat_box",
        on_submit=clear_chat_error,
    )
    if not question:
        question = ss.pop("retry_question", None)
    if question:
        submit_question(question, box)


# ---------- 当前方案编辑 ----------

def render_draft_empty_state():
    st.markdown("当前会话还没有方案草案。")
    st.caption("先在左侧聊好线路和价格，再整理成草案并调整；只有点击“保存方案”才会进入方案库。")
    with st.container(horizontal=True):
        if st.button(
            "生成路线草案", type="primary", icon=":material/auto_awesome:",
            key="generate_draft", disabled=ss.conversation_id is None,
        ):
            run_action({"type": "generate_draft"})
            st.rerun()
        st.button("新建空白草案", icon=":material/note_add:", on_click=create_blank_draft, key="create_blank")
    if ss.conversation_id is None:
        st.caption("发送第一条消息后，就可以把聊天内容整理成草案。")


def render_day(draft, day_index, day):
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"**第{day_index + 1}天**{day_label(draft, day_index)}", width="stretch")
            st.button(
                "删除这天", icon=":material/delete:", type="tertiary",
                key=wkey("remove_day", day["id"]), on_click=remove_day, args=(day["id"],),
                disabled=len(draft["days"]) == 1,
            )

        # 每个景点一行：名称、上移、下移、删除；控件键跟随景点编号，调整顺序时内容不会串行。
        for spot_index, spot in enumerate(day["spots"]):
            with st.container(horizontal=True, vertical_alignment="center", gap="small"):
                spot["name"] = st.text_input(
                    f"第{day_index + 1}天第{spot_index + 1}个景点",
                    key=bind(wkey("spot", spot["id"]), spot["name"]),
                    placeholder="景点名称", label_visibility="collapsed", width="stretch",
                )
                st.button(
                    ":material/arrow_upward:", key=wkey("up", spot["id"]), help="上移",
                    on_click=move_spot, args=(day["id"], spot["id"], -1), disabled=spot_index == 0,
                )
                st.button(
                    ":material/arrow_downward:", key=wkey("down", spot["id"]), help="下移",
                    on_click=move_spot, args=(day["id"], spot["id"], 1),
                    disabled=spot_index == len(day["spots"]) - 1,
                )
                st.button(
                    ":material/close:", key=wkey("remove_spot", spot["id"]), help="删除景点",
                    on_click=remove_spot, args=(day["id"], spot["id"]),
                )
        st.button(
            "添加景点", icon=":material/add:", type="tertiary",
            key=wkey("add_spot", day["id"]), on_click=add_spot, args=(day["id"],),
        )

        hotel_col, notes_col = st.columns([1, 1.4])
        day["hotel"] = hotel_col.text_input(
            "住宿", key=bind(wkey("hotel", day["id"]), day["hotel"]), placeholder="酒店或区域",
        )
        day["notes"] = notes_col.text_input(
            "备注", key=bind(wkey("notes", day["id"]), day["notes"]), placeholder="预约、接送、时间安排等",
        )


def auto_pending_items(draft):
    """根据当前输入自动列出的待确认事项（不含员工手动补充）。"""
    items = find_route_items(draft) + find_missing_prices(draft)
    state = quote_state()
    if state == "none":
        items.append("费用尚未核算")
    elif state == "stale":
        items.append("费用或人数已修改，需重新核算")
    return items


def render_pending_items(draft):
    st.markdown("##### 待确认事项")
    items = auto_pending_items(draft)

    for item in items:
        st.markdown(f"- {md_escape(item)}")

    # 员工手动补充的事项，可逐条删除。
    for index, text in enumerate(draft["manual_items"]):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"- {md_escape(text)} :gray-badge[员工补充]", width="stretch")
            st.button(
                ":material/close:", key=wkey("remove_item", index), help="删除事项",
                on_click=remove_manual_item, args=(index,),
            )
    if not items and not draft["manual_items"]:
        st.caption("暂无待确认事项。")

    input_key = wkey("new_item")
    with st.container(horizontal=True, vertical_alignment="bottom"):
        st.text_input("补充事项", key=input_key, placeholder="例如：与客户确认返程时间", width="stretch")
        st.button("添加", key=wkey("add_item"), on_click=add_manual_item, args=(input_key,))


def render_plan_editor():
    draft = ss.draft
    if draft is None:
        render_draft_empty_state()
        return

    st.markdown("##### 基本信息")
    name_col, dest_col = st.columns([1.4, 1])
    draft["name"] = name_col.text_input(
        "方案名称", key=bind(wkey("name"), draft["name"]), placeholder="例如：杭州三天两晚亲子线",
    )
    draft["destination"] = dest_col.text_input(
        "目的地", key=bind(wkey("destination"), draft["destination"]),
    )

    date_col, adult_col, child_col = st.columns([1.4, 1, 1])
    draft["start_date"] = date_col.date_input(
        "出发日期", key=bind(wkey("start_date"), draft["start_date"]), value=None, format="YYYY-MM-DD",
    )
    draft["adults"] = adult_col.number_input(
        "成人", key=bind(wkey("adults"), draft["adults"]), min_value=1, max_value=50, step=1,
    )
    draft["children"] = child_col.number_input(
        "儿童", key=bind(wkey("children"), draft["children"]), min_value=0, max_value=50, step=1,
    )

    st.markdown(f"##### 每日路线 · {len(draft['days'])} 天")
    for day_index, day in enumerate(draft["days"]):
        render_day(draft, day_index, day)
    st.button("增加一天", icon=":material/add:", key=wkey("add_day"), on_click=add_day)

    render_pending_items(draft)


# ---------- 费用区域 ----------

def render_price_inputs(draft, side, people):
    """一组单人价格输入：留空=未提供，0=明确为0元。"""
    is_child = side == "child"
    disabled = is_child and people == 0
    for key, label in PRICE_CATEGORIES:
        draft["prices"][side][key] = st.number_input(
            label,
            key=bind(wkey("price", side, key), draft["prices"][side][key]),
            value=None, min_value=0.0, step=10.0, format="%.2f",
            placeholder="无儿童" if disabled else "未提供",
            disabled=disabled,
        )


def render_lodging(draft):
    st.markdown("##### 住宿（整组）")
    draft["lodging_mode"] = st.radio(
        "住宿", options=list(LODGING_MODES), format_func=LODGING_MODES.get,
        key=bind(wkey("lodging_mode"), draft["lodging_mode"]), horizontal=True,
        label_visibility="collapsed",
    )
    if draft["lodging_mode"] != "items":
        return

    for room in draft["rooms"]:
        type_col, rooms_col, nights_col, price_col, action_col = st.columns(
            [1.5, 0.75, 0.75, 1.25, 0.55], vertical_alignment="bottom",
        )
        room["room_type"] = type_col.text_input(
            "房型", key=bind(wkey("room_type", room["id"]), room["room_type"]), placeholder="如 标准双床房",
        )
        room["rooms"] = rooms_col.number_input(
            "间数", key=bind(wkey("rooms", room["id"]), room["rooms"]), min_value=1, max_value=50, step=1,
        )
        room["nights"] = nights_col.number_input(
            "晚数", key=bind(wkey("nights", room["id"]), room["nights"]), min_value=1, max_value=30, step=1,
        )
        room["room_night_price"] = price_col.number_input(
            "每间每晚（元）", key=bind(wkey("room_price", room["id"]), room["room_night_price"]),
            value=None, min_value=0.0, step=50.0, format="%.2f", placeholder="未提供",
        )
        action_col.button(
            ":material/close:", key=wkey("remove_room", room["id"]), help="删除房型",
            on_click=remove_room, args=(room["id"],),
        )
    st.button("添加房型", icon=":material/add:", type="tertiary", key=wkey("add_room"), on_click=add_room)


def render_quote_result(draft):
    st.markdown("##### 核算结果")
    quote_input = build_quote_input(draft)

    with st.container(horizontal=True, vertical_alignment="center"):
        recalculate = st.button("重新核算", type="primary", icon=":material/calculate:", key=wkey("recalculate"))
        st.caption("仅供核对，不作为正式报价")

    # 重新核算
    if recalculate:
        result = api.calculate_quote(quote_input,current_token())
        if result["ok"]:
            ss.quote_result = {
                "signature": serialize(quote_input),
                "input": quote_input,
                "data": result["data"],
            }
            ss.quote_error = None
        else:
            ss.quote_error = result["error"]
        st.rerun()

    if ss.quote_error:
        st.error(ss.quote_error, icon=":material/error:")

    if ss.quote_result is None:
        st.caption("尚未核算。填写或调整价格后点击“重新核算”。")
    else:
        if quote_state() == "stale":
            st.caption(":orange[费用或人数已修改，以下是上次核算结果，请重新核算。]")
        used = ss.quote_result["input"]
        data = ss.quote_result["data"]

        if used["children"] == 0:
            child_text, child_note = money(data["child_known_total"]), "无儿童"
        elif data["child_known_total"] is None:
            child_text, child_note = "未提供", "儿童价格未提供，不套用成人价"
        else:
            child_text = money(data["child_known_total"])
            child_note = f"单人已知 {money(data['child_costs']['child_base'])} × {used['children']}人"

        if data["accommodation"] is None:
            lodging_text, lodging_note = "未提供", "住宿未提供"
        elif used["room_items"] == []:
            lodging_text, lodging_note = money(data["accommodation"]["known_total"]), "不安排住宿"
        else:
            lodging_text, lodging_note = money(data["accommodation"]["known_total"]), "按间数 × 晚数 × 单价"

        top_left, top_right = st.columns(2)
        top_left.metric("成人小计", money(data["adult_known_total"]))
        top_left.caption(f"单人已知 {money(data['person_costs']['adult_base'])} × {used['adults']}人")
        top_right.metric("儿童小计", child_text)
        top_right.caption(child_note)
        bottom_left, bottom_right = st.columns(2)
        bottom_left.metric("整组住宿", lodging_text)
        bottom_left.caption(lodging_note)
        bottom_right.metric("已知费用合计", money(data["known_total"]))
        bottom_right.caption("仅含已提供价格的项目")

    st.markdown("**缺失项**")
    missing = find_missing_prices(draft)
    if missing:
        for item in missing:
            st.markdown(f"- {md_escape(item)}")
    else:
        st.caption("价格项已全部提供。")


def render_costs():
    draft = ss.draft
    if draft is None:
        st.caption("请先在“当前方案”中生成或新建草案。")
        return

    st.caption("单价按 元/人/整条线路 填写。留空表示未提供，填 0 表示明确为 0 元；儿童价格需单独填写，不会套用成人价。")
    adult_col, child_col = st.columns(2, gap="medium")
    with adult_col:
        st.markdown(f"##### 成人单价 · {draft['adults']} 人")
        render_price_inputs(draft, "adult", draft["adults"])
    with child_col:
        st.markdown(f"##### 儿童单价 · {draft['children']} 人")
        render_price_inputs(draft, "child", draft["children"])

    render_lodging(draft)
    render_quote_result(draft)


# ---------- 方案保存与复用 ----------

def render_plan_preview(plan):
    draft = plan["draft"]
    st.markdown(f"##### 查看方案 · {plan['plan_id']}")
    with st.container(border=True):
        st.markdown(f"**{md_escape(draft['name'])}** {status_badge(draft['status'])} :gray-badge[v{draft['version']}]")
        date_text = draft["start_date"].isoformat() if draft["start_date"] else "日期未定"
        st.caption(
            f"{md_escape(draft['destination'] or '目的地未填')} · {date_text} · "
            f"成人 {draft['adults']} · 儿童 {draft['children']} · 更新于 {plan['updated_at']}"
        )
        for index, day in enumerate(draft["days"], start=1):
            spots = " → ".join(spot["name"] for spot in day["spots"] if spot["name"].strip()) or "未安排景点"
            hotel = f" · 住宿：{day['hotel']}" if day["hotel"].strip() else ""
            st.markdown(f"**第{index}天** {md_escape(spots + hotel)}")

        for side, label in (("adult", "成人"), ("child", "儿童")):
            if side == "child" and draft["children"] == 0:
                continue
            parts = [
                f"{name} {money(draft['prices'][side][key])}" for key, name in PRICE_CATEGORIES
            ]
            st.caption(f"{label}单价：" + " · ".join(parts))

        is_current = ss.draft is not None and ss.draft["plan_id"] == plan["plan_id"]
        with st.container(horizontal=True):
            # 继续编辑：放在所有输入控件之后执行，保证能检查到刚输入的未保存修改。
            if st.button(
                "继续编辑", type="primary", icon=":material/edit:", key=f"continue_{plan['plan_id']}",
                disabled=is_current and not draft_changed(),
            ):
                request_action({"type": "continue_plan", "plan_id": plan["plan_id"]})
                st.rerun()
            st.button(
                "复制", icon=":material/content_copy:", key=f"copy_{plan['plan_id']}",
                on_click=copy_plan, args=(plan["plan_id"],),
            )
            with st.popover("删除", icon=":material/delete:"):
                st.caption("将删除这份方案和全部版本，无法恢复。")
                st.button(
                    "确认删除", type="primary", key=f"delete_{plan['plan_id']}",
                    on_click=delete_plan, args=(plan["plan_id"],),
                )
            st.button("关闭", key="close_preview", on_click=lambda: ss.update(preview_plan_id=None))
        if is_current:
            st.caption("这份方案正在编辑中。")


def render_plan_library():
    result = api.list_plans(current_token())
    if not result["ok"]:
        st.error(result["error"], icon=":material/error:")
        return

    plans = result["data"]["plans"]
    if not plans:
        st.caption("还没有保存的方案。")

    current_id = ss.draft["plan_id"] if ss.draft is not None else None
    for plan in plans:
        with st.container(border=True):
            with st.container(horizontal=True, vertical_alignment="center"):
                editing = " :blue-badge[编辑中]" if plan["id"] == current_id else ""
                st.markdown(
                    f"**{md_escape(plan['title'])}** {status_badge(plan['status'])}{editing}  \n"
                    f":gray[#{plan['id']} · v{plan['current_version']} · 更新于 {display_time(plan['updated_at'])}]",
                    width="stretch",
                )
                st.button(
                    "打开", key=f"open_{plan['id']}", icon=":material/visibility:",
                    on_click=lambda plan_id=plan["id"]: ss.update(preview_plan_id=plan_id),
                )

    if ss.preview_plan_id:
        result = api.fetch_plan(ss.preview_plan_id, current_token())
        if not result["ok"]:
            st.error(result["error"], icon=":material/error:")
            return
        render_plan_preview({
            "plan_id": result["data"]["id"],
            "updated_at": display_time(result["data"]["updated_at"]),
            "draft": draft_from_plan(result["data"]),
        })


def render_plan_header():
    """方案标题、状态和保存按钮；在各编辑控件之后渲染，状态反映本次输入。"""
    draft = ss.draft
    with st.container(horizontal=True, vertical_alignment="center"):
        if draft is None:
            st.markdown("##### 当前方案  \n:gray[尚未创建]", width="stretch")
        else:
            if draft_changed():
                save_badge = ":orange-badge[有未保存修改]"
            elif draft["plan_id"] is None:
                save_badge = ":gray-badge[尚未保存]"
            else:
                save_badge = f":green-badge[已保存 v{draft['version']}]"
            pending_count = len(auto_pending_items(draft)) + len(draft["manual_items"])
            st.markdown(
                f"##### {md_escape(draft['name'].strip() or '未命名方案')}  \n"
                f"{status_badge(draft['status'])} {save_badge} "
                f":gray[{draft['plan_id'] or '新方案'} · 待确认 {pending_count} 项]",
                width="stretch",
            )
        if draft is not None and ss.conversation_id is not None:
            st.button(
                "重新生成", icon=":material/refresh:", key="regenerate_draft",
                on_click=lambda: ss.update(pending_action={"type": "generate_draft"}),
            )
        # 保存：只有明确点击才写入方案库。
        if st.button(
            "保存方案", type="primary", icon=":material/save:", key="save_plan", disabled=draft is None,
        ):
            save_current_plan()
            st.rerun()

    if draft is not None and draft["status"] == "confirmed" and draft_changed():
        st.caption(":orange[已确认的方案有修改，保存后会生成新版本，需要重新提交。]")
    render_status_actions(draft)
    if draft is not None and draft["plan_id"] is not None:
        st.caption("要做另一条线路，建议点“新建对话”，避免价格和景点混在一起。")
    if ss.autosave_error:
        st.caption(f":orange[草稿自动保存失败：{md_escape(ss.autosave_error)}]")


def render_plan_column():
    header = st.container()
    plan_tab, cost_tab, library_tab = st.tabs(["当前方案", "费用核算", "方案库"])
    with plan_tab:
        render_plan_editor()
    with cost_tab:
        render_costs()
    with library_tab:
        render_plan_library()
    with header:
        render_plan_header()


# ---------- 侧栏：会话入口 ----------

def open_conversation(conversation_id):
    result = api.fetch_conversation(conversation_id, current_token())
    if not result["ok"]:
        ss.sidebar_error = result["error"]
        return
    ss.sidebar_error = None
    request_action({
        "type": "open_conversation",
        "conversation_id": conversation_id,
        "messages": result["data"]["messages"],
    })


def delete_current_conversation():
    conversation_id = ss.conversation_id
    result = api.delete_conversation(conversation_id, current_token())
    if not result["ok"]:
        ss.sidebar_error = result["error"]
        return
    reset_conversation()
    notify("success", f"已删除会话 #{conversation_id}")


def render_conversation_list():
    result = api.list_conversations(current_token())
    if not result["ok"]:
        st.error(result["error"], icon=":material/error:")
        return

    conversations = result["data"]["conversations"]
    if not conversations:
        st.caption("还没有历史会话。")

    for item in conversations:
        # 按钮文字支持 Markdown，标题来自用户问题，需要转义。
        if st.button(
            md_escape(item["title"]), key=f"open_conversation_{item['id']}", type="tertiary",
            width="stretch", disabled=item["id"] == ss.conversation_id,
        ):
            open_conversation(item["id"])
            st.rerun()
        st.caption(display_time(item["updated_at"]))


def render_sidebar():
    with st.sidebar:
        st.markdown("### 会话工作台")
        # 切换身份立即清空页面状态；这只是演示，真实权限由后端按令牌校验。
        st.selectbox("演示身份", list(api.DEMO_USERS), key="user_select", on_change=reset_conversation)

        # 新建对话：放在主区控件之后执行，能检查到刚输入的未保存修改。
        if st.button("新建对话", type="primary", icon=":material/add:", width="stretch", key="new_conversation"):
            request_action({"type": "new_conversation"})
            st.rerun()

        st.caption("当前是新对话" if ss.conversation_id is None else f"当前会话 #{ss.conversation_id}")

        if ss.conversation_id is not None:
            with st.popover("删除当前会话", icon=":material/delete:", width="stretch"):
                st.caption("将删除后端保存的聊天记录，并清空当前页面的未保存草案；已保存的方案不受影响。")
                if st.button("确认删除", type="primary", key="confirm_delete_conversation"):
                    delete_current_conversation()
                    st.rerun()

        if ss.sidebar_error:
            st.error(ss.sidebar_error, icon=":material/error:")

        st.divider()
        st.markdown("**历史会话**")
        render_conversation_list()

        st.divider()
        st.caption("资料与费用仅供员工参考，实际政策和最终报价仍需核实。")


def render_workflow():
    """V1 闭环进度：查资料 → 生成草案 → 调整 → 保存 → 确认方案 → 打开继续编辑。"""
    draft = ss.draft
    steps = [
        ("查资料", bool(ss.messages)),
        ("生成路线草案", draft is not None),
        ("调整路线和价格", draft is not None and quote_state() == "fresh"),
        ("保存", draft is not None and draft["plan_id"] is not None and not draft_changed()),
        ("确认方案", draft is not None and draft["status"] == "confirmed"),
        ("打开继续编辑", ss.reopened),
    ]
    current = next((index for index, (_, done) in enumerate(steps) if not done), None)
    parts = []
    for index, (label, done) in enumerate(steps):
        if done:
            parts.append(f":green[✓ {label}]")
        elif index == current:
            parts.append(f"**{label}**")
        else:
            parts.append(f":gray[{label}]")
    st.caption(" › ".join(parts))


# ---------- 页面主体 ----------

init_state()   #整合所有数据，在页面显示

notice = ss.pop("notice", None)
if notice is not None:
    kind, text = notice
    icons = {"success": ":material/check_circle:", "error": ":material/error:", "info": ":material/info:"}
    st.toast(text, icon=icons[kind])

st.title("旅行社 Copilot 工作台")
workflow_slot = st.container()
render_pending_action()

# 宽屏并排：左聊天、右方案；窄窗口自动上下排列。
# 先渲染方案列再渲染聊天列，保证发送提问前，方案输入已写回草案。
chat_col, plan_col = st.columns([1, 1.05], gap="large")
with plan_col:
    render_plan_column()
with chat_col:
    render_chat()

with workflow_slot:
    render_workflow()

render_sidebar()
autosave_draft()
