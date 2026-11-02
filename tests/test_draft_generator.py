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




from app.draft_generator import check_extracted, collect_route_evidence, merge_draft
from app.workspace_plan import empty_draft, new_day, normalize_draft, route_markdown


def staff_draft():
    draft = empty_draft()
    draft.update(name="杭州两日游", adults=2, children=1, start_date="2026-11-20")
    draft["days"] = [new_day(["西湖"], "湖滨银泰附近"), new_day(["灵隐寺"])]
    draft["prices"]["adult"]["meal_price"] = 150
    return draft


def generated_draft(**changes):
    extracted = ExtractedDraft(
        name="别的名字", merchant="胜蓝旅游18人经典团", adults=2, children=1,
        start_date="2026-11-20", pickup="08:00上门接",
        days=[
            {"spots": ["断桥"], "hotel": "另一家酒店", "meals": "午餐自理"},
            {"spots": ["灵隐寺"], "meals": "素斋"},
        ],
        adult_prices={"meal_price": 150, "ticket_price": 80},
        notices=[{"text": "携带身份证", "source": "对话"}],
    )
    draft = to_draft(extracted, 7)
    draft.update(changes)
    return draft


def test_merge_keeps_staff_fields_and_fills_blanks():
    merged = merge_draft(staff_draft(), generated_draft())

    assert merged["name"] == "杭州两日游"
    assert merged["days"][0]["spots"][0]["name"] == "西湖"
    assert merged["days"][0]["hotel"] == "湖滨银泰附近"
    assert merged["days"][0]["meals"] == "午餐自理"
    assert merged["days"][1]["meals"] == "素斋"
    assert merged["merchant"] == "胜蓝旅游18人经典团"
    assert merged["pickup"] == "08:00上门接"
    assert merged["prices"]["adult"]["ticket_price"] == 80
    assert merged["notices"] == ["携带身份证"]


def test_merge_lists_conflicts_instead_of_overwriting():
    generated = generated_draft(adults=3)
    generated["prices"]["adult"]["meal_price"] = 120

    merged = merge_draft(staff_draft(), generated)

    assert merged["adults"] == 2
    assert merged["prices"]["adult"]["meal_price"] == 150
    assert "聊天里提到成人3人，草案为2人，请核对" in merged["manual_items"]
    assert "聊天里提到成人餐饮120元，草案为150元，请核对" in merged["manual_items"]


def test_merge_blank_draft_takes_generated_people():
    merged = merge_draft(empty_draft(), generated_draft(adults=4))

    assert merged["adults"] == 4
    assert merged["days"][0]["spots"][0]["name"] == "断桥"
    assert not any("人，请核对" in item for item in merged["manual_items"])


def test_check_drops_unmentioned_price_and_unknown_source():
    extracted = ExtractedDraft(
        adult_prices={"meal_price": 150, "ticket_price": 95},
        notices=[{"text": "资料里的提醒", "source": "1"}, {"text": "编出来的提醒", "source": "5"}],
    )

    checked = check_extracted(extracted, "员工：成人餐费150", evidence_count=2)

    assert checked.adult_prices.meal_price == 150
    assert checked.adult_prices.ticket_price is None
    assert [item.text for item in checked.notices] == ["资料里的提醒"]
    assert any("门票95元在对话中没有出现" in item for item in checked.open_items)


def test_generate_draft_keeps_current_draft(monkeypatch):
    fake_model = Mock(return_value={
        "answer": '{"name":"新名字","adults":2,"children":1,"adult_prices":{"meal_price":120},'
                  '"pickup":"09:00雷峰塔检票口集合"}',
        "record": None,
        "error": "",
    })
    monkeypatch.setattr("app.draft_generator.call_model", fake_model)

    result = generate_draft([{"role": "user", "content": "成人餐费120"}], 7, current=staff_draft())

    draft = result["draft"]
    assert draft["name"] == "杭州两日游"
    assert draft["prices"]["adult"]["meal_price"] == 150
    assert draft["pickup"] == "09:00雷峰塔检票口集合"
    assert "员工当前草案" in fake_model.call_args.kwargs["context"]


def fake_route_search(monkeypatch):
    calls = []

    def fake_retrieve(queries, resources, where=None):
        calls.append({"queries": queries, "where": where})
        return [{"chunk_id": str(i)} for i in range(10)]

    monkeypatch.setattr("app.tools.retrieve_routes", fake_retrieve)
    monkeypatch.setattr("app.rag_resources.get_rag_resources", lambda: {})
    return calls


def test_route_evidence_filters_named_product(monkeypatch):
    calls = fake_route_search(monkeypatch)

    evidence = collect_route_evidence([{"role": "user", "content": "报胜蓝旅游18人经典团"}])

    assert calls[0]["where"] == {"source_id": {"$in": ["S05"]}}
    assert len(evidence) == 8


def test_route_evidence_searches_own_data_by_route(monkeypatch):
    calls = fake_route_search(monkeypatch)

    collect_route_evidence([{"role": "user", "content": "整理成草案"}], staff_draft())

    assert calls[0]["where"] is None
    assert "西湖" in calls[0]["queries"][0] and "灵隐寺" in calls[0]["queries"][0]


def test_old_draft_gets_new_fields():
    old = {"days": [{"spots": [], "hotel": "", "notes": ""}]}

    normalize_draft(old)

    assert old["merchant"] == "" and old["notices"] == []
    assert old["days"][0]["meals"] == ""


def test_route_markdown_shows_whole_route():
    draft = merge_draft(staff_draft(), generated_draft())

    text = route_markdown(draft)

    assert "商家：胜蓝旅游18人经典团" in text
    assert "第1天：西湖；用餐：午餐自理；住宿：湖滨银泰附近" in text
    assert "**注意事项**" in text and "携带身份证" in text


def test_to_draft_drops_copied_blank_room_and_note():
    extracted = ExtractedDraft(
        rooms=[{"room_type": "", "rooms": 1, "nights": 1}],
        notices=[{"text": "", "source": "对话"}],
    )

    draft = to_draft(extracted, 7)

    assert draft["rooms"] == [] and draft["lodging_mode"] == "unknown"
    assert draft["notices"] == []


def test_check_drops_open_items_the_page_already_shows():
    extracted = ExtractedDraft(open_items=[
        "聊天中未提及出发日期，请确认",
        "资料[1]中地名表述不规范，请核对",
        "客人希望下午4点前结束，需与导游确认",
    ])

    checked = check_extracted(extracted, "", evidence_count=0)

    assert checked.open_items == ["客人希望下午4点前结束，需与导游确认"]
