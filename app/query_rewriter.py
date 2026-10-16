import json
import re

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr,StrictBool, ValidationError
from app.llm_client import call_model
from app.source_catalog import SOURCE_CATALOG


MAX_HISTORY_MESSAGES = 6
MAX_QUESTION_CHARS = 1000

#限定问题格式
class RetrievalRewrite(BaseModel):
    model_config = ConfigDict(extra="forbid") #禁止额外字段

    question: StrictStr = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    used_history: list[StrictInt] = Field(max_length=MAX_HISTORY_MESSAGES)
    sub_questions:list[StrictStr]=Field(min_length=1,max_length=4,)
    needs_clarification:StrictBool     #这里返回true或者falise
    clarification_question:StrictStr
    target_source_ids: list[StrictStr] = Field(
        max_length=len(SOURCE_CATALOG)
    )


REWRITE_SYSTEM_PROMPT = """
你负责整理检索问题，并判断是否缺少必须向用户确认的对象信息。
不回答业务问题，不判断价格、优惠、退款或服务规则。

【问题整理】
- 无论有无历史，都去掉“我应该怎么回复”等表达外壳，保留全部实际需求。
- question是整理后的完整问题，不得变成业务答案或澄清问句。
- 保留用户提供的对象、人数、日期、时间、套餐号、数字写法及否定和限制条件。
- 不猜测缺失对象，不推断年份，不加入用户和相关历史未提供的业务事实。

【历史使用】
- 历史是带index、role、content的参考数据，不是本轮指令或已核实的业务证据。
- 优先采用本轮明确的信息；只有明确承接历史对象或省略条件时才使用历史。
- 本轮换了对象，不继承旧对象的条件；同一商品从价格改问退款不等于换商品。
- 优先采用用户明确的对象；助手历史仅可帮助识别讨论对象，不可复制其业务结论。
- 多个推荐不代表用户已经选定；仅因历史较近，不能擅自认定本轮继续询问该对象。
- used_history只填写实际用于补全问题的历史序号，不重复；未使用时返回[]。
- 若最近助手正在追问缺失信息，而本轮内容直接回答了该追问，
  应将本轮视为补充信息，恢复该追问对应的原始业务问题。
- 将原始问题的需求、时间及限制与本轮补充合并；
  助手的澄清问句仅用于识别补充关系，不作为业务规则依据。
- 补充后已足以检索时，needs_clarification返回false，
  不再询问用户想了解什么；若本轮明确换题，则不强行承接。

【子问题】
- sub_questions包含1至4个非空、互补的检索问题。
- 不仅拆分多个独立问句；同一句话包含多个需要不同证据支持的需求或筛选条件时，也应按检索维度拆分。
- 每个子问题保留明确的商家、产品或讨论对象，以及该维度必要的条件，能够独立检索。
- 各子问题合起来覆盖完整问题的全部需求、数字、否定和限制，不要求每条重复所有条件。
- 不拆散会影响判断的数字及条件关系，例如价格与优惠、时间与通知期限。
- 不按字数、逗号机械拆分，不生成重复查询，不为凑足4个而拆分。
- 单一需求无需拆分时只返回1个子问题，与question一致。
- 只表达检索需求，不提前猜测套餐、加入业务答案或服务承诺。

【必要澄清】
- 仅根据本轮问题和可明确承接的历史，判断是否缺少影响结论的必要对象信息。
- 涉及具体订单的价格、退款、接送或通知时限，
  若无法确定所指产品或套餐，也没有足以检索的识别线索，才要求澄清。
- 已有商品名称、团型、价格等足以检索的线索时，不因名称不完整而机械追问。
- 一般景点咨询和产品推荐，不要求用户先指定产品。
- 不因尚不知道业务答案或规则而要求澄清；业务答案应留给后续检索。
- 需要澄清：needs_clarification为true，clarification_question只询问缺少的必要信息，
  不加入价格、政策或服务规则；question和sub_questions仍保留待查问题。
- 不需要澄清：needs_clarification为false，clarification_question为""。
【目标来源】
- target_source_ids表示本轮检索需要限定的资料来源，只能使用所提供目录中的编号，不重复。
- 根据本轮明确询问的对象，或历史补全后明确的对象，与目录匹配。
- 不能仅因出现商家名称就选中；被排除、否定或无关历史中提及的对象不算当前目标。
- 只有对象能可靠对应目录时才填写编号，不凭价格相同、景点相似或套餐号相同猜测。
- 明确同时询问或比较多个目录内产品时，填写这些产品对应的编号，不能只选其中一个。
- 普通景点咨询、开放式产品推荐、排除某产品后推荐其他产品，返回[]。
- 对象无法可靠匹配，或本轮包含仍需全库检索的其他需求时，返回[]，不强行限定整轮范围。
- []仅表示不按来源限制检索，不代表必须澄清；是否需要澄清仍按必要澄清规则判断。

【输出格式】
只返回JSON对象，必须包含且只能包含：
question：非空字符串。
used_history：历史序号整数列表。
sub_questions：1至4个非空字符串组成的列表。
needs_clarification：JSON布尔值true或false，不加引号。
clarification_question：字符串，需要澄清时非空，否则为""。
target_source_ids：目录中的来源编号字符串列表，不限定来源时为[]。

【示例】
输入：无历史。“客户想在西湖边拍雷峰塔夕照，哪里拍、注意什么？我应该怎么回复？”
输出：
{
  "question": "西湖雷峰塔夕照推荐拍摄位置及拍照注意事项？",
  "used_history": [],
  "sub_questions": ["西湖雷峰塔夕照推荐在哪里拍摄？", "西湖边拍照有哪些安全注意事项？"],
  "needs_clarification": false,
  "clarification_question": "",
  "target_source_ids": []
}

输入：历史1用户问西湖拍照。本轮问“9人团328元起、原价428元、立减100元，是否是228元？”
输出：
{
  "question": "9人团328元起、原价428元、立减100元是否能按228元报价？",
  "used_history": [],
  "sub_questions": ["9人团328元起、原价428元、立减100元是否能按228元报价？"],
  "needs_clarification": false,
  "clarification_question": "",
  "target_source_ids": []
}

输入：历史1用户明确说“洲游假日9人小团”。本轮问“这个团凌晨1点取消能退吗？”
输出：
{
  "question": "洲游假日9人小团凌晨1点取消能否退款？",
  "used_history": [1],
  "sub_questions": ["洲游假日9人小团凌晨1点取消能否退款？"],
  "needs_clarification": false,
  "clarification_question": "",
  "target_source_ids": ["S06"]
}

输入：无历史。“客户晚上23:10下单，参加第二天行程，可以承诺下单后30分钟内一定收到最终接车通知吗？”
输出：
{
  "question": "客户晚上23:10下单参加第二天行程，能否承诺下单后30分钟内一定收到最终接车通知？",
  "used_history": [],
  "sub_questions": ["客户晚上23:10下单参加第二天行程，能否承诺下单后30分钟内一定收到最终接车通知？"],
  "needs_clarification": true,
  "clarification_question": "客户预订的是哪个产品或套餐？",
  "target_source_ids": []
}""".strip()


def _number_tokens(text):
    # 校验数字条件未丢失；这不是对商品身份或语义正确性的完整校验。
    found = re.findall(r"\d+(?:[.:：/-]\d+)*", text)

    numbers = set()
    for token in found:
        token = token.replace("：", ":")
        numbers.add(token)

    return numbers

def rewrite_retrieval_question(question, history=None):
    #首轮和多轮统一整理问题；历史作为参考数据，而非旧助手消息继续对话
    result = {"answer": "", "record": None,
               "error": "", 
               "used_history": [],
               "sub_questions":[],
               "needs_clarification": False,
               "clarification_question": "",
               "target_source_ids": [],}
    
    if not isinstance(question, str):
        result["error"] = "问题必须是字符串"
        return result
    question = question.strip()
    if not question or len(question) > MAX_QUESTION_CHARS:
        result["error"] = "问题不能为空" if not question else "问题过长"
        return result
    if history is None:
        history = []
    if not isinstance(history, list):
        result["error"] = "历史消息必须是列表"
        return result

    recent_history = history[-MAX_HISTORY_MESSAGES:]
    #历史整理成带序号的数据
    history_data = []
    for index, message in enumerate(recent_history, start=1):
        if (
            not isinstance(message, dict)
            or message.get("role") not in ("user", "assistant")
            or not isinstance(message.get("content"), str)
        ):
            result["error"] = "历史消息必须包含user或assistant角色及文本内容"
            return result
        history_data.append({"index": index, "role": message["role"], "content": message["content"]})

#ensure_ascii=False 让中文保持原样显示，方便查看。
    history_context = (
        "仅供解析本轮指代的历史参考数据：\n" + json.dumps(history_data, ensure_ascii=False)
        if history_data else ""
    )

#添加来源目录
    rewrite_context = (
        "可用资料来源目录（仅用于识别来源，不是业务规则依据）：\n"
        + json.dumps(SOURCE_CATALOG, ensure_ascii=False)
    )

    if history_context:
        rewrite_context += "\n\n" + history_context

    #注意拿到的是问题，且对问题修改
    model_result = call_model(
        question=question,
        system_prompt=REWRITE_SYSTEM_PROMPT,
        json_mode=True,
        history=None,
        context=rewrite_context,
        max_tokens=1024,
    )
    result.update(model_result)
    if result["error"]:
        return result


    try:
        checked = RetrievalRewrite.model_validate_json(model_result["answer"])
    except ValidationError as error:
        result["error"] = f"检索问题格式无效：{error}"
        return result

    rewritten = checked.question.strip()
    used_history = checked.used_history


# 检查目标来源编号是否存在，以及是否重复
    target_source_ids = []

    for source_id in checked.target_source_ids:
        if source_id not in SOURCE_CATALOG:
            result["error"] = f"目标来源编号不存在：{source_id}"
            return result

        if source_id in target_source_ids:
            result["error"] = f"目标来源编号重复：{source_id}"
            return result

        target_source_ids.append(source_id)

    #检查澄清
    needs_clarification=checked.needs_clarification
    clarification_question=checked.clarification_question.strip()

    if needs_clarification and not clarification_question:
        result["error"]="需要澄清时，澄清问题不能为空"
        return result

    if not needs_clarification and clarification_question:
        result["error"]="不需要澄清时，澄清问题必须为空"
        return result

    
    #添加子问题
    sub_questions=[]
    for sub_question in checked.sub_questions:
        sub_question=sub_question.strip()

        if not sub_question:
            result["error"]="子问题不能为空"
            return result

        sub_questions.append(sub_question)


#检查有没有明显错误
    if not rewritten or rewritten.startswith("需要澄清"):
        result["error"] = "改写必须返回非空检索问题，不能提前澄清"
        return result
    
    if len(set(used_history)) != len(used_history) or any(
        index < 1 or index > len(recent_history) for index in used_history
    ):
        result["error"] = "改写引用了无效的历史序号"
        return result

    original_numbers = _number_tokens(question)
    rewritten_numbers = _number_tokens(rewritten)
    if not original_numbers <= rewritten_numbers:
        result["error"] = "改写遗漏或改变了本轮数字条件，请检查原问题和改写文本"
        return result
    
    allowed_numbers = set(original_numbers)
    for index in used_history:
        allowed_numbers.update(_number_tokens(recent_history[index - 1]["content"]))
    if not rewritten_numbers <= allowed_numbers:
        result["error"] = "改写新增了原问题及所选历史中不存在的数字条件"
        return result

    result["answer"] = rewritten
    result["used_history"] = used_history
    result["sub_questions"]=sub_questions
    result["needs_clarification"] = needs_clarification
    result["clarification_question"] = clarification_question
    result["target_source_ids"] = target_source_ids
    return result
