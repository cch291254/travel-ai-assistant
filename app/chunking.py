#整理最小切片
def same_merge_scope(left,right):  #比较前后两条记录
    #以下信息需要一致
    required_keys=("document_id","source_id","section_path")

    for key in required_keys:
        if not left.get(key) or left.get(key) !=right.get(key):
            return False

    #文件路径、有效期和页码也不能冲突
    optional_keys=("source","valid_from","valid_until","page_number")

    for key in optional_keys:
        if left.get(key)!=right.get(key):
            return False

    return True


#标题，独立条目不可随便合并
def is_merge_boundary(record):
    #标题出现时，停止合并
    if record.get("heading_level") is not None:
        return True

    content=record["content"].strip()

    if not content:
        return True

    #部分边界不合并
    if "\n" not  in content and content.startswith(
        ("来源编号:", "来源编号：", "首次整理日期")
    ):
        return True

    return False

#组合合并规则
def merge_two_records(left,right):
    merged=left.copy() #保留原数据

    #分割两片数据
    merged["content"]=(
        left["content"].rstrip()
        +"\n\n"
        +right["content"].lstrip()
    )

    return merged


#往后合并
def merge_short_records(
        records,
        short_threshold=50,
        target_size=200,
        max_size=400,
):
    if not 0 < short_threshold <= target_size <= max_size:
        raise ValueError("需满足：0 < 短段阈值 <= 目标长度 <= 合并上限")


    result=[]
    pending=None #待合并记录

    for record in records:
        #遇到问题，先结束上一组
        if is_merge_boundary(record):
            if pending is not None:
                result.append(pending)
                pending=None

            result.append(record.copy())
            continue

            #pending为上一条
        if pending is not None:
            if same_merge_scope(pending,record):
                merge_piece=merge_two_records(pending,record)

                if len(merge_piece["content"])<=max_size:
                    pending=merge_piece

                    #达到长度，停止
                    if len(pending["content"])>=target_size:
                        result.append(pending)
                        pending=None

                    continue

            result.append(pending) #当达到后，保存为新的一片
            pending=None

        #
        if len(record["content"])<short_threshold:
            pending=record.copy()  #更新新的一片小于50的
        else:
            result.append(record.copy())  #超过50的单独加进去

#防止最后一片没有并入
    if pending is not None:
        result.append(pending)

    return result

#文本切割
def split_text(text,chunk_size=500,overlap=80):
    chunk_text=[]

    if chunk_size<=0:
        raise ValueError("切片长度需大于0")
    if overlap<0 or overlap>=chunk_size:
        raise ValueError("重叠长度需大于等于0,且小于切片长度")
    if text.strip()=="":
        return []
    if len(text)<=chunk_size:
        return [text]

    start=0
    step=chunk_size-overlap
    while start<len(text):
        end=start+chunk_size

        piece=text[start:end]
        chunk_text.append(piece)

        if end>=len(text):
            break

        start+=step

    return  chunk_text

#检查切片，初步清洗
def split_record(record,chunk_size=200,overlap=80):
    pieces=split_text(record["content"],chunk_size,overlap)
    chunks=[]

    paragraph_index=record.get("paragraph_index")
    page_number=record.get("page_number")
    if page_number is not None and paragraph_index is not None:
        position = f"page-{page_number}:paragraph-{paragraph_index}"
    elif paragraph_index is not None:
        position=f"paragraph-{paragraph_index}"
    elif page_number is not None:
        position=f"page-{page_number}"
    else:
        position="position-uknown"
    for index,piece in enumerate(pieces,start=1):
        chunk=record.copy()
        chunk["chunk_index"]=index
        chunk["content"]=piece
        chunk["chunk_id"] = (
        f"{record['document_id']}:{position}:chunk-{index}")
        chunks.append(chunk)

    return chunks

def split_records(records,chunk_size=400,overlap=80):
    records = merge_short_records(
    records,
    short_threshold=min(50, chunk_size),
    target_size=min(200, chunk_size),
    max_size=chunk_size,
)
    chunks=[]
    #阻止标题切片
    for record in records:
        if record.get("heading_level")is not None:
            continue

        #阻止提示进行切片
        content=record["content"].strip()
        if "\n" not in content and content.startswith(("来源编号:","来源编号：","首次整理日期")):
            continue

        pieces=split_record(record,chunk_size,overlap)
        chunks.extend(pieces)

    return chunks


if __name__ == "__main__":
    result = split_text(
        "abcdefghijklmnop",
        chunk_size=6,
        overlap=2,
    )
    print(result)


    record = {
    "document_id": "hangzhou_routes",
    "source_id": "S05",
    "source": "data/raw/hangzhou_routes.md",
    "paragraph_index": 3,
    "page_number":2,
    "content": "abcdefghijklmnop",
    }

    result = split_record(record, chunk_size=6, overlap=2)

    print(result)
    print(record)