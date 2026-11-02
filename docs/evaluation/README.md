# 评测记录

## 当前评测

| 文件 | 内容 |
|---|---|
| `baseline_20261031.md` | 工具聊天的正式基线：40 题、51 轮，含人工评分 |
| `../../examples/rag_eval_cases.json` | 题目和评分标准 |
| `../../examples/EVALUATION_QUICKSTART.md` | 怎么跑评测、生成报告 |

评测运行结果保存在 `examples/evaluation_runs/`，只在本地，不进入 Git。

## 历史记录：`history/`

前三轮用的是旧的固定问答流程（见 `archive/legacy_rag/`）。

| 文件 | 内容 |
|---|---|
| `early_questions.md` | 最早的开发题和运行记录，含 R 系列旧检索题 |
| `round1_review.md`、`round1_results.json` | 第一轮评审和原始结果（E01–E27） |
| `round2_review.md`、`round2_results.json` | 第二轮：短段合并、多路检索 |
| `round3_review.md`、`round3_results.json` | 第三轮：v2 索引、打开来源过滤 |

三轮的答案正确率是当时的人工判断，和基线的要点覆盖、依据分口径不同，不能直接比较。

这三轮已导入 Langfuse（`historical-rag-round-*`），导入脚本是 `examples/import_langfuse_history.py`，说明见 `examples/LANGFUSE_HISTORY.md`。
