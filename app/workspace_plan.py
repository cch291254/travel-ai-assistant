"""当前方案草案的数据结构与检查规则。

草案是普通字典，便于以后直接作为保存接口的请求体。
价格统一用 None 表示“未提供”，0 表示“明确为 0 元”，两者不能混用。
这里只做缺失项检查和组装核算参数，不计算金额。
"""
import json
from uuid import uuid4
import copy
from datetime import date


# 六项单人费用，字段名与后端 CalculateQuoteInput 保持一致。
PRICE_CATEGORIES = [
    ("meal_price", "餐饮"),
    ("transport_price", "交通"),
    ("guide_price", "导游"),
    ("ticket_price", "门票"),
    ("boat_price", "船票"),
    ("entertainment_price", "娱乐"),
]
# dict(成对元素的列表)：把 (字段名, 中文名) 转成 {字段名: 中文名}，用于按键查名称。
PRICE_LABELS = dict(PRICE_CATEGORIES)

PLAN_STATUSES = {"draft": "草案", "pending": "待确认", "confirmed": "员工已确认"}
STATUS_BADGE_COLORS = {"draft": "gray", "pending": "orange", "confirmed": "green"}

# 住宿与后端 room_items 对应：未提供=None，不安排=[]，填写明细=列表。
LODGING_MODES = {"unknown": "未提供", "none": "不安排住宿", "items": "填写房型明细"}


# 作用：为景点、天数和房型行创建临时标识，便于编辑、移动、删除时定位同一行。
# prefix 是 spot/day/room 等前缀；此标识不是数据库中的方案编号。
def new_id(prefix):
    # uuid4() 生成随机 UUID；.hex 取十六进制文本；[:8] 只取前 8 个字符。
    # 截短的标识用于当前页面行定位，不保证全局绝对唯一。
    return f"{prefix}_{uuid4().hex[:8]}"


# 作用：创建一个带标识和名称的景点行；name="" 表示不传名称时创建空白行。
def new_spot(name=""):
    return {"id": new_id("spot"), "name": name}


# 作用：创建一天的路线，包含景点、住宿名称和备注。
# 默认值 () 是不可变空元组，避免用列表作默认值导致多次调用共享同一个可变对象。
def new_day(spots=(), hotel="", notes=""):
    return {
        "id": new_id("day"),
        # 列表推导式：将每个景点名称转换成带 id 的景点字典。
        "spots": [new_spot(name) for name in spots],
        "hotel": hotel,
        "notes": notes,
    }


# 作用：创建一条住宿明细，记录房型、间数、晚数和每间每晚单价。
# room_night_price=None 是“未提供”，0 是“明确零元”，两者含义不同。
def new_room(room_type="", rooms=1, nights=1, room_night_price=None):
    return {
        "id": new_id("room"),
        "room_type": room_type,
        "rooms": rooms,
        "nights": nights,
        "room_night_price": room_night_price,
    }


# 作用：创建一套六项单人价格，初始全部未提供；成人和儿童分别调用，获得独立字典。
def empty_prices():
    # 字典推导式；key, _ 对二元组拆包，_ 代表这里不用的中文名称，不是特殊关键字。
    return {key: None for key, _ in PRICE_CATEGORIES}


# 作用：创建页面编辑所需的完整空白草案；只返回内存字典，不写文件或数据库。
# 每次重新创建列表和价格字典，避免不同草案、成人与儿童价格共用可变数据。
def empty_draft():
    """空白草案：一个会话只持有一份，保存前不生成方案记录。"""
    return {
        "plan_id": None,
        "version": 0,
        "status": "draft",
        "name": "",
        "destination": "",
        "start_date": None,
        "adults": 1,
        "children": 0,
        "days": [new_day()],
        "manual_items": [],
        "prices": {"adult": empty_prices(), "child": empty_prices()},
        "lodging_mode": "unknown",
        "rooms": [],
        "conversation_id": None,
    }


# 作用：把草案或核算参数变成稳定的 JSON 字符串，用于检查修改和核算结果是否过期。
# value 是要转换的数据；此函数不负责保存方案。
def serialize(value):
    """稳定序列化，用于判断“有未保存修改”和核算结果是否过期。"""
    # ensure_ascii=False 保留中文；sort_keys=True 固定字典键顺序，避免仅因键顺序不同而误判修改。
    # default=str：遇到日期、Decimal 等默认不支持的对象时调用 str() 转为字符串。
    # 解析这个快照时，不会自动把字符串恢复成日期或 Decimal 类型。
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


# 作用：把页面草案变成能发给后端的 JSON 数据；日期会变成 "2026-11-08" 这样的字符串。
def draft_to_json(draft):
    return json.loads(serialize(draft))


# 作用：把后端取回的草案恢复成页面能用的数据；日期控件需要 date 对象，不能是字符串。
def restore_draft(draft):
    restored = copy.deepcopy(draft)
    if restored["start_date"]:
        restored["start_date"] = date.fromisoformat(restored["start_date"])
    return restored


# 作用：把 GET /plans/{id} 的结果变成页面草案；编号、版本、状态以数据库字段为准。
def draft_from_plan(plan):
    draft = restore_draft(plan["draft"])
    draft["plan_id"] = plan["id"]
    draft["version"] = plan["current_version"]
    draft["status"] = plan["status"]
    draft["name"] = plan["title"]
    draft["conversation_id"] = plan["conversation_id"]
    return draft


# 作用：找出一套价格中尚未提供的项目，返回中文名称列表，供页面提示。
def _missing_labels(prices):
    # is None 精确判断“未提供”，填入的 0 不算缺失；get 找不到键时也返回 None。
    return [PRICE_LABELS[key] for key, _ in PRICE_CATEGORIES if prices.get(key) is None]


# 作用：汇总成人价格、必要的儿童价格和住宿信息中的缺失项，返回提示文字列表。
# 这里只检查缺失，不修改草案、不算金额，也不代替后端的参数合法性校验。
def find_missing_prices(draft):
    """按当前输入列出缺失的价格项，不涉及金额计算。"""
    missing = []

    adult_missing = _missing_labels(draft["prices"]["adult"])
    if adult_missing:
        missing.append("成人单价未提供：" + "、".join(adult_missing))

    # 没有儿童时不需要儿童价格；有儿童时必须单独填写，不套用成人价。
    if draft["children"] > 0:
        child_missing = _missing_labels(draft["prices"]["child"])
        if child_missing:
            missing.append("儿童单价未提供：" + "、".join(child_missing))

    if draft["lodging_mode"] == "unknown":
        missing.append("住宿未提供（如无需住宿，请选择“不安排住宿”）")
    elif draft["lodging_mode"] == "items":
        if not draft["rooms"]:
            missing.append("住宿明细为空，请添加房型或改为“不安排住宿”")
        # enumerate(..., start=1)：同时取得从 1 开始的显示序号和当前房型字典。
        for index, room in enumerate(draft["rooms"], start=1):
            # strip() 去掉首尾空白；名称为空时，or 右侧文字用作显示名称。
            room_name = room["room_type"].strip() or f"第{index}条房型"
            if not room["room_type"].strip():
                missing.append(f"第{index}条住宿未填写房型")
            if room["room_night_price"] is None:
                missing.append(f"{room_name}未提供每间每晚价格")

    return missing


# 作用：检查名称、目的地、日期、每天景点及住宿是否缺失，生成待确认事项。
# 返回提示不等于员工确认，也不会自动补齐路线。
def find_route_items(draft):
    """路线与基础信息里需要员工补充的内容。"""
    items = []
    if not draft["name"].strip():
        items.append("未填写方案名称")
    if not draft["destination"].strip():
        items.append("未填写目的地")
    if draft["start_date"] is None:
        items.append("未确定出行日期")

    for index, day in enumerate(draft["days"], start=1):
        # any(生成器表达式)：至少一个景点名称去掉空白后非空，就为 True。
        # not any(...) 表示没有有效景点；空列表也会进入这个缺失分支。
        if not any(spot["name"].strip() for spot in day["spots"]):
            items.append(f"第{index}天未安排景点")

    # 最后一天通常返程，不要求住宿。
    if draft["lodging_mode"] != "none":
        # [:-1] 是切片，取最后一项之前的所有天数；最后一天通常返程，不要求住宿。
        for index, day in enumerate(draft["days"][:-1], start=1):
            if not day["hotel"].strip():
                items.append(f"第{index}天未填写住宿")

    return items


# 作用：把页面草案转成后端 CalculateQuoteInput 接受的结构，供核算接口计算。
# 将成人价格移到顶层、住宿模式转为 room_items，并去掉仅供页面使用的行 id。
def build_quote_input(draft):
    """组装与后端 calculate_quote 相同结构的参数，供核算接口使用。"""
    children = draft["children"]
    child_prices = draft["prices"]["child"]

    # values() 遍历字典的值；all(...) 要求每一项都满足条件，这里判断儿童价格是否全未提供。
    # 没有儿童，或儿童价格全未提供时，child_input 为 None；明确填入的 0 会被保留。
    if children == 0 or all(value is None for value in child_prices.values()):
        child_input = None
    else:
        child_input = dict(child_prices)  # 浅复制成新字典；当前价格值没有嵌套字典或列表。

    # 三种状态保留区别：None=住宿未知，[]=不安排住宿，列表=按房型明细核算。
    if draft["lodging_mode"] == "unknown":
        room_items = None
    elif draft["lodging_mode"] == "none":
        room_items = []
    else:
        # 选择后端计算需要的字段；id 只供页面定位，不传给核算接口。
        room_items = [
            {
                "room_type": room["room_type"].strip(),
                "rooms": room["rooms"],
                "nights": room["nights"],
                "room_night_price": room["room_night_price"],
            }
            for room in draft["rooms"]
        ]

    return {
        "adults": draft["adults"],
        "children": children,
        "room_items": room_items,
        # 字典中的 ** 将六项成人价格键值对展开到当前字典顶层。
        **draft["prices"]["adult"],
        "child_prices": child_input,
    }
