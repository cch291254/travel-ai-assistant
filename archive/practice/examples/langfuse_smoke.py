from pathlib import Path
from dotenv import load_dotenv
from langfuse import get_client


#明确读取当前项目根目录的.env
env_path=Path(__file__).resolve().parents[1]/".env"
load_dotenv(env_path)

#根据环境变量langfse 客户端。
langfuse=get_client()

#检查地址
if not langfuse.auth_check():
    raise RuntimeError("Langfuse 连接验证失败，请检查地址和钥匙")

with langfuse.start_as_current_observation(  #创建一条测试
    as_type="span",
    name="connection-test",
    input={"message":"这是一条连接测试"},
) as span:
    span.update(output={"status":"ok"})
    trace_id=langfuse.get_current_trace_id()


#等待后台发送，避免脚本退出时测试数据还没发完
langfuse.flush()
print("测试追踪编号：",trace_id)
