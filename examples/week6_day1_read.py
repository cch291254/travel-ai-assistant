import sqlite3

conn=sqlite3.connect("week6_chat_demo.db")
conn.execute("PRAGMA foreign_Keys=ON")

conversation_id=16
other_id=15

rows=conn.execute(
    "SELECT id,role,content FROM messages WHERE conversation_id=?",(conversation_id,)
).fetchall()

print("读取已有对话：",conversation_id)
for row in rows:
    print(row)

test_id=16

parent=conn.execute(
    "SELECT id FROM conversations WHERE id=?",(test_id,)
).fetchone()

print("对应会话：",parent)

try:
    conn.execute(
        "INSERT INTO messages(conversation_id, role,content) VALUES (?,?,?)",(test_id,"user","外键测试消息")
    )
except sqlite3.IntegrityError as error:
    print("写入被拒绝：",error)
else:
    print("写入被允许")
finally:
    conn.rollback()
rows=conn.execute(
    "SELECT id,role,content FROM messages WHERE conversation_id=?",(conversation_id,)
).fetchall()
print("回滚后的消息：",rows)

try:
    rows_1=conn.execute(
    "SELECT id,role,content FROM messages WHERE conversation_id=?",(other_id,)
).fetchall()
    print("其他消息：",rows_1)

    delete_cursor=conn.execute(
        "DELETE FROM conversations WHERE id =?",(conversation_id,)
    )
    print("删除会话条数：",delete_cursor.rowcount)

    rows=conn.execute(
    "SELECT id,role,content FROM messages WHERE conversation_id=?",(conversation_id,)
).fetchall()
    print("删除后的消息：",rows)

    parent_after_delete=conn.execute(
        "SELECT id FROM conversations WHERE id=?",(conversation_id,)
    ).fetchone()
    print("删除后的会话记录：",parent_after_delete)

    rows_1=conn.execute(
    "SELECT id,role,content FROM messages WHERE conversation_id=?",(other_id,)
).fetchall()
    print("其他消息：",rows_1)

finally:
    conn.rollback()

rows=conn.execute(
    "SELECT id,role,content FROM messages WHERE conversation_id=?",(conversation_id,)
).fetchall()
print("回滚后的消息：",rows)


query_id=15
joined_rows=conn.execute(
    """
    SELECT m.id,c.title,m.role,m.content,c.owner_id,m.created_at
    FROM messages AS m
    JOIN conversations AS c ON m.conversation_id=c.id
    WHERE m.conversation_id=?
    ORDER BY m.created_at ASC,m.id ASC
    """,(query_id,)
).fetchall()

print("关联查询结果：")
for row in joined_rows:
    print(row)


try:
    conn.execute(
        "UPDATE messages SET created_at=? WHERE id=?",("2026-10-06 09:00:00",18)
    )
    conn.execute(
        "UPDATE messages SET created_at=? WHERE id=?",("2026-10-06 08:00:00",19)
    )

    joined_rows=conn.execute(
    """
    SELECT m.id,c.title,m.role,m.content,c.owner_id,m.created_at
    FROM messages AS m
    JOIN conversations AS c ON m.conversation_id=c.id
    WHERE m.conversation_id=?
    ORDER BY m.created_at ASC,m.id ASC
    """,(query_id,)
    ).fetchall()
    print("关联查询结果：")
    for row in joined_rows:
        print(row)

finally:
    conn.rollback()

conn.close()
