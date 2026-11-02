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


def test_cli_passes_pending_question_and_saves_turns(monkeypatch, capsys):
    first = "晚上23:10下单，能保证30分钟内收到接车通知吗？"
    second = "艾客旅游千岛湖套餐1"
    clarification = "您预订的是哪个产品或套餐？"
    final_answer = "不能保证下单后30分钟内收到最终接车通知。"

    history = [
        {"role": "user", "content": first},
        {"role": "assistant", "content": clarification},
    ]

    # 模拟两轮 run_rag 返回：第一轮追问，第二轮回答
    pipeline = Mock(side_effect=[
        {
            "data": {"answer": clarification, "sources": []},
            "citations": [],
            "evidence": [],
            "rewrite_record": {"总tokens": 30},
            "record": None,
            "error": "",
            "needs_clarification": True,
            "pending_question": first,
        },
        {
            "data": {"answer": final_answer, "sources": []},
            "citations": [],
            "evidence": [],
            "rewrite_record": {"总tokens": 40},
            "record": {"总tokens": 50},
            "error": "",
            "needs_clarification": False,
            "pending_question": None,
        },
    ])

    conversation_id = Mock(return_value=123)
    save_turn = Mock()
    get_messages = Mock(return_value=history)

    # 入口会导入这些模块，提前放入替身，避免真实初始化
    fake_module(
        monkeypatch, "app.embedding",
        load_embedding_model=Mock(return_value=Mock()),
    )
    fake_module(
        monkeypatch, "app.vector_store",
        get_vector_collection=Mock(return_value=object()),
    )
    fake_module(
        monkeypatch, "app.reranker",
        load_reranker=Mock(return_value=Mock()),
    )
    fake_module(
        monkeypatch, "app.rag_pipeline",
        run_rag=pipeline,
    )
    fake_module(
        monkeypatch, "app.conversation_store",
        init_db=Mock(),
        get_messages=get_messages,
        create_conversation_with_turn=conversation_id,
        save_turn=save_turn,
    )

    # 用预设输入代替键盘输入，最后退出循环
    inputs = iter([first, second, "退出"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))

    script = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "week7_full_retrieval.py"
    )
    runpy.run_path(str(script), run_name="__main__")

    # 两次问题调用业务流程，“退出”不调用
    assert pipeline.call_count == 2
    first_call = pipeline.call_args_list[0].kwargs
    second_call = pipeline.call_args_list[1].kwargs

    assert first_call["question"] == first
    assert first_call["history"] == []
    assert first_call["pending_question"] is None

    # 上轮返回的待补充问题，被入口传入下一轮
    assert second_call["question"] == second
    assert second_call["history"] == history
    assert second_call["pending_question"] == first

    # 首轮创建会话并保存追问，次轮保存补充原话和答案
    conversation_id.assert_called_once_with(
        title=first[:30],
        owner_id="user_a",
        user_content=first,
        assistant_content=clarification,
    )
    get_messages.assert_called_once_with(123)
    save_turn.assert_called_once_with(123, second, final_answer)

    output = capsys.readouterr().out
    assert "需要补充的信息：" in output
    assert "最终回答：" in output
    assert final_answer in output