#构建上下文，清洗拿到的排序
def build_context(evidence):
    parts=[]
    source_map={}

    for number,item in enumerate(evidence,start=1):
        citation_id=str(number)
        metadata=item["metadata"]

        block=(
            f"[{citation_id}]\n"
            f"来源编号：{metadata.get('source_id', '未提供')}\n"
            f"资料标题：{metadata.get('source_title', '未提供')}\n"
            f"章节：{metadata.get('section_path', '未提供')}\n"
            f"文档类型：{metadata.get('document_type', '未提供')}\n"
            f"生效日期：{metadata.get('valid_from', '未提供')}\n"
            f"有效期至：{metadata.get('valid_until', '未提供')}\n"
            f"正文：{item['content']}"
        )

        parts.append(block)

        source_map[citation_id]={
            "chunk_id":item["chunk_id"],
            "metadata":metadata,
        }

    return {
            "context":"\n\n".join(parts),
            "source_map":source_map
        }
