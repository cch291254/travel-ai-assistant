import app.conversation_store as store
import app.plan_store as plan_store
import pytest
from app.workspace_plan import empty_draft


#独立的临时数据库
@pytest.fixture(autouse=True) 
def isolated_db(tmp_path,monkeypatch):
    monkeypatch.setattr(store,"DB_PATH",tmp_path/"test_conversation.db")
    store.init_db()

def make_conversation(owner_id="user_a"):
    return store.create_conversation_with_turn("杭州三日",owner_id,"帮我规划杭州三日游","可以安排西湖和灵隐寺")

def test_create_and_get_plan():
    mock_draft={
        "name":"杭州三日游",
        "adults":2,
        "prices": {"adult": {"meal_price": "300.00", "boat_price": None}},
    }
    plan_id=plan_store.create_plan("user_a","杭州三日游",draft=mock_draft,conversation_id=None)
    plan=plan_store.get_plan(plan_id)

    assert plan["draft"]==mock_draft
    assert plan["id"]==plan_id
    assert plan["owner_id"]=="user_a"
    assert plan["title"]=="杭州三日游"
    assert plan["current_version"]==1
    assert plan["status"]=="draft"
    assert plan["conversation_id"] is None


def test_get_missing_plan():
    plan=plan_store.get_plan(999)

    assert plan is None

#验证删除会不会附带最新版本
def test_delete_conversation_keeps_plan():
    conversation_id=make_conversation()
    mock_draft={
            "name":"杭州三日游",
            "adults":2,
            "prices": {"adult": {"meal_price": "300.00", "boat_price": None}},
        }
    plan_id=plan_store.create_plan("user_a","杭州三日游",draft=mock_draft,conversation_id=conversation_id)
    store.delete_conversation(conversation_id)

    plan=plan_store.get_plan(plan_id)

    assert plan is not None 
    assert plan["conversation_id"] is None

#版本号没变
def test_save_plan_version_increments():
    a_draft={
                "name":"杭州三日游",
                "adults":3,
                "prices": {"adult": {"meal_price": "300.00", "boat_price": None}},
            }
    b_draft={
                "name":"杭州三日游",
                "adults":5,
                "prices": {"adult": {"meal_price": "300.00", "boat_price": None}},
            }
    plan_id=plan_store.create_plan("user_a","杭州三日游",draft=a_draft,conversation_id=None)
    new_version=plan_store.save_plan_version(plan_id,b_draft,1,"user_b")

    assert new_version == 2

    plan = plan_store.get_plan(plan_id)
    assert plan["current_version"] == 2
    assert plan["draft"] == b_draft      # 拿到的是新内容，不是 a_draft
    assert plan["status"] == "draft"     # 新版本默认是 draft

#版本号变更
def test_save_with_stale_version_rejected():
    a_draft={
                "name":"杭州三日游",
                "adults":3,
                "prices": {"adult": {"meal_price": "300.00", "boat_price": None}},
            }
    b_draft={
                "name":"杭州三日游",
                "adults":5,
                "prices": {"adult": {"meal_price": "300.00", "boat_price": None}},
            }
    plan_id=plan_store.create_plan("user_a","杭州三日游",draft=a_draft,conversation_id=None)

    assert plan_store.save_plan_version(plan_id, b_draft, 1, "user_b") == 2      # B 先保存，成功
    assert plan_store.save_plan_version(plan_id, a_draft, 1, "user_a") is None   # A 后保存，被拒绝

    plan = plan_store.get_plan(plan_id)
    assert plan["draft"] == b_draft           # 还是 B 的内容，A 的没有写进去
    assert plan["current_version"] == 2       # 版本号没有因为 A 再变成 3


# 价格和住宿都已填写时，pending 可以确认为 confirmed
def test_confirm_with_full_prices():
    # 准备：用 empty_draft() 生成完整结构
    draft = empty_draft()
    for key in draft["prices"]["adult"]:
        draft["prices"]["adult"][key] = "100.00"
    draft["lodging_mode"] = "none"      # 不安排住宿，就不需要房型

    plan_id = plan_store.create_plan("user_a", "杭州三日游", draft)
    plan_store.change_plan_status(plan_id, 1, "pending")    # 准备步骤，不断言

    # 执行：这次调用才是要验证的
    result = plan_store.change_plan_status(plan_id, 1, "confirmed")

    # 断言：返回值正确，数据库里也确实改了
    assert result == {"ok": True, "status": "confirmed"}
    assert plan_store.get_plan(plan_id)["status"] == "confirmed"


#draft → pending → draft 两种合法转换
def test_submit_and_return_to_draft():
    draft=empty_draft()
    plan_id=plan_store.create_plan("user_a","杭州三日游",draft)
    a_result=plan_store.change_plan_status(plan_id,1,"pending")
    assert a_result=={"ok":True,"status":"pending"}
    assert plan_store.get_plan(plan_id)["status"]=="pending"

    b_result=plan_store.change_plan_status(plan_id,1,"draft")
    assert b_result=={"ok":True,"status":"draft"}
    assert plan_store.get_plan(plan_id)["status"]=="draft"

#不合法的转换被拒绝
def test_draft_cannot_skip_to_confirmed():
    draft=empty_draft()
    plan_id=plan_store.create_plan("user_a","杭州三日游",draft)
    result=plan_store.change_plan_status(plan_id,1,"confirmed")

    assert result["error"]=="invalid_transition"
    assert plan_store.get_plan(plan_id)["status"]=="draft"

#不合法价格
def test_confirm_requires_prices():
    draft=empty_draft()
    draft["lodging_mode"] = "none"
    plan_id=plan_store.create_plan("user_a","杭州三日游",draft)
    plan_store.change_plan_status(plan_id, 1, "pending")
    result=plan_store.change_plan_status(plan_id,1,"confirmed")
    

    assert result["error"]=="missing_prices"
    assert result["missing"]
    assert plan_store.get_plan(plan_id)["status"]=="pending"


def  test_status_change_with_stale_version():
    draft=empty_draft()
    plan_id=plan_store.create_plan("user_a","杭州三日游",draft)
    base_version=plan_store.get_plan(plan_id)["current_version"]
    plan_store.save_plan_version(plan_id,draft,base_version,"user_a")
    result=plan_store.change_plan_status(plan_id,1,"pending")

    assert result["error"]=="version_conflict"
    assert plan_store.get_plan(plan_id)["status"]=="draft"


#用户隔离
def test_list_plans_only_own():
    draft=empty_draft()
    a_plan_id=plan_store.create_plan("user_a","杭州三日游",draft)
    a_plan_id_2=plan_store.create_plan("user_a","杭州一日游",draft)
    b_plan_id=plan_store.create_plan("user_b","西湖游",draft)

    a_results=plan_store.list_plans("user_a")

    assert len(a_results)==2
    assert a_results[0]["id"]==a_plan_id_2
    ids=[p["id"]  for p in a_results]
    assert b_plan_id not in ids


def test_delete_plan_removes_versions():
    draft=empty_draft()
    plan_id=plan_store.create_plan("user_a","杭州三日游",draft)
    plan=plan_store.get_plan(plan_id)
    plan_store.save_plan_version(plan_id,draft,plan["current_version"],"user_a")
    deleted=plan_store.delete_plan(plan_id)

    assert deleted is True
    now_plan=plan_store.get_plan(plan_id)
    assert now_plan is None
    conn = store.get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM plan_versions WHERE plan_id=?", (plan_id,)
    ).fetchone()[0]
    conn.close()
    assert count == 0


def test_copy_plan():
    draft=empty_draft()
    plan_a_id=plan_store.create_plan("user_a","杭州三日游",draft)
    edited = empty_draft()
    edited["adults"]=5
    plan_store.save_plan_version(plan_a_id, edited, 1, "user_a")   # 原方案变成第 2 版
    plan_b_id=plan_store.copy_plan(plan_a_id,"user_b")

    assert plan_a_id!=plan_b_id
    plan_a=plan_store.get_plan(plan_a_id)
    plan_b=plan_store.get_plan(plan_b_id)
    assert plan_a["draft"]==plan_b["draft"]
    assert plan_b["current_version"]==1
    assert plan_b["status"]=="draft"
    assert "副本"  in plan_b["title"]
    assert plan_b["owner_id"] == "user_b"
    assert plan_b["draft"]["adults"] == 5



#保存时传标题就更新，不传就保留原标题
def test_save_plan_version_updates_title():
    plan_id=plan_store.create_plan("user_a","杭州三日游",empty_draft())

    plan_store.save_plan_version(plan_id,empty_draft(),1,"user_a")
    assert plan_store.get_plan(plan_id)["title"]=="杭州三日游"

    plan_store.save_plan_version(plan_id,empty_draft(),2,"user_a",title="杭州四日游")
    assert plan_store.get_plan(plan_id)["title"]=="杭州四日游"



def test_list_confirmed_plans_keeps_last_confirmed_version():
    draft = empty_draft()
    draft["lodging_mode"] = "none"
    for key in draft["prices"]["adult"]:
        draft["prices"]["adult"][key] = 10
    plan_id = plan_store.create_plan("user_a", "杭州两日游", draft)
    plan_store.change_plan_status(plan_id, 1, "pending")
    assert plan_store.change_plan_status(plan_id, 1, "confirmed")["ok"]
    plan_store.save_plan_version(plan_id, {"adults": 3}, 1, "user_a")

    plans = plan_store.list_confirmed_plans()

    assert [(plan["id"], plan["current_version"]) for plan in plans] == [(plan_id, 1)]
    assert plans[0]["draft"] == draft