import json
import sqlite3
from app.conversation_store import get_connection
from app.workspace_plan import find_missing_prices

#当前的线路状态
ALLOWED_TRANSITIONS={
    "draft":{"pending"},  #提交状态
    "pending":{"confirmed","draft"},   #确认问题
    "confirmed":set(),  #确认版本
}


def _insert_version(conn, plan_id, version, draft, created_by):
    draft_json=json.dumps(draft,ensure_ascii=False)#防止变化
    conn.execute("""
    INSERT INTO plan_versions(plan_id,version,draft_json,created_by)
    VALUES (?,?,?,?)""",
    (plan_id,version,draft_json,created_by))

def create_plan(owner_id,title,draft,conversation_id=None):
    conn=get_connection()

    try:
        cursor=conn.execute("""
        INSERT INTO plans(owner_id,conversation_id,title,current_version)
        VALUES(?,?,?,?)""",
        (owner_id,conversation_id,title,1))
        plan_id=cursor.lastrowid
        _insert_version(conn, plan_id, 1, draft, owner_id)

        conn.commit()
        return plan_id
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


# 返回当前版本：id, owner_id, conversation_id, title,
# current_version, status, draft(dict), updated_at；不存在返回 None
def get_plan(plan_id):
    conn=get_connection()

    try:
        row=conn.execute("""
        SELECT p.id,p.owner_id,p.conversation_id,p.title,p.current_version,v.status,v.draft_json,p.updated_at
        FROM plans p
        JOIN plan_versions v ON p.id=v.plan_id
        AND v.version=p.current_version
        WHERE p.id=?""",(plan_id,)).fetchone()

        if row is None:
            return None
        return {"id":row[0],"owner_id":row[1],"conversation_id":row[2],"title":row[3],"current_version":row[4],"status":row[5],"draft":json.loads(row[6]),"updated_at":row[7]}

    finally:
        conn.close()

#进行版本更改
def save_plan_version(plan_id,draft,base_version,created_by):
    conn=get_connection()

    try:   #这里使用乐观锁，防止多人更改
        new_version=base_version+1
        cursor=conn.execute("""
        UPDATE plans 
        set current_version=?,updated_at=CURRENT_TIMESTAMP
        WHERE id=? AND current_version=?""",(new_version,plan_id,base_version))

        if cursor.rowcount==0:
            conn.rollback()
            return None
        _insert_version(conn, plan_id,new_version, draft, created_by)

        conn.commit()   
        return new_version

    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()

#更换版本状态
def change_plan_status(plan_id,base_version,new_status):
    conn=get_connection()
    try:
        row=conn.execute("""
                SELECT v.status,v.draft_json
                FROM plans p
                JOIN plan_versions v ON p.id=v.plan_id
                AND v.version=p.current_version
                WHERE p.id=? AND p.current_version=?""",(plan_id,base_version)).fetchone()

        if row is None:
            return {"ok":False,"error":"version_conflict"}#版本号冲突

        current_status=row[0]
        #判断状态
        if new_status not in ALLOWED_TRANSITIONS[current_status]:
            return {"ok":False,"error":"invalid_transition"}
        # 确认前检查价格是否填完
        if new_status=="confirmed":
            draft=json.loads(row[1])
            missing=find_missing_prices(draft)
            if missing:
                return {"ok":False,"error":"missing_prices","missing":missing}

        cursor=conn.execute("""
                UPDATE plan_versions   
                SET status=? WHERE plan_id=?
                AND version=? AND status=?""",(new_status,plan_id,base_version,current_status))
        if cursor.rowcount==0:              #乐观锁是版本号和旧状态
            conn.rollback()
            return {"ok":False,"error":"version_conflict"}
        conn.commit()
        return {"ok": True, "status": new_status}
        
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()
        
        