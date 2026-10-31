# 当前评测说明：模型自动评分已停用

## 运行题目

下面的命令会真实运行旅行助手，产生助手用量；不会请求评分模型。

```powershell
python -m examples.run_langfuse_eval --case E01 E03 E07 --proxy http://127.0.0.1:7897
```

完整题集使用 --all 替换 --case E01 E03 E07。不要重复运行仅为查看结果。
原有 --judge 参数已移除，使用它会在读取云端题集前报参数错误。

## 保留的自动检查

- execution_complete：所有提问是否执行完成，有没有错误。
- source_coverage：预期来源编号是否被引用，不等于回答内容正确。

实际问答、标准、逐轮耗时、追踪编号和规则分数保存在 examples/evaluation_runs/。
模型 Token 在 Langfuse 的 model-call 中查看；成本需核实价格配置。

## 人工评分

在 Langfuse 的 Annotate 中填写 human_answer_coverage 和 human_groundedness。
人工标注不请求评分模型。

## 模型评分模块

已停用的代码和历史结果移到 archive/model_judging/，当前评测和报告不依赖它们。
重新启用的方法见该目录的 README。原模型分和历史追踪仍保留在 Langfuse。

## 历史结果

historical-rag-round-* 的导入说明见 LANGFUSE_HISTORY.md。
旧人工分与模型初评分不是同一评分口径，不能直接比较平均值。
