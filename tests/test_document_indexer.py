from unittest.mock import Mock

from app.document_indexer import index_document


def test_index_docment(tmp_path):
    file_path=tmp_path/"guide.md"
    file_path.write_text(
        "# S07 测试资料\n\n集合时间为09:50。",
        encoding="utf-8",
    )

    collection=Mock()
    collection.get.return_value = {
        "ids": [
            "guide:paragraph-2:chunk-1",
            "guide:paragraph-3:chunk-1",
        ]
    }

    model=Mock()
    model.encode.return_value.tolist.return_value=[[0.1,0.2]]

    result=index_document(file_path,model,collection)

    assert result == {
        "document_id": "guide",
        "written": 1,
        "deleted": 1,
    }

    collection.get.assert_called_once_with(
        where={"document_id": "guide"}
    )
    collection.upsert.assert_called_once()

    saved = collection.upsert.call_args.kwargs
    assert saved["ids"] == ["guide:paragraph-2:chunk-1"]
    assert saved["documents"] == ["集合时间为09:50。"]
    assert saved["metadatas"][0]["source_id"] == "S07"

    collection.delete.assert_called_once_with(
        ids=["guide:paragraph-3:chunk-1"]
    )