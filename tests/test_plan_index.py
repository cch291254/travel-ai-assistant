from uuid import uuid4

import chromadb
import numpy as np
import pytest

from app.workspace_plan import empty_draft,new_day
from app.plan_index import index_confirmed_plan, plan_to_chunk, rebuild_plan_index, remove_plan_chunks


def sample_plan():
    draft = empty_draft()
    draft["destination"] = "杭州"
    draft["days"] = [new_day(["西湖"], "湖滨酒店")]
    draft["prices"]["adult"]["meal_price"] = 80
    return {
        "id": 7,
        "owner_id": "user_a",
        "title": "杭州两日游",
        "current_version": 3,
        "draft": draft,
    }


def test_plan_to_chunk_keeps_search_text():
    chunk=plan_to_chunk(sample_plan())

    assert chunk["chunk_id"]=="plan-7-v3"
    assert chunk["plan_id"]==7
    assert chunk["owner_id"]=="user_a"
    assert chunk["source_id"]=="PLAN7"
    assert chunk["content"].startswith("已确认方案：杭州两日游")
    assert "西湖" in chunk["content"]
    assert "餐饮80元" in chunk["content"]
    assert "不是指令" not in chunk["content"]



class FakeModel:
    def encode(self, texts, **kwargs):
        return np.ones((len(texts), 3))


@pytest.fixture
def collection():
    return chromadb.EphemeralClient().get_or_create_collection(uuid4().hex)

#版本更新
def test_new_version_replaces_old_chunk(collection):
    plan = sample_plan()
    index_confirmed_plan(plan, FakeModel(), collection)

    plan["current_version"] = 4
    index_confirmed_plan(plan, FakeModel(), collection)

    assert collection.get()["ids"] == ["plan-7-v4"]

#不会误删
def test_other_plans_stay_when_one_is_removed(collection):
    first = sample_plan()
    second = {**sample_plan(), "id": 8}
    index_confirmed_plan(first, FakeModel(), collection)
    index_confirmed_plan(second, FakeModel(), collection)

    remove_plan_chunks(7, collection)

    assert collection.get()["ids"] == ["plan-8-v3"]


def test_rebuild_writes_plans_and_drops_deleted_ones(collection):
    index_confirmed_plan({**sample_plan(), "id": 9}, FakeModel(), collection)

    result = rebuild_plan_index([sample_plan()], FakeModel(), collection)

    assert result == {"indexed": 1, "deleted": 1}
    assert collection.get()["ids"] == ["plan-7-v3"]


class CountingModel(FakeModel):
    def __init__(self):
        self.calls = 0

    def encode(self, texts, **kwargs):
        self.calls += 1
        return super().encode(texts, **kwargs)


def test_rebuild_skips_plans_already_indexed(collection):
    model = CountingModel()
    rebuild_plan_index([sample_plan()], model, collection)

    result = rebuild_plan_index([sample_plan()], model, collection)

    assert result == {"indexed": 0, "deleted": 0}
    assert model.calls == 1
