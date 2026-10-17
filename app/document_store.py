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
        conn.execute("""
CREATE TABLE IF NOT EXISTS document_indexes (
    collection_name TEXT NOT NULL,
    document_id TEXT NOT NULL,
    source TEXT NOT NULL,
    file_hash TEXT NOT NULL,                              
    PRIMARY KEY (collection_name, document_id)
)
""")
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

def save_document_index(
                conn,collection_name,document_id,source,file_hash
):
        try:
                conn.execute(
                        """INSERT INTO document_indexes(
                        collection_name,document_id,source,file_hash
                )
                VALUES (?,?,?,?)
                ON CONFLICT(collection_name,document_id)
                DO UPDATE SET
                        source=excluded.source,
                        file_hash=excluded.file_hash
                        """,
                (collection_name,document_id,source,file_hash))
                conn.commit()

        except sqlite3.Error:
                conn.rollback()
                raise
                
def delete_document_index(conn,collection_name,document_id):
        try:
                cursor=conn.execute(
                        """DELETE FROM document_indexes
                        WHERE collection_name=? AND document_id=?""",(collection_name,document_id)
                )
                conn.commit()

                return cursor.rowcount
        except sqlite3.Error:
                conn.rollback()
                raise

if __name__ == "__main__":
        conn = init_db("data/documents.db")
        register_document(conn,"hangzhou_guide.pdf","data/raw/hangzhou_routes.md","abc123","2026-09-23T17:05:25","success",)
        result=conn.execute("SELECT*FROM documents").fetchone()
        print(result)
        stats=get_document_status(conn)
        print(stats)
        conn.close()