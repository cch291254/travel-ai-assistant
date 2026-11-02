"""第5周第3天：输入检查、有限重试、输出限制和每次调用记录。"""

import os
import time

import requests
from dotenv import load_dotenv


def should_retry(status_code):
    retryable_codes = [429, 500, 502, 503, 504]
    return status_code in retryable_codes


def call_model(
    question,
    max_input_chars=1000,
    max_tokens=300,
    max_attempts=3,
    timeout=60,
    retry_delay=1,
):
    result = {"success": False, "answer": "", "error": "", "records": []}

    # 先检查输入；检查失败时不会加载配置或发送请求。
    if not isinstance(question, str):
        result["error"] = "问题必须是字符串"
        return result

    question = question.strip()
    if len(question) == 0:
        result["error"] = "问题不能为空"
        return result
    if len(question) > max_input_chars:
        result["error"] = "问题过长"
        return result
    if max_attempts < 1 or max_tokens < 1 or timeout <= 0 or retry_delay < 0:
        result["error"] = "尝试次数、输出上限和超时必须为正，等待时间不能为负"
        return result

    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")

    if not api_key or not api_key.strip():
        result["error"] = "未配置 DeepSeek API Key"
        return result

    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一名旅行社行程助手，回答要简洁、谨慎。"},
            {"role": "user", "content": question},
        ],
        "thinking": {"type": "disabled"},
        "max_tokens": max_tokens,
        "stream": False,
        "temperature": 0.2,
    }

    for attempt in range(max_attempts):
        # 没收到usage时用None表示未知，不能把它当成消耗了0个token。
        record = {
            "模型名": model,
            "状态码": None,
            "输入tokens": None,
            "输出tokens": None,
            "总tokens": None,
            "结束原因": "",
            "重试次数": attempt,
            "耗时秒": 0,
            "结果": "",
            "错误类型": "",
        }
        result["records"].append(record)
        request_started = time.perf_counter()

        # 这里只捕获发送请求时的异常，JSON解析在后面单独处理。
        try:
            response = requests.post(
                url, headers=headers, json=payload, timeout=timeout
            )
        except requests.exceptions.SSLError as error:
            record["耗时秒"] = round(time.perf_counter() - request_started, 3)
            record["结果"] = "网络配置错误"
            record["错误类型"] = type(error).__name__
            result["error"] = "TLS/证书连接失败，请检查配置，不自动重试"
            return result
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as error:
            record["耗时秒"] = round(time.perf_counter() - request_started, 3)
            record["结果"] = "网络异常"
            record["错误类型"] = type(error).__name__
            if attempt + 1 == max_attempts:
                result["error"] = "网络请求失败，尝试次数耗尽"
                return result
            time.sleep(retry_delay)
            continue
        except requests.exceptions.RequestException as error:
            record["耗时秒"] = round(time.perf_counter() - request_started, 3)
            record["结果"] = "请求配置错误"
            record["错误类型"] = type(error).__name__
            result["error"] = "请求异常，请检查地址和配置，不自动重试"
            return result

        record["耗时秒"] = round(time.perf_counter() - request_started, 3)
        record["状态码"] = response.status_code

        if response.status_code != 200:
            record["结果"] = "HTTP失败"
            record["错误类型"] = f"HTTP {response.status_code}"
            # 所有HTTP错误均保留本次记录；只有选定的临时错误会再请求。
            if should_retry(response.status_code) and attempt + 1 < max_attempts:
                time.sleep(retry_delay)
                continue
            # 正文只用于展示最终错误原因，不放入调用记录。
            error_text = response.text[:500] or "服务器未提供错误正文"
            result["error"] = f"HTTP {response.status_code}：{error_text}"
            if should_retry(response.status_code):
                result["error"] += "，尝试次数耗尽"
            return result

        # HTTP成功后才解析JSON。正文或结构错误不会自动重试模型调用。
        try:
            data = response.json()
            choice = data["choices"][0]
            answer = choice["message"]["content"]
            if answer is None:
                answer = ""
            if not isinstance(answer, str):
                raise TypeError("模型回答不是字符串")
            usage = data["usage"]
            record.update({
                "模型名": data.get("model", model),
                "输入tokens": usage["prompt_tokens"],
                "输出tokens": usage["completion_tokens"],
                "总tokens": usage["total_tokens"],
                "结束原因": choice["finish_reason"],
            })
        except (ValueError, KeyError, IndexError, TypeError) as error:
            record["结果"] = "响应解析失败"
            record["错误类型"] = type(error).__name__
            result["error"] = "响应不是有效JSON或缺少预期字段，不自动重试"
            return result

        result["answer"] = answer
        if record["结束原因"] == "length":
            record["结果"] = "回答截断"
            result["error"] = "达到生成长度限制，回答可能不完整；不自动重试"
            return result
        if record["结束原因"] != "stop" or not answer.strip():
            record["结果"] = "回答未正常完成"
            result["error"] = "模型未返回完整的非空回答，不自动重试"
            return result

        record["结果"] = "正常结束"
        result["success"] = True
        return result


if __name__ == "__main__":
    question = (
        "请为两名第一次来杭州的游客安排一日游。"
        "只按上午、下午、晚上三个时间段回答，每段推荐一个地点，不要编造实时票价。"
    )
    result = call_model(question)
    if result["answer"]:
        print("模型回答：", result["answer"])
    if not result["success"]:
        print("调用提示：", result["error"])
    for record in result["records"]:
        print("调用记录：", record)
