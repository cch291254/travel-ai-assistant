

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
    chunks=[]
    #阻止标题切片
    for record in records:
        if record.get("heading_level")is not None:
            continue

        #阻止提示进行切片
        content=record["content"].strip()
        if "\n" not in content and content.startswith(("来源编号:","来源编号：")):
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