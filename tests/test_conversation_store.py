import pytest

import app.conversation_store as store

#独立的临时数据库
@pytest.fixture(autouse=True)
def isolated_db(tmp_path,monkeypatch):
    monkeypatch.setattr(store,"DB_PATH",tmp_path/"test_conversation.db")
    store.init_db()

def make_conversation(owner_id="user_a"):
    return store.create_conversation_with_turn("杭州三日",owner_id,"帮我规划杭州三日游","可以安排西湖和灵隐寺")

# 保存后读取，得到的草案和保存前一致
def test_save_and_get_draft():
    conversation_id = store.create_conversation_with_turn(
        "杭州三日", "user_a", "帮我规划杭州三日游", "可以安排西湖和灵隐寺"
    )
    draft = {
        "name": "杭州三日",
        "adults": 2,
        "prices": {"adult": {"meal_price": 300.0, "boat_price": None}},
    }

    store.save_draft(conversation_id, draft)

    assert store.get_draft(conversation_id) == draft

#重复保存
def test_save_draft_overwrites():
    conversation_id=make_conversation()

    store.save_draft(conversation_id,{"name":"第一版"})
    store.save_draft(conversation_id,{"name":"第二版"})

    assert store.get_draft(conversation_id)=={"name":"第二版"}

    conn=store.get_connection()
    count=conn.execute("SELECT COUNT(*) FROM conversation_drafts").fetchone()[0]
    conn.close()
    assert count==1

#没有草案
def test_get_missing_draft():
    conversation_id=make_conversation()

    assert store.get_draft(conversation_id) is None


#删除会话，草案协同
def test_delete_conversation_removes_draft():
    conversation_id=make_conversation()

    store.save_draft(conversation_id, {"name": "杭州三日"})

    store.delete_conversation(conversation_id)

    assert store.get_draft(conversation_id) is None
