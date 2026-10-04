from examples.week5_day4_structured_output import parse_structured_answer
import examples.week5_day4_structured_output as structured_output


def test_vaild_structured_answer():
    raw_text='{"answer":"推荐西湖","sources":["官网"]}'
    result=parse_structured_answer(raw_text)

    assert result["error"]==""
    assert result["data"]["answer"]=="推荐西湖"
    assert result["data"]["sources"][0]=="官网"

def test_invalid_json():
    raw_text="推荐西湖"
    result=parse_structured_answer(raw_text)

    assert result["error"]!=""
    assert result["data"]==None

def test_missing_sourcess():
    raw_text='{"answer":"推荐西湖"}'
    result=parse_structured_answer(raw_text)

    assert "sources" in result["error"]
    assert result["data"] is None

def test_sources_erong_type():
    raw_text='{"answer":"推荐西湖","sources":"官网"}'
    result=parse_structured_answer(raw_text)

    assert "sources" in result["error"]
    assert "valid list" in result["error"]
    assert result["data"] is None
    

def test_call_structured_model_success(monkeypatch):
    def fake_call_model(question, system_prompt,json_mode=False):
        assert json_mode is True
        return {
    "answer": '{"answer": "推荐西湖", "sources": ["官网"]}',
    "error": "",
    "record": {"状态码": 200},
}
    monkeypatch.setattr(
        structured_output,"call_model",fake_call_model
    )
    result = structured_output.call_structured_model("推荐杭州景点")

    assert result["error"]==""
    assert result["data"]["answer"]=="推荐西湖"
    assert result["record"]["状态码"]==200

def test_call_structured_model_api_error(monkeypatch):
    def fake_call_model(question,system_prompt,json_mode=False):
        assert json_mode is True

        return {
    "answer": "",
    "error": "HTTP请求失败，状态码401",
    "record": {"状态码": 401},
}
    monkeypatch.setattr(
        structured_output,"call_model",fake_call_model
    )
    result=structured_output.call_structured_model("推荐杭州景点")

    assert result["error"]=="HTTP请求失败，状态码401"
    assert result["record"]["状态码"]==401
    assert result["data"] is None

def test_call_structured_model_invalid_json(monkeypatch):
    def fake_call_model(question,system_prompt,json_mode=False):
        assert json_mode is True

        return {
    "answer": "推荐西湖",
    "error": "",
    "record": {"状态码": 200},
}
    monkeypatch.setattr(
        structured_output,"call_model",fake_call_model
    )
    result=structured_output.call_structured_model("推荐杭州景点")

    assert result["error"]!=""
    assert result["data"] is None
    assert result["record"]["状态码"]==200