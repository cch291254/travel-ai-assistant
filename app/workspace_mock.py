"""工作台原型使用的演示数据。

- 历史会话列表：固定演示数据，仅占位展示。
- 生成草案：结构化示例数据，不从聊天回答中解析。
"""
import copy
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.workspace_plan import (
    PRICE_CATEGORIES,
    empty_draft,
    new_day,
    new_room,
)


# 历史会话列表占位：真实列表接口实现前，只做展示，不可打开。
DEMO_CONVERSATIONS = {
    "用户A": [
        {"title": "杭州三天两晚 · 亲子", "updated_at": "今天 10:24"},
        {"title": "西湖游船票价核对", "updated_at": "昨天 16:05"},
        {"title": "乌镇一日游接送点", "updated_at": "10-24"},
    ],
    "用户B": [
        {"title": "千岛湖两日 · 公司团建", "updated_at": "今天 09:12"},
        {"title": "灵隐寺开放时间", "updated_at": "10-25"},
    ],
}


def build_demo_draft(conversation_id=None):
    """演示用“生成路线草案”：结构化示例数据，不从聊天回答中解析。"""
    draft = empty_draft()
    draft.update({
        "name": "杭州三天两晚经典线（演示）",
        "destination": "杭州",
        "start_date": date.today() + timedelta(days=14),
        "adults": 2,
        "children": 1,
        "conversation_id": conversation_id,
        "lodging_mode": "items",
    })
    draft["days"] = [
        new_day(["断桥残雪", "白堤", "孤山", "苏堤春晓"], hotel="西湖边精品酒店", notes="下午可安排西湖游船，需确认船票"),
        new_day(["灵隐寺", "飞来峰", "龙井村"], hotel="西湖边精品酒店", notes="灵隐寺需提前预约"),
        new_day(["西溪湿地"], notes="下午返程，预留去车站时间"),
    ]
    # 演示“未提供”和“明确为0元”的区别：导游为0元，船票、娱乐暂未提供。
    draft["prices"]["adult"].update({
        "meal_price": 300.0, "transport_price": 220.0, "guide_price": 0.0,
        "ticket_price": 120.0, "boat_price": None, "entertainment_price": None,
    })
    draft["prices"]["child"].update({
        "meal_price": 150.0, "transport_price": 220.0, "guide_price": 0.0,
        "ticket_price": None, "boat_price": None, "entertainment_price": None,
    })
    draft["rooms"] = [new_room("标准双床房", rooms=1, nights=2, room_night_price=680.0)]
    draft["manual_items"] = ["与客户确认儿童身高（门票按身高分档）"]
    return draft
