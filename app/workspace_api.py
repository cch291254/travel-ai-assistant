"""工作台的真实后端调用。

只封装后端已经存在的接口：聊天、会话、费用核算、草稿和方案。
页面拿到的都是统一结构 {"ok", "data", "error", "status_code"}，
以后新增方案、核算接口时，在这里补函数即可，页面不直接拼请求。
"""

import os

import requests


# 后端地址可用环境变量覆盖，默认与现有页面一致；这里不读取 .env 里的密钥。
# os.getenv(名称, 默认值)：未设置环境变量时使用默认地址。
# rstrip("/") 去掉末尾的 /，避免与接口路径拼接成两个 /。
API_URL = os.getenv("WORKSPACE_API_URL", "http://127.0.0.1:8000").rstrip("/")

# 演示身份与后端 DEMO_TOKEN_USERS 对应；真正的权限校验在后端完成。
DEMO_USERS = {"用户A": "token_a", "用户B": "token_b"}

CHAT_TIMEOUT = 90
DEFAULT_TIMEOUT = 10


# 作用：统一组装失败结果，让页面通过 ok/data/error 字段显示错误。
# status_code=None 表示没有状态码，例如连接失败时尚未收到响应。
# 函数名开头的 _ 是“内部辅助函数”的约定，不是禁止外部调用的语法。
def _failure(error, status_code=None):
    return {"ok": False, "data": None, "error": error, "status_code": status_code}


# 作用：从后端错误响应中提取提示；格式不符时给出通用提示。
# response 是 HTTP 响应对象，含 status_code（状态码）和响应正文。
def _error_detail(response):
    """把后端的错误响应转换成员工能看懂的一句话。"""
    try:
        body = response.json()  # 把 JSON 正文解析成 Python 数据，不是转换成 JSON 字符串。
    except ValueError:
        # 解析失败会抛出 ValueError 或其子类，例如后端返回了 HTML 错误页。
        return f"服务返回异常（{response.status_code}）"

    # 条件表达式：body 是字典时取 detail，否则取 None；isinstance 用于检查类型。
    # 字典 get("detail") 在找不到键时返回 None，不会像 ["detail"] 那样报 KeyError。
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, str) and detail:
        # and detail 还要求字符串非空；空字符串的布尔值为 False。
        return detail
    if response.status_code == 422:
        return "提交内容不符合要求，请检查后重试"
    return f"请求未完成（{response.status_code}）"


# 作用：统一发送后端请求，处理地址拼接、访问令牌、超时和错误结果。
# method 是 GET/POST/DELETE 等方法；path 是 /chat 等路径；token 是访问令牌。
# 单独的 * 表示 timeout 必须按名称传入，例如 timeout=90。
# **kwargs 把额外关键字参数收集成字典，例如 json={...}，再转交给 requests。
def _request(method, path, token, *, timeout=DEFAULT_TIMEOUT, **kwargs):
    try:
        response = requests.request(
            method,
            f"{API_URL}{path}",  # f 字符串把花括号里的变量值放入文本。
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
            **kwargs,  # 调用中的 ** 将字典展开为参数，例如 {"json": body} 变成 json=body。
        )
    except requests.exceptions.Timeout:
        return _failure("服务响应超时，请稍后重试")
    except requests.exceptions.RequestException:
        # Timeout 也是 RequestException 的子类，因此前面先捕获超时，给出专门提示。
        return _failure("暂时无法连接服务，请确认后端已启动后重试")

    # 当前封装的接口以 200 为成功；这里尚未把 201、204 等状态作为成功处理。
    if response.status_code != 200:
        return _failure(_error_detail(response), response.status_code)

    try:
        data = response.json()
    except ValueError:
        return _failure("服务返回了无法识别的内容", response.status_code)

    return {"ok": True, "data": data, "error": "", "status_code": 200}


# 作用：发送本轮聊天问题，将回答整理为页面需要的会话编号、正文和引用等字段。
# conversation_id=None 时由后端新建会话；已有编号时继续该会话。
def send_chat(question, conversation_id, token):
    """发送一轮提问；成功时只取页面需要的字段。"""
    result = _request(
        "POST",
        "/chat",
        token,
        timeout=CHAT_TIMEOUT,
        # requests 的 json= 接收 Python 字典，发送时自动编码成 JSON 正文。
        json={"question": question, "conversation_id": conversation_id},
    )
    if not result["ok"]:
        return result

    body = result["data"]
    # data 缺失、为 None 或空字典时，or {} 提供空字典，便于继续调用 get。
    answer = (body.get("data") or {}).get("answer")
    # strip() 去掉首尾空白；not answer.strip() 可以识别只有空格的回答。
    if not isinstance(answer, str) or not answer.strip():
        return _failure("服务没有返回可用回答，请稍后重试", 200)

    result["data"] = {
        "conversation_id": body.get("conversation_id"),
        "answer": answer,
        "citations": body.get("citations") or [],  # 值不存在或为 None 时，提供空列表。
        "evidence": body.get("evidence") or [],
        "needs_clarification": bool(body.get("needs_clarification")),  # bool 转为 True/False。
    }
    return result


# 作用：读取已有会话，只保留页面展示所需的 user/assistant 消息。
# 会话归属由后端根据 token 检查；这里的前端封装不能代替后端权限校验。
def fetch_conversation(conversation_id, token):
    """读取已有会话；后端只保存 role/content，不包含引用。"""
    result = _request("GET", f"/conversations/{conversation_id}", token)
    if not result["ok"]:
        return result

    body = result["data"]
    result["data"] = {
        "conversation": body.get("conversation") or {},
        # 列表推导式：[要生成的内容 for 元素 in 列表 if 筛选条件]。
        "messages": [
            {"role": item.get("role"), "content": item.get("content", "")}
            for item in body.get("messages") or []
            if item.get("role") in {"user", "assistant"}  # in 检查角色是否属于这个集合。
        ],
    }
    return result


# 作用：调用后端删除会话；成功后页面再清理当前显示的会话和消息。
def delete_conversation(conversation_id, token):
    return _request("DELETE", f"/conversations/{conversation_id}", token)



# 作用：把人数、单价和住宿参数送往 /quotes/calculate，取得后端核算结果。
# quote_input 是 build_quote_input() 组装的字典；token 用于后端访问校验。
def calculate_quote(quote_input,token):
    result=_request(
        "POST",    #发送数据
        "/quotes/calculate",    #后端核算接口
        token,                  #令牌
        json=quote_input
    )

    return result

# 作用：读取当前会话自动保存的草稿；还没有草稿时 data["draft"] 是 None。
def fetch_draft(conversation_id, token):
    return _request("GET", f"/conversations/{conversation_id}/draft", token)


# 作用：覆盖保存当前会话的草稿，一个会话只有一份。
def save_draft(conversation_id, draft, token):
    return _request("PUT", f"/conversations/{conversation_id}/draft", token, json={"draft": draft})


# 作用：读取当前用户的方案列表，不包含草案内容。
def list_plans(token):
    return _request("GET", "/plans", token)


# 作用：读取一个方案的最新版本，包含完整草案。
def fetch_plan(plan_id, token):
    return _request("GET", f"/plans/{plan_id}", token)


# 作用：第一次保存时新建方案。
def create_plan(title, draft, conversation_id, token):
    body = {"title": title, "draft": draft, "conversation_id": conversation_id}
    return _request("POST", "/plans", token, json=body)

# 作用：再次保存时生成新版本；base_version 过期时后端返回 409。
def save_plan_version(plan_id, title, draft, base_version, token):
    body = {"title": title, "draft": draft, "base_version": base_version}
    return _request("PUT", f"/plans/{plan_id}", token, json=body)


# 作用：提交、退回或确认方案，流转规则由后端判断。
def change_plan_status(plan_id, status, base_version, token):
    body = {"status": status, "base_version": base_version}
    return _request("POST", f"/plans/{plan_id}/status", token, json=body)


# 作用：删除方案及其全部版本。
def delete_plan(plan_id, token):
    return _request("DELETE", f"/plans/{plan_id}", token)


# 作用：把方案复制成一份新的第 1 版。
def copy_plan(plan_id, token):
    return _request("POST", f"/plans/{plan_id}/copy", token)