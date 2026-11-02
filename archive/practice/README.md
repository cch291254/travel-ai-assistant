# 练习脚本

第 5 到第 10 周学习时写的脚本，记录了从调用接口到建立检索的过程。主程序不依赖它们。

| 文件 | 内容 |
|---|---|
| `examples/week5_*` | HTTP 请求、环境变量、DeepSeek 客户端和重试 |
| `examples/week6_*` | SQLite 建表、读写和用户隔离练习 |
| `examples/week7_day*` | 切片、向量、建索引、重载和重排 |
| `examples/week7_full_index.py`、`week7_full_retrieval.py` | 旧的全量建索引和命令行问答 |
| `examples/week9_day1_tool_contract.py` | 工具定义的第一版 |
| `examples/week10_async_demo.py` | 同步和异步的对比 |
| `examples/langfuse_smoke.py`、`langfuse_chat_smoke.py` | 接入 Langfuse 时的连通检查 |
| `tests/test_week5_*`、`test_week7_full_retrieval.py` | 上面两个脚本的测试 |
| `tests/*.db` | week6 练习用的 SQLite 文件 |

现在建索引用 `python -m app.setup_data`，问答走 `/chat` 接口。
