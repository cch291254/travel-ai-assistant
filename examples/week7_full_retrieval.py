import time

from app.embedding import load_embedding_model
from app.vector_store import get_vector_collection
from app.reranker import load_reranker
from app.retrieval import retrieve_evidence
from app.rag_context import build_context
from app.rag_answer import generate_rag_answer
from app.conversation_store import (
    init_db,
    get_messages,
    create_conversation_with_turn,
    save_turn,
)
from app.query_rewriter import rewrite_retrieval_question


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

    # 等待补充时，把尚未解决的原问题一起交给改写。
    rewrite_input = question
    if pending_question is not None:
        rewrite_input = (
            pending_question
            + "\n用户补充信息："
            + question
        )

    rewrite_result = rewrite_retrieval_question(
        rewrite_input,
        history,
    )
    print("改写调用统计：", rewrite_result["record"])
    if rewrite_result["error"]:
        print("问题改写失败：", rewrite_result["error"])
        if DEBUG:
            print("改写返回文本：", rewrite_result["answer"])
        print("本轮处理耗时秒：", round(time.perf_counter() - round_start, 3))
        continue

    retrieval_question = rewrite_result["answer"].strip()
    if DEBUG:
        print("本轮历史消息数：", len(history))
        print("改写输入：", rewrite_input)
        print("改写后的完整问题：", retrieval_question)
        print("使用的历史聊天序号：", rewrite_result["used_history"])
        print("是否需要澄清：", rewrite_result["needs_clarification"])

    if rewrite_result["needs_clarification"]:
        pending_question = rewrite_input
        assistant_content = rewrite_result["clarification_question"]
        print("需要补充的信息：", assistant_content)
        print("本轮仅澄清，未调用检索和回答模型；输入“取消追问”可换题。")

        round_seconds = time.perf_counter() - round_start
        print("本轮处理耗时秒：", round(round_seconds, 3))

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
        continue

    # 补充已完成，不把原问题带入后续独立提问。
    pending_question = None

    # 只在目标来源明确时限定检索范围。
    target_source_ids = rewrite_result["target_source_ids"]
    where = None

    if target_source_ids:
        where = {
            "source_id": {"$in": target_source_ids}
        }

    if DEBUG:
        print("目标来源编号：", target_source_ids)
        print("检索筛选条件：", where)

    # 每个子问题分别召回和重排，合并时按片段编号去重。
    sub_questions = rewrite_result["sub_questions"]

    evidence = []
    seen_chunk_ids = set()

    for query_index, sub_question in enumerate(sub_questions, start=1):
        if DEBUG:
            print("实际检索子问题：", query_index, sub_question)
        branch_evidence = retrieve_evidence(
            sub_question,
            model,
            collection,
            reranker,
            where=where,
            n_results=5,
            top_k=2
        )

        for item in branch_evidence:
            if item["chunk_id"] not in seen_chunk_ids:
                seen_chunk_ids.add(item["chunk_id"])
                evidence.append(item)

    if DEBUG:
        for citation_id, item in enumerate(evidence, start=1):
            print(
                f"资料[{citation_id}] 来源：{item['metadata'].get('source_id', '未提供')}，"
                f"召回位置：{item['retrieval_rank']}，重排位置：{item['rerank_rank']}，"
                f"片段：{item['chunk_id']}"
            )
            print("正文：", item["content"])

    # 把证据整理成大模型能阅读的上下文
    context_result = build_context(evidence)

    # 根据证据生成回答
    answer_result = generate_rag_answer(
        question,
        context_result,
        retrieval_question=retrieval_question,
    )

    print("回答调用统计：", answer_result["record"])

    round_seconds = time.perf_counter() - round_start
    print("本轮处理耗时秒：", round(round_seconds, 3))
    if answer_result["error"] or answer_result["data"] is None:
        print("回答失败：", answer_result["error"] or "未返回可用回答")
        continue

    assistant_content = answer_result["data"]["answer"]
    print("最终回答：", assistant_content)
    print("引用编号：", answer_result["data"]["sources"])

    # 保存用户原始输入和回答，不保存拼接后的改写输入。
    if conversation_id is None:
        conversation_id=create_conversation_with_turn(
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
