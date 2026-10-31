# 已停用的模型自动评分

这里保存已停用的模型评分代码和历史结果，当前评测和报告都不依赖它们。

| 文件 | 原位置 | 作用 |
|---|---|---|
| `eval_judge.py` | `app/` | 评分提示词、结果校验、模型请求和分数汇总 |
| `judge_langfuse_saved.py` | `examples/` | 读取已有答案，同步人工复核分数 |
| `test_eval_judge.py` | `tests/` | 模型评分测试 |
| `quality_reviews/` | `examples/` | 已有评分缓存、理由、用量和人工复核模板 |

## 重新启用

把四项移回原位置，代码里的导入和路径都按原位置编写，不用修改：

- `eval_judge.py` 回到 `app/`
- `judge_langfuse_saved.py` 回到 `examples/`
- `test_eval_judge.py` 回到 `tests/`
- `quality_reviews/` 回到 `examples/`

然后把 `eval_judge.py` 的 `MODEL_JUDGING_ENABLED` 改为 `True`，再恢复评分入口。

历史模型分 `answer_coverage`、`groundedness` 使用 `travel-quality-v1` 标准，
与当前人工分来源不同，不能直接比较平均值。
