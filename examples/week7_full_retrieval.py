import time

from app.embedding import load_embedding_model
from app.vector_store import get_vector_collection
from app.reranker import load_reranker
from app.conversation_store import (
    init_db,
    get_messages,
    create_conversation_with_turn,
    save_turn,
)
from app.rag_pipeline import run_rag

# 普通运行只显示回答、调用统计和耗时；排查检索时改为 True。
DEBUG = False
MAX_HISTORY_TURNS = 3

# 初始化数据库和模型，不计入每轮处理耗时。
init_db()
conversation_id = None
pending_question = None


collection=get_vector_collection("travel_documents_full_20161014_v1")
model=load_embedding_model()
model.to("cpu")
reranker=load_reranker()


while True:
    question = input("请输入问题（退出 / 取消追问）：").strip()
    if question == "退出":
        break

    if not question:
        print("问题不能为空")
        continue

    if question == "取消追问":
        pending_question = None
        print("已取消当前追问，可以输入新问题")
        continue

    round_start = time.perf_counter()

    # 读取最近三轮历史。
    history = []

    if conversation_id is not None:
        history = get_messages(conversation_id)
        history = history[-MAX_HISTORY_TURNS * 2:]

        # 业务流程统一交给 run_rag
    result = run_rag(
        question=question,
        history=history,
        model=model,
        collection=collection,
        reranker=reranker,
        pending_question=pending_question,
    )

    # 接住状态，供下一轮输入使用
    pending_question = result["pending_question"]

    print("改写调用统计：", result["rewrite_record"])
    if result["record"] is not None:
        print("回答调用统计：", result["record"])

    round_seconds = time.perf_counter() - round_start
    print("本轮处理耗时秒：", round(round_seconds, 3))

    # 失败时不保存为成功的聊天记录
    if result["error"]:
        print("本轮处理失败：", result["error"])
        continue

    if result["data"] is None:
        print("本轮处理失败：未返回可用结果")
        continue

    assistant_content = result["data"]["answer"]

    if result["needs_clarification"]:
        print("需要补充的信息：", assistant_content)
        print("本轮仅澄清；输入“取消追问”可换题。")
    else:
        print("最终回答：", assistant_content)
        print("引用编号：", result["data"]["sources"])

    # 排查时查看本轮实际保留的证据
    if DEBUG:
        for citation_id, item in enumerate(result["evidence"], start=1):
            print(f"资料[{citation_id}] 片段：{item['chunk_id']}")
            print("正文：", item["content"])

    # 澄清追问和正常回答共用这一段保存逻辑
    # 保存的是用户原话，不是拼接后的检索问题
    if conversation_id is None:
        conversation_id = create_conversation_with_turn(
            title=question[:30],
            owner_id="user_a",
            user_content=question,
            assistant_content=assistant_content,
        )
    else:
        save_turn(
            conversation_id,
            question,
            assistant_content,
        )

    print("当前会话编号：", conversation_id)
