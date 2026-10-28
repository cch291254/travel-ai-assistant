import re

#构建上下文，清洗拿到的排序
def build_context(evidence,start_nimber=1):
    parts=[]
    source_map={}

    for number,item in enumerate(evidence,start=start_nimber):
        citation_id=str(number)
        metadata=item["metadata"]

        block=(
            f"[{citation_id}]\n"
            f"引用编号：{citation_id}\n"
            f"来源标识（非引用编号）：{metadata.get('source_id', '未提供')}\n"
            f"资料标题：{metadata.get('source_title', '未提供')}\n"
            f"资料类型：{metadata.get('content_type', '内部资料正文')}\n"
            f"网页链接：{metadata.get('url', '无')}\n"
            f"章节：{metadata.get('section_path', '未提供')}\n"
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


def extract_citation_ids(answer):
    citation_ids = []

    for citation_id in re.findall(r"\[([1-9][0-9]*)\]", answer):
        if citation_id not in citation_ids:
            citation_ids.append(citation_id)

    return citation_ids


def build_web_evidence(tool_name,data):
    if tool_name=="web_search":
        pages=data["results"]
        text_key="summary"   #搜索结果中的摘要字段
        content_type="搜索摘要"
    else:
        pages=[data]
        text_key="content"     #抓取结果中的正文字段
        content_type="网页正文"

    evidence=[]

    for page in pages:
        if not isinstance(page,dict):
            continue

        url=page.get("url")
        content=page.get(text_key)

        if not isinstance(url,str) or not url.strip():
            continue
        if not isinstance(content,str) or not content.strip():
            continue

        title=page.get("title")
        if not isinstance(title,str) or not title.strip():
            title=url

        evidence.append({   #给证据增加网络来源
            "chunk_id": f"{tool_name}:{url}",
            "content": content,
            "metadata": {
                "source_type": "web",
                "source_title": title,
                "url": url,
                "content_type": content_type,
        }
        })

    return evidence
