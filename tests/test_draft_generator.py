import pytest
from pydantic import ValidationError

from app.draft_generator import ExtractedDraft, to_draft
from unittest.mock import Mock

from app.draft_generator import format_conversation, generate_draft



def test_to_draft_keeps_unknown_price_as_none():
    extracted = ExtractedDraft(
        name="杭州两日游",
        start_date="2026-11-08",
        adults=2,
        days=[{"spots": ["西湖"], "hotel": "湖滨酒店", "notes": ""}],
        adult_prices={"meal_price": 80, "guide_price": 0},
        rooms=[{"room_type": "双床房", "rooms": 1, "nights": 1}],
    )

    draft = to_draft(extracted, 7)

    assert draft["conversation_id"] == 7
    assert draft["start_date"] == "2026-11-08"
    assert draft["days"][0]["spots"][0]["name"] == "西湖"
    assert draft["prices"]["adult"]["guide_price"] == 0
    assert draft["prices"]["adult"]["ticket_price"] is None
    assert draft["lodging_mode"] == "items"


def test_to_draft_keeps_blank_day_when_no_route():
    draft = to_draft(ExtractedDraft(), 7)

    assert len(draft["days"]) == 1
    assert draft["lodging_mode"] == "unknown"


def test_negative_price_is_rejected():
    with pytest.raises(ValidationError):
        ExtractedDraft(adult_prices={"meal_price": -1})

#zhicun
def test_format_conversation_drops_oldest_when_too_long():
    messages = [
        {"role": "user", "content": "旧" * 10},
        {"role": "assistant", "content": "新" * 10},
    ]

    text = format_conversation(messages, max_chars=15)

    assert "新" in text
    assert "旧" not in text


#测试正常流程
def test_generate_draft_reads_model_json(monkeypatch):
    fake_model = Mock(return_value={
        "answer": '{"name":"杭州两日游","adults":2,"adult_prices":{"meal_price":80}}',
        "record": None,
        "error": "",
    })
    monkeypatch.setattr("app.draft_generator.call_model", fake_model)

    result = generate_draft([{"role": "user", "content": "两位成人餐费80"}], 7)

    assert result["error"] == ""
    assert result["draft"]["name"] == "杭州两日游"
    assert result["draft"]["prices"]["adult"]["meal_price"] == 80
    assert result["draft"]["prices"]["adult"]["ticket_price"] is None


#测试有无记录
def test_generate_draft_rejects_bad_json(monkeypatch):
    fake_model = Mock(return_value={"answer": "不是JSON", "record": None, "error": ""})
    monkeypatch.setattr("app.draft_generator.call_model", fake_model)

    result = generate_draft([{"role": "user", "content": "内容"}], 7)

    assert result["draft"] is None
    assert result["error"] == "草案整理失败，请重试"


#测试没有消息时的反应
def test_generate_draft_skips_model_without_messages(monkeypatch):
    fake_model = Mock()
    monkeypatch.setattr("app.draft_generator.call_model", fake_model)

    result = generate_draft([], 7)

    assert result["draft"] is None
    fake_model.assert_not_called()


from app.draft_generator import draft_to_context

#这里测试文件前端返回整理
def test_draft_context_keeps_zero_and_skips_unknown():
    extracted = ExtractedDraft(
        destination="杭州",
        days=[{"spots": ["西湖"]}],
        adult_prices={"meal_price": 80, "guide_price": 0},
    )

    text = draft_to_context(to_draft(extracted, 7))

    assert "餐饮80.0元" in text
    assert "导游0.0元" in text
    assert "门票" not in text
    assert "第1天：西湖" in text


def test_draft_context_has_length_limit():
    extracted = ExtractedDraft(name="杭州", destination="杭" * 5000)

    assert len(draft_to_context(to_draft(extracted, 7))) == 1500


