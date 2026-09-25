import sqlite3
from pathlib import Path
def init_db(db_path):
        file_path=Path(db_path)
        conn=sqlite3.connect(file_path)
        conn.execute("""CREATE TABLE IF NOT EXISTS documents(
id INTEGER PRIMARY KEY,
filename TEXT NOT NULL,
source TEXT NOT NULL,
file_hash TEXT UNIQUE,
updated_at TEXT,
status TEXT NOT NULL,
error_message TEXT)""")
        conn.commit()
        return conn

def register_document(conn,filename,sourse,file_hash,updated_at,status,error_message=None):

        try:
                conn.execute("""INSERT INTO documents
                (filename,source,file_hash,updated_at,status,error_message)
        VALUES(?,?,?,?,?,?)""",(
        filename,
         sourse,
        file_hash,
        updated_at,
        status,
        error_message,
        ),)
                conn.commit()
                return True
        except sqlite3.IntegrityError:
                conn.rollback()
                print("重复文件，已跳过")
                return False
def get_document_status(conn):
        rows=conn.execute("""select status,count(*) from documents group by status""").fetchall()
        return dict(rows)
if __name__ == "__main__":
        conn = init_db("data/documents.db")
        register_document(conn,"hangzhou_guide.pdf","data/raw/hangzhou_guide.pdf","abc123","2026-09-23T17:05:25","success",)
        result=conn.execute("SELECT*FROM documents").fetchone()
        print(result)
        stats=get_document_status(conn)
        print(stats)
        conn.close()