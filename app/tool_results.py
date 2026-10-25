#统一返回格式
import json

#成功板块
def tool_success(data):
    return {"ok": True, "data": data, "error": None}

#失败板块
def tool_failure(code, message):
    return {
        "ok": False,
        "data": None,
        "error": {"code": code, "message": message},
    }

#json返回
def tool_result_to_json(result):
    return json.dumps(result, ensure_ascii=False, default=str)
