# 杭州旅行社知识库与报价 Copilot

本项目面向旅行社销售、行程顾问和客服人员，基于杭州旅游资料和项目模拟业务资料，辅助完成知识查询、路线比较、分项报价和行程草案生成。所有报价和行程建议均需员工确认。

## 当前已完成

- TXT、Markdown和文本层PDF解析；
- 文件哈希计算与重复识别；
- SQLite文档状态登记；
- 单文件和目录批量导入；
- 失败文件记录与错误原因保存；
- 当前109项自动化测试通过，模型调用使用模拟响应，会话数据库使用临时目录；不包含GPU向量模型的自动化验证
- DeepSeek 调用与重试、结构化回答校验、FastAPI 接口、接口成功与失败测试
- SQLite 会话与消息存储已接入 `/chat`，支持会话历史和用户权限隔离；保留第六周第一天SQL学习示例
- Markdown标题路径和产品标题元数据、正文切片、本地Chroma向量入库与检索、BGE重排序命令行实验


## 首版计划支持的功能

- 查询旅行产品、景点、路线、交通和政策资料；
- 根据客户人数、天数、预算和偏好筛选候选方案；
- 对路线和产品进行比较；
- 根据给定单价和计价单位进行确定性分项报价；
- 生成带资料来源和有效期的行程草案；
- 资料缺失、冲突或过期时提醒员工确认。

## 暂不支持的功能

- 不使用爬虫自动收集旅游资料
- 不识别扫描版 PDF，不提供 OCR 功能
- 不解析图片和复杂表格
- 不提供实时天气、客流、交通和票价信息
- 不提供订票、酒店预订和支付功能
- 不保证覆盖杭州全部景点和路线
- 暂不回答杭州以外地区的旅游问题
- 不把系统生成的报价视为旅行社最终报价
- 不自动生成合同或代替员工确认行程

## 第一版知识范围
第一版继续使用8～15份杭州公开旅游资料，并增加少量项目模拟业务资料，包括旅行产品、价格规则、退改规则和供应商说明。模拟资料必须明确标注，不代表真实旅行社内部数据或实际报价。

# 项目结构

- app/: 项目主要代码
- data/raw/: 待处理的公开旅游资料和已标注的模拟业务资料
- logs: 程序运行日志
- tests/: 自动化测试
- .env.example: 环境变量配置示例
- requirements.txt: Python 依赖列表

# 环境与安装

建议使用python 3.10 或者更高版本

创建虚拟环境：

```powershell
python -m venv .venv
```

激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

安装依赖：

```powershell
python -m pip install -r requirements.txt
```



## 当前支持的文档处理

- 读取 UTF-8 编码的 TXT 和 Markdown 文件
- 按自然段整理 TXT 和 Markdown 内容
- 使用 pypdf 逐页提取文字型 PDF
- 保留 PDF 的真实页码和来源信息
- 对空白 PDF 页面和损坏 PDF 给出明确结果



## 当前限制

- 暂不支持扫描型 PDF 和 OCR
- 暂不保证复杂表格、多栏排版的提取效果
- 向量召回与重排序目前通过命令行示例运行，尚未接入 `/chat` 的回答生成及可核验引用
- 来源链接未经程序核验；模型函数返回的错误暂时统一映射为 502


## 运行测试

```powershell
python -m pytest -v
```



## SQLite 文档登记

- 使用 `data/documents.db` 持久保存文档登记信息
- `init_db()` 初始化 `documents` 表
- `register_document()` 使用参数化 SQL 登记文档
- 使用 `file_hash` 唯一约束识别重复内容
- 保存处理状态和错误信息
- 重复登记返回 `False`，不会中断程序
- 本地数据库文件已加入 `.gitignore`



## 启动 API 服务

```
python -m uvicorn app.api:app --reload
```
配置模型环境变量、激活虚拟环境、从项目根目录运行，以及 http://127.0.0.1:8000/docs

## 第六周第一天 SQL 练习

这些是学习演示脚本，不是已接入 API 的会话存储模块。四个脚本只使用 Python 标准库，不调用模型 API。

- `examples/week6_day1_sql.py`：创建会话与消息表，启用外键，参数化写入和读取消息。
- `examples/week6_day1_read.py`：读取已有会话，验证合法关联与回滚、级联删除、其他会话不受影响，并练习 JOIN 与时间排序。测试中的写入、删除和时间修改最后回滚。
- `examples/week6_day1_user_test.py`：将创建会话和首条消息作为一组操作，演示成功提交与重新连接后的持久化读取。把消息内容改为 `None` 可验证约束失败后整组回滚。
- `examples/week6_day1_index.py`：比较联合索引创建前后的查询计划，并使用 JOIN 按用户筛选消息。

从项目根目录运行，例如：

```powershell
.\.venv\Scripts\python.exe examples\week6_day1_sql.py
```

`week6_day1_sql.py` 每次运行会新增两个会话和四条消息；`week6_day1_user_test.py` 的成功分支每次会新增一个测试会话和一条消息。只查询旧数据时不要重复执行这些 INSERT。

`week6_day1_read.py` 和索引示例保留课堂数据编号：会话 15、16，消息 18、19。新环境首次运行写入脚本会生成不同编号，需根据实际输出调整示例中的查询编号和排序测试消息编号；两条排序测试消息应属于要查询的会话。不存在或没有消息的会话不能作为级联删除验证的充分证据。

`week6_chat_demo.db` 与 `week6_chat_2_demo.db` 是本地生成的练习数据库，不进入 Git。不要将误拼的 `week_chat_demo.db` 当作原数据库。

索引一旦创建会保留，再次运行时两次查询计划都可能使用该索引。已观察到原查询计划从 `SCAN messages` 加临时排序，变为使用 `idx_messages_conversation_time` 的 `SEARCH`；尚未测量实际耗时提升。之前的 49 项核心自动测试不包含这些手工 SQL 实验。

## 第七周向量检索与重排序实验

- Embedding：`BAAI/bge-m3`，使用归一化的1024维稠密向量。
- 向量化输入：完整标题路径加正文；Chroma分别保存原正文和来源元数据。
- 当前批量切片配置：400字符、80字符重叠；标题和纯来源编号行不生成正文切片。
- 本地向量库目录：`data/chroma/`；当前索引与查询示例使用集合 `travel_documents_bge_m3_titles_v4`。
- 召回：最多5条候选；`where` 可按已确认的产品元数据限定范围，当前查询示例保留全库检索实验的 `where=None`。
- 重排序：`BAAI/bge-reranker-v2-m3`，对问题和候选文本联合打分，再按原文档与段落筛选最多2条证据。段落筛选是实验规则，不能保证证据充分或产品一致。
- 两个模型输入上限设为512 token，使用CUDA与半精度；召回完成后Embedding移到CPU，腾出显存供Reranker使用。
- 当前已验证环境为Python 3.10、PyTorch `2.13.0+cu130`。运行GPU示例需另行准备兼容的CUDA版PyTorch。
- `app/embedding.py` 和查询示例使用 `local_files_only=True`，需先准备两个模型的本地Hugging Face缓存；模型权重不进入Git。

在项目根目录运行：

```powershell
python -m examples.week7_day1_chunking
python -m examples.week7_day2_index
python -m examples.week7_day2_reload
```

索引脚本会写入本地集合，`upsert` 不会自动删除旧切片。切片参数或Embedding输入发生变化时，应使用新集合或明确重建对应集合，不能仅凭本次处理数判断没有旧记录。

`examples/week7_day2_embedding.py` 保留基础向量示例，`examples/week7_day3_reranker.py` 保留固定候选打分示例。检索实验记录位于 `examples/week6_day5_quetions.md`；这些开发题结果不代表整个知识库的召回率。

原始资料和构建脚本进入Git，`data/chroma/`、SQLite数据库、模型缓存、密钥和运行日志不进入Git。
