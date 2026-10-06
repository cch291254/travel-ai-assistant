import sqlite3

conn = sqlite3.connect("week6_chat_demo.db")

query_sql = """
    SELECT id, role, content
    FROM messages
    WHERE conversation_id = ?
    ORDER BY created_at, id
"""

plans = conn.execute(
    "EXPLAIN QUERY PLAN " + query_sql,
    (16,)
).fetchall()

for plan in plans:
    print(plan)

conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_messages_conversation_time
    ON messages (conversation_id, created_at,id)
""")

conn.commit()

plans = conn.execute(
    "EXPLAIN QUERY PLAN " + query_sql,
    (16,)
).fetchall()

for plan in plans:
    print(plan)
conn.close()


conn=sqlite3.connect("week6_chat_demo.db")
conn.execute("PRAGMA foreign_Keys=ON")

owner_id = "user_a"
joined_rows=conn.execute(
    """
    SELECT c.id,c.title,m.role,c.owner_id,m.content,m.id,m.created_at
    FROM messages AS m
    JOIN conversations AS c ON m.conversation_id=c.id
    WHERE c.owner_id=?
    ORDER BY c.id ASC,m.created_at ASC,m.id ASC
    """,(owner_id,)
).fetchall()

print(joined_rows)
conn.close()
