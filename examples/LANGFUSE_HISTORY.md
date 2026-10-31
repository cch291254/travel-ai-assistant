# 三轮历史评测迁移

运行脚本：`python -m examples.import_langfuse_history`。默认只生成本地预览，
文件位于 `examples/langfuse_history/`，保留完整原结果、原评审、配置与文件哈希。

正式导入：

```powershell
python -m examples.import_langfuse_history --upload --proxy http://127.0.0.1:7897
```

只导入一个案例做检查：

```powershell
python -m examples.import_langfuse_history --upload --round 1 --case E03 --proxy http://127.0.0.1:7897
```

脚本读取已有结果，不导入聊天/检索执行模块，也不请求模型。固定实验名包含结果和评审的
联合指纹；上传前读取该实验已有题号，跳过已存在的记录。回执保存本次提交的 trace ID。
云端写入可能有延迟，刚上传后不要立即并行运行第二个导入进程。

## 去哪里看

在 Langfuse 的 Experiments 中搜索 `historical-rag-round-`：

- round-1：27案例、29轮；原人工准确15/27（55.56%）。
- round-2：30案例、40轮；原人工准确13/30（43.33%）。
- round-3：30案例、40轮；原人工准确22/30（73.33%）。

查看 `legacy_answer_correct`（0/1）的平均值即可对照原报告。
`legacy_execution_ok` 只表示原结果中已记录的轮次是否均为 `ok`。
它们沿用原评审口径，不等于新评测的 `execution_complete`、`source_coverage`，
也不将旧评分拆造为要点覆盖/事实依据两个分数。

Input/Expected Output 使用旧文件的快照；链接现有题号只为进行同题比较，不修改当前题集。
第一轮未测的E28—E30不导入。部分旧题只测试首轮，按原报告保留，
例如第一轮E07准确是指当时已测的澄清首问，不表示新版两轮全部通过。
第一轮评审的E019与原始结果E19关联，原标题保留于本地预览。

## 时间、用量与原文

云端新增的span记录的是本次导入过程，页面Start Time/Latency是导入时间/耗时。
原开始时间在 `original_started_at`，完整运行配置和报告说明在记录详情的
`metadata.original_run_info`、`metadata.original_review_preamble`。
原回答、状态、引用原文、每轮耗时和原模型用量在Output的turns中。
原人工评审全文在 `output.original_human_review`。

完整原始检索候选、原回答等仍保存在本地prepared文件的 `original_rows`；
云端只展示实际引用到的证据正文，避免无关候选淹没回答。
历史运行当时未接追踪，所以不补造generation/工具子调用或当时的时间线。
第三轮原run_info有召回参数旧记录问题，原值与原报告的修正说明一并保留，不悄悄改写。

需要续传时先查看本地回执及云端输出；导入失败记录不得作为模型质量失败统计。
