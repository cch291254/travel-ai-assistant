import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# 把项目根目录加入导入路径。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tracing import (
    setup_tracing,
    get_tracing_client,
    shutdown_tracing,
)
from app.tool_calling import run_tool_chat

# 模拟第一次模型返回：要求调用计算工具。
tool_request = {
    "role": "assistant",
    "content": None,
    "tool_calls": [{
        "id": "call_demo_1",
        "type": "function",
        "function": {
            "name": "calculate_quote",
            "arguments": json.dumps({
                "adults": 2,
                "children": 0,
                "meal_price": "50.00",
            }),
        },
    }],
}

# 模拟第二次模型返回：根据工具结果回答。
final_answer = {
    "role": "assistant",
    "content": "两位成人餐费合计100元。",
}

# 两次 HTTP 响应都带模拟用量，用于检查记录是否成功。
responses = []
for message in [tool_request, final_answer]:
    response = Mock()
    response.json.return_value = {
        "choices": [{"message": message, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "total_tokens": 150,
        },
    }
    responses.append(response)

# 开启追踪，并在结束时发送记录、关闭客户端。
setup_tracing()
client = get_tracing_client()

try:
    if client is None:
        raise RuntimeError("请先开启 LANGFUSE_ENABLED")

    with client.start_as_current_observation(
        as_type="span",
        name="tool-chat-smoke",
        metadata={"simulated": True},
    ) as span:
        # 替换模型 HTTP 请求；计算工具仍执行真实的本地代码。
        with patch(
            "app.tool_calling.requests.post",
            side_effect=responses,
        ):
            result = run_tool_chat("两位成人，每人餐费50元，帮我计算")

        span.update(output=result)
        trace_id = client.get_current_trace_id()

    print("运行结果：", result)
    print("追踪编号：", trace_id)
finally:
    shutdown_tracing()