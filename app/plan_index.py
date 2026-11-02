from app.draft_generator import draft_to_context
from app.vector_store import (delete_document_chunks,
replace_document_chunks,
get_vector_collection)


PLAN_COLLECTION="confirmed_plans"

def get_plan_collection():
    return get_vector_collection(PLAN_COLLECTION)

def plan_document_id(plan_id):
    return f"plan-{plan_id}"

#整条方案转化为切片
def plan_to_chunk(plan):
    lines=draft_to_context(plan["draft"]).split("\n")[1:] #去掉列表第一项，遇到换行就切开
    return{
        "chunk_id":f"plan-{plan['id']}-v{plan['current_version']}",
        "content":"\n".join([f"已确认方案：{plan['title']}"]+lines),
        "plan_id":plan["id"],     #标题加正文内容全部
        "version":plan["current_version"],
        "owner_id":plan["owner_id"],
        "source_id":f"PLAN{plan['id']}",
        "source_title":plan["title"],
        "document_id":plan_document_id(plan["id"])
    }


#新版会替换旧版本
def index_confirmed_plan(plan,model,collection):
    return replace_document_chunks(
        plan_document_id(plan["id"]),
        [plan_to_chunk(plan)],
        model,
        collection,
    )



def remove_plan_chunks(plan_id,collection):
    return delete_document_chunks(plan_document_id(plan_id),collection)



#查数据库中的id，补写进入向量库
def rebuild_plan_index(plans,model,collection):
    wanted={plan_to_chunk(plan)["chunk_id"]:plan for plan in plans}
    existing=set(collection.get()["ids"])

    written=0
    for chunk_id,plan in wanted.items():
        if chunk_id not in existing:   #已是最新版就跳过，不重复计算向量
            index_confirmed_plan(plan,model,collection)
            written+=1

    stale=sorted(set(collection.get()["ids"])-set(wanted))
    if stale:
        collection.delete(ids=stale)
    return {"indexed":written,"deleted":len(stale)}


if __name__=="__main__":
    from app.plan_store import list_confirmed_plans
    from app.rag_resources import get_rag_resources
    #运行可以添加补写
    result=rebuild_plan_index(
        list_confirmed_plans(),
        get_rag_resources()["model"],
        get_plan_collection(),
    )
    print("已写入",result["indexed"],"条方案，删除",result["deleted"],"个过期切片")


