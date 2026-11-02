import sqlite3


conn=sqlite3.connect("week6_chat_2_demo.db")
conn.execute("PRAGMA foreign_keys=ON")

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

try:
    cursor=conn.execute(
    "INSERT INTO conversations (title,owner_id) VALUES (?,?)",("杭州两日游","user_test")
)

    conversation_id_1=cursor.lastrowid

    message_cursor=conn.execute(
    "INSERT INTO messages (conversation_id,role,content) VALUES (?,?,?)",(conversation_id_1,"user","事务成功测试")
)
except sqlite3.IntegrityError as error:
    print(error)
    conn.rollback()
else:
    conn.commit()
    print("事务提交成功")


parent_after_transaction = conn.execute(
    "SELECT id FROM conversations WHERE id = ?",
    (conversation_id_1,)
).fetchone()

print("事务处理后的新会话：", parent_after_transaction)
conn.close()

conn=sqlite3.connect("week6_chat_2_demo.db")
conn.execute("PRAGMA foreign_keys=ON")
saved_conversation = conn.execute(
    "SELECT id FROM conversations WHERE id = ?",
    (conversation_id_1,)
).fetchone()

print("持久化对话：", saved_conversation)

saved_messages = conn.execute(
    "SELECT id, role, content FROM messages WHERE conversation_id = ?",
    (conversation_id_1,)
).fetchall()

print("持久化消息：", saved_messages)

conn.close()
