from unittest.mock import Mock

import pytest

from app import setup_data


def test_collect_chunks_reads_markdown_only(tmp_path, monkeypatch):
    (tmp_path / "b.md").write_text("b", encoding="utf-8")
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / "skip.txt").write_text("c", encoding="utf-8")
    monkeypatch.setattr(setup_data, "parse_document", lambda path: [path.name])
    monkeypatch.setattr(setup_data, "add_source_id", lambda records: records)
    monkeypatch.setattr(
        setup_data, "split_records",
        lambda records, chunk_size, overlap: records,
    )

    assert setup_data.collect_chunks(tmp_path) == ["a.md", "b.md"]


def test_build_index_skips_existing_collection(monkeypatch):
    collection = Mock()
    collection.count.return_value = 5
    fake_collect = Mock()
    monkeypatch.setattr(setup_data, "get_vector_collection", lambda name: collection)
    monkeypatch.setattr(setup_data, "collect_chunks", fake_collect)

    setup_data.build_index()

    fake_collect.assert_not_called()


def test_build_index_fails_when_collection_stays_empty(monkeypatch):
    collection = Mock()
    collection.count.return_value = 0
    monkeypatch.setattr(setup_data, "get_vector_collection", lambda name: collection)
    monkeypatch.setattr(setup_data, "collect_chunks", lambda raw_dir: [])
    monkeypatch.setattr(setup_data, "upsert_chunks", Mock(return_value=0))
    monkeypatch.setattr("app.embedding.load_embedding_model", Mock())

    with pytest.raises(RuntimeError, match="仍然为空"):
        setup_data.build_index()


def test_download_models_keeps_only_needed_files(monkeypatch):
    fake_download = Mock()
    monkeypatch.setattr(setup_data, "snapshot_download", fake_download)

    setup_data.download_models()

    assert fake_download.call_count == 2
    fake_download.assert_any_call(
        "BAAI/bge-m3",
        ignore_patterns=setup_data.IGNORED_MODEL_FILES,
    )
