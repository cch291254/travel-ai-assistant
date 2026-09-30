import os
from dotenv import load_dotenv
load_dotenv()
api_key=os.getenv("DEEPSEEK_API_KEY")
base_url=os.getenv(
    "DEEPSEEK_BASE_URL",
    "http://api.deepseek.com"
)
model=os.getenv(
    "DEEPSEEK_MODEL",
    "deepSEEK-FLASH",
)
if not api_key:
    print("未配置 Deepseek API key")
else:
    print("已读取DeepSeek API key")
print("api地址:",base_url)
print("模型名称：",model)