import argparse
from pathlib import Path
import chromadb

from app.document_store import init_db
from app.document_indexer import (
    index_document_with_registration,   
    delete_document_with_registration,
)


def main():
    parser = argparse.ArgumentParser(   #创建一个参数解析器
        description="管理单份文档的向量索引"
    )
    parser.add_argument(
        "action",   #动作
        choices=["index", "delete"],
        help="index：新增或更新；delete：删除索引",
    )
    parser.add_argument(   #登记一个位置参数
        "target",
        help="index 时传文件路径；delete 时传 document_id",  #运行 --help 时显示
    )
    parser.add_argument(
        "--collection",
        required=True,  #必须带上这个选项
        help="要操作的向量集合名",
    )

    args = parser.parse_args()  #这一行才真正读取、检查命令行参数。

    if not Path("data/chroma").is_dir():
        parser.error("找不到向量库目录，请在项目根目录运行")

    if args.action == "index":
        if not Path(args.target).is_file():
            parser.error("目标文件不存在，或者不是文件")

    if args.action=="delete":
        confirmation = input(
            f"将删除集合 {args.collection} 中"
            f"文档 {args.target} 的索引，不删除原文件。"
            "输入 DELETE 确认："
        )

        if confirmation != "DELETE":
            print("已取消删除")
            return


    client = chromadb.PersistentClient(path="data/chroma")  #连接向量库
    collection = client.get_collection(name=args.collection)   

    conn = init_db("data/real_documents.db")
    try:
        if args.action == "index":    
            from app.embedding import load_embedding_model

            model = load_embedding_model()
            result = index_document_with_registration(
                args.target, model, collection, conn
            )
        else:
            result = delete_document_with_registration(
                args.target, collection, conn
            )

        print(result)
    finally:
        conn.close()

if __name__ == "__main__":
    main()