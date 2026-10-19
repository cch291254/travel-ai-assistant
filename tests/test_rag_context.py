from copy import deepcopy

from app.rag_context import build_context


def test_empty_evidence_has_no_context_or_citation_map():
    assert build_context([]) == {"context": "", "source_map": {}}


def test_citation_numbers_are_distinct_from_shared_source_id():
    evidence = [
        {"chunk_id": "one", "content": "第一片。", "metadata": {"source_id": "S02"}},
        {"chunk_id": "two", "content": "第二片。", "metadata": {"source_id": "S02"}},
    ]
    original = deepcopy(evidence)
    result = build_context(evidence)

    assert "[1]\n引用编号：1\n来源标识（非引用编号）：S02" in result["context"]
    assert "[2]\n引用编号：2\n来源标识（非引用编号）：S02" in result["context"]
    assert list(result["source_map"]) == ["1", "2"]
    assert result["source_map"]["1"]["chunk_id"] == "one"
    assert result["source_map"]["2"]["chunk_id"] == "two"
    assert "S02" not in result["source_map"]
    assert evidence == original


def test_missing_source_id_does_not_remove_local_citation_number():
    result = build_context([
        {"chunk_id": "one", "content": "测试片段。", "metadata": {}},
    ])

    assert "引用编号：1" in result["context"]
    assert "来源标识（非引用编号）：未提供" in result["context"]
    assert result["source_map"]["1"] == {"chunk_id": "one", "metadata": {}}
