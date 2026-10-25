#工具定义板块
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field,HttpUrl


class KnowledgeSearchInput(BaseModel):
                    #配置字典类型 ,后面都是规则
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=3, strict=True, ge=1, le=10)


class AccommodationItemInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    room_type: str = Field(min_length=1, max_length=100)
    rooms: int = Field(strict=True, gt=0, le=50)
    nights: int = Field(strict=True, gt=0, le=30)
    room_night_price: Decimal | None = Field(
        default=None,
        ge=0,
        decimal_places=2,
        description="住宿参考费用，人民币元/间/晚；None表示未提供，0表示明确为零",
    )

class ChildPricesInput(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    meal_price: Decimal | None = Field(
        default=None,
        ge=0,
        decimal_places=2,
        description="餐饮参考费用，人民币元/儿童/整条线路",
    )
    transport_price: Decimal | None = Field(
            default=None, ge=0, decimal_places=2,
            description="交通参考费用，人民币元/儿童/整条线路",
        )
    guide_price: Decimal | None = Field(
        default=None, ge=0, decimal_places=2,
        description="导游参考费用，人民币元/儿童/整条线路",
    )
    ticket_price: Decimal | None = Field(
        default=None, ge=0, decimal_places=2,
        description="门票参考费用，人民币元/儿童/整条线路",
    )
    boat_price: Decimal | None = Field(
        default=None, ge=0, decimal_places=2,
        description="船票参考费用，人民币元/儿童/整条线路",
    )
    entertainment_price: Decimal | None = Field(
        default=None, ge=0, decimal_places=2,
        description="娱乐参考费用，人民币元/儿童/整条线路",)

class CalculateQuoteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    adults: int = Field(strict=True, ge=1, le=50)
    children: int = Field(strict=True, ge=0, le=50)
    room_items: list[AccommodationItemInput] | None = Field(
        default=None,
        description="住宿明细；None表示未提供，空列表表示不住宿，每项房间数和晚数必须大于0",
    )
    meal_price: Decimal | None = Field(
        default=None, ge=0, decimal_places=2,
        description="餐饮参考费用，人民币元/成人/整条线路",
    )
    transport_price: Decimal | None = Field(
        default=None, ge=0, decimal_places=2,
        description="交通参考费用，人民币元/成人/整条线路",
    )
    guide_price: Decimal | None = Field(
        default=None, ge=0, decimal_places=2,
        description="导游参考费用，人民币元/成人/整条线路",
    )
    ticket_price: Decimal | None = Field(
        default=None, ge=0, decimal_places=2,
        description="门票参考费用，人民币元/成人/整条线路",
    )
    boat_price: Decimal | None = Field(
        default=None, ge=0, decimal_places=2,
        description="船票参考费用，人民币元/成人/整条线路",
    )
    entertainment_price: Decimal | None = Field(
        default=None, ge=0, decimal_places=2,
        description="娱乐参考费用，人民币元/成人/整条线路",
    )
    child_prices: ChildPricesInput | None = Field(
    default=None,
    description="员工提供的儿童单人各项费用；未提供时不能套用成人价格",
)


class WebSearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query:str=Field(min_length=1,max_length=128,)
    count:int=Field(default=5,strict=True,ge=1,le=50)  #返回的数量


class WebFetchInput(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True,extra="forbid")

    url:HttpUrl



if __name__ == "__main__":
    checked = WebSearchInput.model_validate({
        "query": "  西湖游船 官方票价  ",
    })

    print(checked.model_dump())


    checked = WebFetchInput.model_validate({
    "url": "https://example.com/article",
    })

    print(checked.model_dump(mode="json"))