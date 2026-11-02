import requests
import streamlit as st


API_URL = "http://127.0.0.1:8000"  # 后端地址；本次只调整页面，不改变接口。
DEMO_USERS = {"用户A": "token_a", "用户B": "token_b"}  # 保留原有演示身份。


# 页面配置：采用宽布局，再用下方样式限制正文宽度，兼顾大屏与小窗口。
st.set_page_config(
    page_title="旅行社 Copilot",
    page_icon=":material/travel_explore:",
    layout="wide",
    initial_sidebar_state="auto",  # 窄窗口自动收起侧栏，避免挡住正文。
)


# 页面样式：只调整间距、字号和阅读宽度；颜色跟随 Streamlit 的明暗主题。
st.markdown(
    """
    <style>
    /* 主内容和底部输入框保持相近宽度，避免大屏上每行文字过长。 */
    .block-container {
        max-width: 64rem;
        padding-top: 2rem;
        padding-bottom: 5rem;
    }
    [data-testid="stBottomBlockContainer"] {
        max-width: 64rem;
        margin-inline: auto;
    }

    /* 标题保持克制，让视觉重点落在问题与回答上。 */
    [data-testid="stMainBlockContainer"] [data-testid="stHeadingWithActionElements"] h1 {
        font-size: 1.85rem;
        letter-spacing: -0.02em;
    }
    [data-testid="stMainBlockContainer"] [data-testid="stHeadingWithActionElements"] h3 {
        font-size: 1.2rem;
    }
    [data-testid="stChatMessage"] {
        border-radius: 0.8rem;
        padding: 1.1rem;
        margin-bottom: 0.75rem;
    }
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
        background: color-mix(in srgb, currentColor 5%, transparent);
    }
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
        background: transparent;
    }

    /* 放松正文行距，保留模型原有的列表、表格和引用编号。 */
    [data-testid="stChatMessage"] p,
    [data-testid="stChatMessage"] li { line-height: 1.8; }
    [data-testid="stChatMessage"] h2 { font-size: 1.2rem; margin-top: 1.4rem; }
    [data-testid="stChatMessage"] h3 { font-size: 1.08rem; margin-top: 1.15rem; }
    [data-testid="stChatMessage"] table { width: 100%; font-size: 0.95rem; }
    [data-testid="stChatMessage"] th,
    [data-testid="stChatMessage"] td { padding: 0.65rem 0.8rem; vertical-align: top; }

    /* 引用原文仍按纯文本显示，用正常字体阅读，不执行网页里的 HTML。 */
    [data-testid="stText"] {
        font-family: inherit;
        line-height: 1.65;
        overflow-wrap: anywhere;
    }

    /* 小窗口缩小留白，为聊天内容留出更多横向空间。 */
    @media (max-width: 768px) {
        .block-container { padding-top: 1rem; padding-inline: 1rem; }
        [data-testid="stChatMessage"] { padding: 0.8rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# 初始化页面状态：这里只保存当前页面的会话编号和成功完成的聊天记录。
if "conversation_id" not in st.session_state:
    st.session_state["conversation_id"] = None
if "messages" not in st.session_state:
    st.session_state["messages"] = []


# 侧栏身份：切换演示用户时清空当前页面，避免把不同用户的聊天混在一起。
st.sidebar.title("会话工作台")
selected_user = st.sidebar.selectbox("演示身份", list(DEMO_USERS.keys()))
if "selected_user" not in st.session_state:
    st.session_state["selected_user"] = selected_user
elif st.session_state["selected_user"] != selected_user:
    st.session_state["selected_user"] = selected_user
    st.session_state["conversation_id"] = None
    st.session_state["messages"] = []
current_token = DEMO_USERS[selected_user]


# 新建对话：只重置当前页面；下一次成功提问时由后端创建新会话。
if st.sidebar.button(
    "新建对话", type="primary", icon=":material/add:", width="stretch"
):
    st.session_state["conversation_id"] = None
    st.session_state["messages"] = []


# 会话状态移到侧栏，主聊天区不再重复显示大块的会话编号提示。
conversation_id = st.session_state["conversation_id"]
if conversation_id is None:
    st.sidebar.caption("当前是新对话")
else:
    st.sidebar.caption(f"当前会话 #{conversation_id}")
st.sidebar.divider()
st.sidebar.markdown("**使用提示**")
st.sidebar.caption("先说明目的地、天数和人数，再逐步补充路线、价格与其他条件。")
st.sidebar.caption("讨论另一位客户或全新需求时，可以新建对话。")
st.sidebar.divider()
st.sidebar.caption("资料与费用供员工参考，实际政策和最终报价仍需核实。")


# 主区标题：展示业务用途，隐藏 FastAPI 等与页面操作无关的实现细节。
st.title("旅行社 Copilot")
st.caption("旅行资料查询 · 路线讨论 · 费用核算")


# 新对话引导：只给文字示例，不自动发送问题或触发收费请求。
if not st.session_state["messages"]:
    with st.container(border=True):
        st.subheader("从一条旅行需求开始")
        st.write("可以先查资料，也可以把已知价格交给我核算，再逐步调整细节。")
        st.markdown(
            "**查资料**　杭州有哪些适合三天两晚的路线？\n\n"
            "**算费用**　2位成人、0位儿童，每人餐费100元，帮我计算。"
        )


# 引用展示：标题直接放进入口，展开后保留来源信息、网页链接和完整原文。
def render_sources(message):
    citations = message.get("citations", [])
    if not citations:
        return

    st.caption(f"参考来源 · {len(citations)} 条，展开可核对原文")
    for citation in citations:
        citation_id = citation["citation_id"]
        metadata = citation.get("metadata", {})
        title = metadata.get("source_title") or "未提供资料标题"
        short_title = title if len(title) <= 42 else title[:42] + "…"

        with st.expander(f"[{citation_id}] {short_title}"):
            st.markdown("**资料标题**")
            st.write(title)

            # 网络与内部来源分别展示；链接只使用后端返回的原始网址。
            if metadata.get("source_type") == "web":
                st.caption(f"网页资料 · {metadata.get('content_type', '网页内容')}")
                st.link_button(
                    "打开原网页", metadata["url"], icon=":material/open_in_new:"
                )
            else:
                st.caption(f"内部资料 · 来源编号 {metadata.get('source_id', '未提供')}")

            # 长原文放入固定高度区域滚动查看，短原文按内容高度正常显示。
            for chunk in message.get("evidence", []):
                if chunk["chunk_id"] == citation["chunk_id"]:
                    content = chunk["content"]
                    is_long = len(content) > 700 or content.count("\n") > 10
                    st.caption(f"原始资料 · {len(content)} 字符")
                    with st.container(height=280 if is_long else "content", border=False):
                        st.text(content)
                    break


# 渲染成功完成的历史消息；统一头像，并在助手回答下方展示本条引用。
for message in st.session_state["messages"]:
    avatar = ":material/person:" if message["role"] == "user" else ":material/travel_explore:"
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])
        if message.get("needs_clarification", False):
            st.caption("请在下方补充信息，我会接着处理。")
        render_sources(message)


# 输入区：长度与后端的 1000 字符限制保持一致，减少提交后才报错的情况。
question = st.chat_input("输入旅行需求，或继续补充、调整条件…", max_chars=1000)

if question:
    # 先即时显示提问；请求成功前，不把它写入页面的持久聊天状态。
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(question)

    # 组装原有接口参数和演示令牌，不改变 /chat 的请求协议。
    payload = {
        "question": question,
        "conversation_id": st.session_state["conversation_id"],
    }
    headers = {"Authorization": f"Bearer {current_token}"}

    # 等待后端回答；连接失败时保留旧历史，给出可操作的提示。
    try:
        with st.spinner("正在整理回答，请稍候…"):
            response = requests.post(
                f"{API_URL}/chat", json=payload, headers=headers, timeout=90
            )
    except requests.exceptions.RequestException:
        st.error("暂时无法连接服务，请确认后端已启动后重试。")
        st.caption("本次提问未加入页面历史，可以重新发送。")
        st.stop()

    # 成功后一次保存完整的一问一答，再重新渲染，避免重复和闪烁。
    if response.status_code == 200:
        result = response.json()
        answer = result["data"]["answer"]
        st.session_state["conversation_id"] = result["conversation_id"]
        st.session_state["messages"].append({"role": "user", "content": question})
        st.session_state["messages"].append({
            "role": "assistant",
            "content": answer,
            "citations": result.get("citations", []),
            "evidence": result.get("evidence", []),
            "needs_clarification": result.get("needs_clarification", False),
        })
        st.rerun()

    # 服务返回失败时显示原因；不保存半轮消息，下一次重试不会累积提问。
    else:
        detail = response.json().get("detail", "请求失败")
        st.error(f"本次请求未完成（{response.status_code}）：{detail}")
        st.caption("本次提问未加入页面历史，可以修改后重新发送。")
