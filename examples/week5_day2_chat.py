import os
import requests
from dotenv import load_dotenv
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
payload={
    "model":model,
    "messages":[{
        "role":"system",
        "content":"你是一名旅行社行程助手，回答要简洁、谨慎。",
    },
    {
        "role":"user",
        "content":"请为两名第一次来杭州的游客安排一日游。只按上午、下午、晚上三个时间段回答，每段推荐一个地点，不要编造实时票价。"
    },
    ],
    "tinking":{"type":"disabled"},
    "max_tokens":3000,
    "stream":False,
    "temperature":0.2,
}
try:
    response=requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=60,
    )
    print("状态码：",response.status_code)
    if response.status_code !=200:
        print("错误内容:",response.text)
    else:
        data=response.json()
        answer=data["choices"][0]["message"]["content"]
        usage=data["usage"]
        print("模型回答：",answer)
        print("usage原始数据：", usage)
        print("输入tokens:",usage["prompt_tokens"])
        print("输出 tokens：", usage["completion_tokens"])
        print("总 tokens：", usage["total_tokens"])
        print("结束原因：", data["choices"][0]["finish_reason"])
except requests.exceptions.RequestException as error:
    print("网络请求失败：",error)