"""用假模型、假检索和假存储验证CLI接线，不加载GPU或访问真实数据库/API。"""
import runpy
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock


def fake_module(monkeypatch, name, **attributes):
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    monkeypatch.setitem(__import__("sys").modules, name, module)


def test_two_turns_resolve_history_once_and_do_not_feed_old_answers_to_generation(monkeypatch, capsys):
    first = "西湖拍照有什么推荐？"
    second = "9人团328元，原价428元、减100元，是228元吗？"
    normalized = ["西湖推荐拍照位置及安全注意事项？", second]
    history = [
        {"role": "user", "content": first},
        {"role": "assistant", "content": "旧回答，仅用于测试指代处理。"},
    ]
    rewrite = Mock(side_effect=[
        {"answer": normalized[0], "error": "", "record": None, "used_history": []},
        {"answer": normalized[1], "error": "", "record": None, "used_history": []},
    ])
    retrieve = Mock(return_value=[{
        "chunk_id": "one", "content": "测试证据", "metadata": {"source_id": "S06"},
        "retrieval_rank": 1, "rerank_rank": 1,
    }])
    answer = Mock(side_effect=[
        {"data": {"answer": "旧回答，仅用于测试指代处理。", "sources": []}, "citations": [], "error": ""},
        {"data": {"answer": "需核对商品条件。", "sources": []}, "citations": [], "error": ""},
    ])
    create_turn = Mock(return_value=123)
    save_turn = Mock()
    fake_module(monkeypatch, "app.embedding", load_embedding_model=Mock(return_value=Mock()))
    fake_module(monkeypatch, "app.vector_store", get_vector_collection=Mock(return_value=object()))
    fake_module(monkeypatch, "app.reranker", load_reranker=Mock(return_value=Mock()))
    fake_module(monkeypatch, "app.retrieval", retrieve_evidence=retrieve)
    fake_module(monkeypatch, "app.query_rewriter", rewrite_retrieval_question=rewrite)
    fake_module(monkeypatch, "app.rag_answer", generate_rag_answer=answer)
    fake_module(
        monkeypatch, "app.conversation_store", init_db=Mock(), get_messages=Mock(return_value=history),
        create_conversation_with_turn=create_turn, save_turn=save_turn,
    )
    inputs = iter([first, second, "退出"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))
    script = Path(__file__).resolve().parents[1] / "examples" / "week7_full_retrieval.py"
    runpy.run_path(str(script), run_name="__main__")

    assert rewrite.call_count == 2
    assert rewrite.call_args_list[0].args == (first, [])
    assert rewrite.call_args_list[1].args == (second, history)
    assert [call.args[0] for call in retrieve.call_args_list] == normalized
    for call in retrieve.call_args_list:
        assert call.kwargs["n_results"] == 5
        assert call.kwargs["top_k"] == 2
    for index, call in enumerate(answer.call_args_list):
        assert "history" not in call.kwargs
        assert call.kwargs["retrieval_question"] == normalized[index]
    assert answer.call_args_list[0].args[0] == first
    assert answer.call_args_list[1].args[0] == second
    assert create_turn.call_args.kwargs["user_content"] == first
    save_turn.assert_called_once_with(123, second, "需核对商品条件。")
    output = capsys.readouterr().out
    assert "检索问题：" in output
    assert "用于补全的历史序号：" in output
