import os
import requests
from dotenv import load_dotenv
import time

def should_retry(status_code):
    retryable_codes = [429, 500, 502, 503, 504]
    if status_code in retryable_codes:
        return True
    return False


def call_model(question,system_prompt="你是一名旅行行程助手，回答要简洁、谨慎",json_mode=False,history=None):
    result={"answer":"","record":None,"error":""}
    max_input_chars=1000
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
    load_dotenv()
    api_key=os.getenv("DEEPSEEK_API_KEY")
    base_url=os.getenv("DEEPSEEK_BASE_URL",
    "https://api.deepseek.com")
    model=os.getenv("DEEPSEEK_MODEL",
    "deepseek-flash")
    if not api_key:
        raise RuntimeError("未配置 DeepSeek api Key")
    url=base_url+"/chat/completions"
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if history is None:
        history=[]
    messages=[
        {
            "role":"system",
            "content":system_prompt
        }]
    messages.extend(history)
    messages.append({
        "role":"user",
        "content":question})
    payload={
        "model":model,
        
        "messages":messages,
        
        "thinking":{"type":"disabled"},
        "max_tokens":300,
        "stream":False,
        "temperature":0.2,
    }
    if json_mode:
        payload["response_format"]={"type":"json_object"}
    max_attempts=3
    for attempt in range(max_attempts):
            call_record = {
        "模型名": model,
        "状态码": None,
        "输入tokens": None,
        "输出tokens": None,
        "总tokens": None,
        "结束原因": None,
        "重试次数": attempt,
        "请求耗时秒":None,
    }
            start_time = time.perf_counter()

            try:   
                response=requests.post(
                    url,
                    json=payload,
                    timeout=60,
                    headers=headers,
                )
                call_record["请求耗时秒"]=round(time.perf_counter()-start_time,3)
                status_code=response.status_code
                call_record["状态码"]=status_code
                print("第",attempt+1,"次请求，状态码：",status_code)
                retry_allowed=should_retry(status_code)
                if status_code==200:
                    data=response.json()
                    choice=data["choices"][0]
                    answer=choice["message"]["content"]
                    usage=data["usage"]
                    
                    call_record["输入tokens"]=usage["prompt_tokens"]
                    call_record["输出tokens"]=usage["completion_tokens"]
                    call_record["总tokens"]=usage["total_tokens"]
                    call_record["结束原因"]=choice["finish_reason"]
                    
                    result["answer"]=answer
                    result["record"]=call_record

                    if choice["finish_reason"] == "length":
                        result["error"] = "回答不完整"

                    elif choice["finish_reason"] != "stop" or not answer.strip():
                        result["error"] = "模型未返回完整回答"
                    break
                elif not retry_allowed:
                    result["error"]=f"HTTP请求失败,状态码{status_code},不允许重试"
                    result["record"] = call_record
                    break
                elif attempt+1==max_attempts:
                    result["error"]=f"次数已耗尽，状态码{status_code},已尝试次数{attempt+1}"
                    result["record"] = call_record
                    print("错误内容：",response.text)
                    break
                else:
                    print("准备重试")
                    time.sleep(1)
            except requests.exceptions.RequestException as error:
                call_record["请求耗时秒"]=round(time.perf_counter()-start_time,3)
                if attempt+1==max_attempts:
                    result["error"]=f"网络请求失败，次数已耗尽{error}，已尝试次数{attempt+1}"
                    result["record"] = call_record
                    break

                print("准备重试")
                time.sleep(1)   
    return result


if __name__ == "__main__":
    print("只在直接运行本文件时执行")
    result=call_model("推荐西湖")
    print(result)