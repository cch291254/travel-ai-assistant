import streamlit as st
import requests

API_URL = "http://127.0.0.1:8000"


st.set_page_config(
    page_title="旅行社 Copilot",
    page_icon="✈️"
)

st.title("旅行社 Copilot")
st.caption("通过FastAPI 调用旅行助手")

if "conversation_id" not in st.session_state:
    st.session_state["conversation_id"]=None

if "messages" not in st.session_state:
    st.session_state["messages"]=[]

DEMO_USERS={
    "用户A":"token_a",
    "用户B":"token_b"
}

selected_user=st.sidebar.selectbox(
    "演示用户",
    list(DEMO_USERS.keys())
)

if "selected_user" not in st.session_state:
    st.session_state["selected_user"]=selected_user

elif st.session_state["selected_user"]!=selected_user:
    st.session_state["selected_user"]=selected_user
    st.session_state["conversation_id"]=None
    st.session_state["messages"]=[]

current_token=DEMO_USERS[selected_user]

if st.sidebar.button("新建对话"):
    st.session_state["conversation_id"]=None
    st.session_state["messages"]=[]


if st.session_state["conversation_id"] is None:
    st.info("当前是新对话")
else:
    st.info(
        f'当前会话ID：{st.session_state["conversation_id"]}'
    )


for message in st.session_state["messages"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

question=st.chat_input("请输入旅行需求")

if question:
    st.session_state["messages"].append({
        "role":"user",
        "content":question
    })

    with st.chat_message("user"):
        st.markdown(question)

    payload={
        "question":question,
        "conversation_id":st.session_state["conversation_id"]
    }

    headers={
        "Authorization":f"Bearer {current_token}"
    }


    try:
        with st.spinner("正在生成答案......"):
            response=requests.post(
                f"{API_URL}/chat",
                json=payload,
                headers=headers,
                timeout=90
            )
    except requests.exceptions.RequestException:
        st.error("请求未完成，请检查后端是否启动或者稍后重试")
        st.stop()

    if response.status_code==200:
        result=response.json()

        answer=result["data"]["answer"]

        st.session_state["conversation_id"]=(result["conversation_id"])

        st.session_state["messages"].append({
            "role":"assistant",
            "content":answer
        })

        with st.chat_message("assistant"):
            st.markdown(answer)

        st.rerun()
            
    else:
        detail=response.json().get(
            "detail",
            "请求失败"
        )

        st.error(f"请求失败({response.status_code}):{detail}")