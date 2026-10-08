import sqlite3
from pathlib import Path



 
DB_PATH=(
    Path(__file__).resolve().parent.parent
    /"data"
    /"conversation.db"
)

def get_connection():
    DB_PATH.parent.mkdir(parents=True,exist_ok=True)

    conn=sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")

    return conn

def init_db():
    conn=get_connection()

    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS conversations(
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"""
        )

        conn.execute("""
    CREATE TABLE IF NOT EXISTS messages(
    id INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (conversation_id)
    REFERENCES conversations(id)
    ON DELETE CASCADE)
    """)
        conn.commit()
    finally:
        conn.close()

def creat_conversation(title,owner_id):
    conn=get_connection()

    try:
        cursor=conn.execute(
            """INSERT INTO conversations (title,owner_id)VALUES (?,?)
            """,(title,owner_id)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def get_conversation(conversation_id):
    conn=get_connection()

    try:
        row=conn.execute(
            """SELECT id,title,owner_id FROM conversations WHERE id=?""",
            (conversation_id,)
        ).fetchone()
        if row is None:
            return None
        return {"id":row[0],"title":row[1],"owner_id":row[2]}
    finally:
        conn.close()

def get_messages(conversation_id,):
    conn=get_connection()
    messages=[]
    try:
        rows=conn.execute(
            """SELECT role,content FROM messages WHERE conversation_id=? ORDER BY created_at ASC,id ASC""",(conversation_id,)
    ).fetchall()
        for row in rows:
            messages.append({"role":row[0],"content":row[1]})
        return messages
    finally:
        conn.close()

def save_turn(conversation_id,user_content,assistant_content):
    conn=get_connection()

    try:
        conn.execute(
            """INSERT INTO messages(conversation_id,role,content) VALUES (?,?,?)""",(conversation_id,"user",user_content)
        )
        conn.execute(
            """INSERT INTO messages(conversation_id,role,content) VALUES (?,?,?)""",(conversation_id,"assistant",assistant_content)
        )
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()

def create_conversation_with_turn(
    title,
    owner_id,
    user_content,
    assistant_content
):
    conn=get_connection()
    try:
        conversation_id=conn.execute(
        """ INSERT INTO conversations(title,owner_id) VALUES(?,?)""",(title,owner_id)
    ).lastrowid
        conn.execute(
        """INSERT INTO messages(conversation_id,role,content) VALUES (?,?,?)""",
        (conversation_id,"user",user_content)
    )
        conn.execute(
        """INSERT INTO messages(conversation_id,role,content) VALUES(?,?,?)""",
        (conversation_id,"assistant",assistant_content)
    )
        conn.commit()
        return conversation_id
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()

def delete_conversation(conversation_id):
    conn=get_connection()

    try:
        cursor=conn.execute(
            "DELETE FROM conversations WHERE id=?",
            (conversation_id,)
        )
        conn.commit()
        return cursor.rowcount==1

    except sqlite3.Error:
        conn.rollback()
        raise

    finally:
        conn.close()

if __name__=="__main__":
    init_db()
    init_db()
    conn=get_connection()
    print("数据库文件：",DB_PATH)
    print("外键状态：",conn.execute("PRAGMA foreign_keys").fetchone())
    conn.close()


    conn=get_connection()
    print("数据库文件：",DB_PATH)
    print("外键状态：",conn.execute("PRAGMA foreign_keys").fetchone())
    cursor_1=conn.execute("SELECT COUNT(*) FROM conversations").fetchone()
    cursor_2=conn.execute("SELECT COUNT(*) FROM messages").fetchone()
    print(cursor_1)
    print(cursor_2)
    conn.close()
    

    conversation_id=creat_conversation("杭州两日游","user_a")
    print(get_conversation(9999))
    print(get_conversation(conversation_id))


    print(get_messages(conversation_id))


    save_turn(
    conversation_id,
    "杭州玩两天",
    "可以安排西湖和灵隐寺"
    )
    print(get_messages(conversation_id))


    rollback_id=creat_conversation("测试回滚","user_a")
    try:
        save_turn(rollback_id,
        "这条用户消息不能单独留下",
        None)
    except sqlite3.Error as error:
        print(type(error).__name__)
    print(get_messages(rollback_id))


    new_id=create_conversation_with_turn(
        "杭州周末游",
        "user_a",
        "周末我想去杭州",
        "可以安排西湖和灵隐寺"
    )
    print(get_conversation(new_id))
    print(get_messages(new_id))


    conn = get_connection()
    before_count = conn.execute(
        "SELECT COUNT(*) FROM conversations"
    ).fetchone()[0]
    conn.close()

    try:
        create_conversation_with_turn(
            "新会话整体回滚测试",
            "user_a",
            "这条消息不能留下",
            None
        )
    except sqlite3.Error as error:
        print(type(error).__name__)

    conn = get_connection()
    after_count = conn.execute(
        "SELECT COUNT(*) FROM conversations"
    ).fetchone()[0]
    conn.close()

    print(before_count, after_count)