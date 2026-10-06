import sqlite3

conn=sqlite3.connect("week6_chat_demo.db")
conn.execute("PRAGMA foreign_keys=ON")

conn.execute("""
    CREATE TABLE IF NOT EXISTS conversations(
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)

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

cursor=conn.execute(
    "INSERT INTO conversations (title,owner_id) VALUES (?,?)",("杭州两日游","user_a")
)
cursor_2=conn.execute(
    "INSERT INTO conversations (title,owner_id) VALUES (?,?)",("上海周末游","user_b"))

conversation_id_2=cursor_2.lastrowid
conversation_id_1=cursor.lastrowid

message_cursor=conn.execute(
    "INSERT INTO messages (conversation_id,role,content) values (?,?,?)",(conversation_id_1,"user","推荐一个杭州景点")
)

message_cursor_1=conn.execute(
    "INSERT INTO messages (conversation_id,role,content) VALUES(?,?,?)",(conversation_id_1,"assistant","可以考虑西湖")
)

message_cursor_2=conn.execute(
    "INSERT INTO messages (conversation_id,role,content) VALUES (?,?,?)",(conversation_id_2,"user","推荐一个上海景点")
)

message_cursor_3=conn.execute(
    "INSERT INTO messages (conversation_id,role,content) VALUES (?,?,?)",(conversation_id_2,"assistant","可以考虑外滩")
)

print("新增消息编号：", message_cursor.lastrowid)
print("第一个id编号为：",conversation_id_1)
print("第二个id编号为：",conversation_id_2)
conn.commit()
print("会话表创建成功")
print("消息表创建成功")
print("外键状态：",conn.execute("PRAGMA foreign_keys").fetchone())


row_1=conn.execute(
    "SELECT id,role,content FROM messages WHERE conversation_id=?",(conversation_id_1,)
).fetchall()

print("第一个会话的消息：")
for row in row_1:
    print(row)

row_2=conn.execute(
    "SELECT id,role,content FROM messages WHERE conversation_id=?",(conversation_id_2,)
).fetchall()

print("第二个会话消息")
for row in row_2:
    print(row)
conn.close()
