import os
from pathlib import Path
from dotenv import load_dotenv
from langfuse import get_client


_client=None


def setup_tracing():
    global _client # 修改模块中的的_client


    #加载配置,resolve,绝对路劲，上上层
    env_path=Path(__file__).resolve().parents[1]/ ".env"
    load_dotenv(env_path)


    #开始才进行初始化
    if os.getenv("LANGFUSE_ENABLED","false").lower()!="true":
        return

    _client=get_client()


def get_tracing_client():
    return _client    #统一

def shutdown_tracing():
    global _client

    #关闭时删除记录发送后台
    if _client is not None:
        _client.shutdown()
        _client=None