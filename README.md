# 旅行社知识库与线路 Copilot

给旅行社销售和客服用的 AI 助手。员工在聊天里查产品资料、问规则、算报价，把聊到的线路整理成一条完整线路的草案，修改确认后保存成方案；确认过的方案会成为长期记忆，以后能被查到。

资料来自杭州、千岛湖的真实商品页面整理、博主分享，以及明确标注的项目模拟数据。所有价格、退改和行程都需要员工核对后才能对外承诺。

## 能做什么

| 功能 | 说明 |
|---|---|
| 资料问答 | 查产品、套餐、集合、退改、儿童票等规则，回答带引用编号，可展开看原文 |
| 先问清楚再答 | 商家或套餐不明确时先追问，员工补充后自动承接原问题 |
| 算报价 | 按成人、儿童单价和住宿明细算已知费用；没提供的价格不当作 0 元 |
| 网络搜索 | 资料库以外的问题（其他城市、官方最新公告）上网查，并给出来源 |
| 整理完整线路 | 员工说“整理成草案”或点“整理完整线路”，以当前草案为准，用聊天记录和自家资料补齐行程、用餐、住宿、接车集合、注意事项和商家声明；员工填过的内容不会被改，和聊天不一致的列进待确认；价格只认对话里出现过的金额 |
| 方案管理 | 草案保存成方案，带版本号；状态为草案 → 待确认 → 已确认 |
| 长期记忆 | 已确认的方案写入独立向量库，员工以后可以查“之前做过的方案”，只能查到自己的 |

## 工作方式

```text
员工提问
  → 模型决定调用哪些工具：知识库检索、方案检索、算价、网络搜索、网页抓取、保存草案
  → 第一次知识库检索时重写问题：结合员工原话补全商家和条件，判断要不要追问，拆子问题，选定资料来源
  → 需要追问：直接返回追问，不再调用回答模型
  → 否则：主问题＋子问题多路检索，按来源过滤；过滤后资料太少就查全库，再重排去重
  → 模型依据编号证据回答，程序校验引用编号确实来自本轮证据
```

**三层记忆：**

| 层级 | 内容 | 范围 |
|---|---|---|
| 短期 | 最近 3 轮对话 | 当前对话 |
| 中期 | 结构化草案（人数、日期、每日行程、用餐住宿、接车集合、价格、注意事项、待确认事项） | 这条线路的对话 |
| 长期 | 已确认方案的向量检索 | 同一员工的所有对话 |

**几个设计取舍：**

- 员工身份只由后端传给工具，模型无法指定要查谁的方案或会话。
- 每次提问最多 4 轮模型调用、5 次工具调用；最后一轮不提供工具，超限时用已有资料回答，而不是报错。
- 方案写入向量库失败只记日志，不影响员工确认；API 每次启动时自动补齐缺失的切片、删除过期切片。
- 请求体上限 1 MB，每位员工每天 50 次聊天。

## 评测结果

完整报告见 [docs/evaluation/eval_report_20261102.md](docs/evaluation/eval_report_20261102.md)。

| 题组 | 题数 | 用途 |
|---|---|---|
| 开发集 E01–E30 | 30 题、40 轮 | 用来定位问题、调提示词 |
| 留出集 H01–H16 | 16 题、20 轮 | 换问法的改写题和针对已知不足的新题，用来检查过拟合 |
| 功能题 E31–E40 | 10 题、11 轮 | 只验证算价、网络搜索、网页抓取能用，不计入主要成绩 |

**主要成绩（开发集＋留出集）：**

| 指标 | 结果 |
|---|---|
| 执行成功 | 45/46，固定 1 题失败（模型偶发返回空白，单独重跑 6 次都成功） |
| 召回（按关键信息，严格估计） | 约 91% |
| 要点覆盖 | 0.882 |
| 依据分 | 0.922 |
| 幻觉 | 2 题 |
| 平均 token/题 | 11,358（含问题重写） |
| 每轮耗时 | 平均 13.45 秒，中位数 11.44 秒 |
| 澄清 | 6 道应先追问的题，偶有漏问 |

和 10-31 的第一版基线相比（E01–E30）：要点覆盖 0.853 → 0.878，依据分 0.828 → 0.931，幻觉 4 题 → 1 题，平均 token 13,686 → 11,564。开发集与功能题 40 题全量评测，DeepSeek 后台计费 0.83 元。

**要知道的局限：**

- 每题只跑一次，结果有波动。
- 人工分由 Claude 初评、项目作者逐题复核；留出集也是在看过系统表现后编写的，不是完全独立的测试。严格估计还可能再低 5%，也不代表真实用户的使用体验。
- “证据完整命中”只看来源对不对，不看具体切片，所以显示为 50/50；按关键信息看，E12、E21 都缺了关键切片。
- 评测针对的是聊天问答。“整理完整线路”是评测之后加的，只做了离线测试和几次真实试跑（一次约 2,000 token），没有纳入上面的成绩。

## 快速开始（Docker）

需要：Docker Desktop，一个 [DeepSeek API Key](https://platform.deepseek.com/)，预留 15 GB 以上磁盘空间（镜像约 9.5 GB，含 CUDA 版 PyTorch；模型约 4.3 GB）。有 NVIDIA 显卡时用 GPU，没有也能用 CPU 跑。

**1. 配置密钥**

```bash
cp .env.example .env
```

打开 `.env`，把 `DEEPSEEK_API_KEY` 换成你的密钥。下载模型慢时，取消 `HF_ENDPOINT` 那一行的注释，改用镜像站。

**2. 首次准备：下载模型、建立向量库**

```bash
docker compose run --rm setup
```

会下载 `BAAI/bge-m3` 和 `BAAI/bge-reranker-v2-m3` 两个模型（约 4.3 GB，存在本机的 Hugging Face 缓存目录），再把 `data/raw/` 的资料切成 201 片写入 `data/chroma/`。在全新目录、CPU 下实测约 7 分钟。向量库已有数据时会跳过入库。

**3. 启动**

有 NVIDIA 显卡：

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

只用 CPU：

```bash
docker compose up -d --build
```

**4. 打开页面**

| 地址 | 内容 |
|---|---|
| <http://127.0.0.1:8502> | 员工工作台：聊天、草案、方案 |
| <http://127.0.0.1:8000/docs> | API 文档 |
| <http://127.0.0.1:8000/health> | 健康检查 |

启动时会预加载模型，API 大约要一分钟才能接收请求。第一次聊天会慢一些。

**常用操作：**

| 情况 | 命令 |
|---|---|
| 改了代码或 `.env` | 重新运行第 3 步的 `up -d --build`（`restart` 不会加载新代码和新配置） |
| 查看日志 | `docker compose logs -f api` |
| 停止 | `docker compose down`，`data/` 里的会话、方案和向量库会保留 |
| 手动补写方案索引 | `docker compose run --rm api python -m app.plan_index` |

端口只绑定在 `127.0.0.1`，本机以外访问不到。

## 不用 Docker 运行

已验证环境：Windows、Python 3.10/3.11、PyTorch 2.13（CUDA 13）。这种方式没有在全新目录里完整验证过。

```bash
python -m venv .venv
.venv/Scripts/python -m pip install torch==2.13.0 --index-url https://download.pytorch.org/whl/cu130
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m app.setup_data
.venv/Scripts/python -m uvicorn app.api:app --host 127.0.0.1 --port 8000
.venv/Scripts/python -m streamlit run app/streamlit_workspace.py --server.port 8502
```

第二条安装 CUDA 版 PyTorch；只用 CPU 时去掉 `--index-url` 及后面的地址。最后两条分别在两个终端里运行。

## 怎么用

左侧边栏的“演示身份”可以切换两个演示员工（对应 `token_a`、`token_b`），用来验证不同员工之间互相看不到会话和方案。这两个令牌是写死的演示值，不是正式的登录方案。

**可以试的问题：**

- “这个团儿童票怎么买？” → 先追问是哪家 → 回答“胜蓝旅游 18 人经典团”
- “两位客人想单独包车玩胜蓝那个一日游，两个人多少钱？几点接？”
- “2 个成人、1 个 1.1 米的孩子，成人餐费每人 150，孩子 60，订 1 间家庭房 1 晚 450，帮我算一下”
- “就按这个整理成草案” → 右侧出现草案 → 手动修改后点“整理完整线路”补齐接车、用餐和注意事项，展开“完整线路预览”核对 → “保存方案” → “标记为待确认” → “标记为已确认”
- 新开对话问“我之前做过的杭州两日游方案，餐费多少？”

一条线路建议用一个对话；做另一条线路时点“新建对话”。

**主要接口**（除健康检查外，都要带 `Authorization: Bearer token_a`）：

| 接口 | 作用 |
|---|---|
| `POST /chat` | 聊天；返回回答、引用、证据，要求保存时还会返回生成的草案 |
| `GET /conversations`、`GET/DELETE /conversations/{id}` | 会话列表、读取、删除 |
| `GET/PUT /conversations/{id}/draft` | 读取、保存草案 |
| `POST /conversations/{id}/draft/generate` | 整理完整线路；可在请求体带上页面当前草案，不带时用自动保存的草稿 |
| `POST/GET /plans`、`GET/PUT/DELETE /plans/{id}` | 方案的新建、列表、读取、保存新版本、删除 |
| `POST /plans/{id}/status`、`POST /plans/{id}/copy` | 修改状态、复制方案 |
| `POST /quotes/calculate` | 直接算价 |

## 跑测试和评测

离线测试（不调用真实模型，不花钱）：

```bash
.venv/Scripts/python -m pytest -q
```

2026-11-02：326 passed。测试数字只说明代码按预期运行，不代表回答准确率。

真实模型评测会产生模型费用，还要在 `.env` 里配置 Langfuse：`LANGFUSE_ENABLED=true`、`LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY`、`LANGFUSE_BASE_URL`。用法见 [examples/EVALUATION_QUICKSTART.md](examples/EVALUATION_QUICKSTART.md)：

```bash
.venv/Scripts/python -m examples.run_langfuse_eval --all
.venv/Scripts/python -m examples.run_langfuse_eval --all --dataset travel-rag-holdout-v1
.venv/Scripts/python -m examples.build_eval_report
```

## 项目结构

| 路径 | 内容 |
|---|---|
| `app/api.py` | FastAPI 接口、身份校验、额度和请求大小限制 |
| `app/tool_calling.py` | 工具调用循环、轮数和次数限制、引用校验 |
| `app/tools.py`、`app/tool_schemas.py` | 工具定义和实现：检索规划、多路检索、算价、网络搜索、保存草案 |
| `app/query_rewriter.py`、`app/source_catalog.py` | 问题重写、澄清判断、来源选择 |
| `app/retrieval.py`、`app/reranker.py`、`app/embedding.py` | 向量召回和重排 |
| `app/draft_generator.py`、`app/workspace_plan.py` | 整理完整线路（合并草案、检查价格和来源）、草案结构、线路预览 |
| `app/plan_store.py`、`app/plan_index.py` | 方案和版本、已确认方案的长期记忆 |
| `app/conversation_store.py` | 会话、消息、草案、每日额度（SQLite） |
| `app/streamlit_workspace.py`、`app/workspace_api.py` | 员工工作台页面 |
| `app/setup_data.py` | 首次准备：下载模型、建立向量库 |
| `data/raw/` | 知识资料 |
| `examples/` | 评测脚本、评测题目 |
| `docs/evaluation/` | 评测报告、留出集方案、历史评审 |
| `archive/` | 已不再使用的练习脚本、旧问答流程和模型评分，保留作记录 |

## 限制和安全边界

- 不提供订票、支付、实时库存或房态；不会替员工联系商家或完成预订。
- 价格、退改和接送规则都是参考，需要员工确认；模拟资料（SIM 开头）不代表真实报价。
- 只支持文字资料，不做图片识别；资料只有 201 片，规模很小。
- 演示令牌不是正式登录；同一时间只处理一个聊天请求（单进程加锁），没有做多实例部署。
- 已知问题：员工说“先记下来”时，模型有时会直接保存草案；回答 JSON 偶尔为空；同一来源里的关键切片偶尔查不到。
- 按份计价的套餐价（例如成人 258 元/份）放不进六项单价，整理时会列进待确认，需要员工手动处理。

## 后续计划

- 员工登录、资料管理页面
- 完整线路导出（PDF 或发给客人的文字）、套餐价字段
- 继续降低 token 消耗
- 关键词检索（BM25）对比实验，给评测题标注关键事实、计算切片级召回
- 修正“先记下来”触发保存、空回答自动重试

## 资料说明

`data/raw/` 中的商品信息整理自公开的平台商品页面和博主分享，仅用于学习演示，未经商家核验，可能已经过期。项目没有收录原始截图。
