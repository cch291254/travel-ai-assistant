#工具定义板块
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field,HttpUrl


class SaveToDraftInput(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True,extra="forbid")
            #禁止空白和参数



class KnowledgeSearchInput(BaseModel):
                    #配置字典类型 ,后面都是规则
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    #top_k: int = Field(default=3, strict=True, ge=1, le=10)


class AccommodationItemInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    room_type: str = Field(min_length=1, max_length=100)
    rooms: int = Field(strict=True, gt=0, le=50)
    nights: int = Field(strict=True, gt=0, le=30)
    room_night_price: Decimal | None = Field(
        default=None,
        ge=0,
        decimal_places=2,
        description="元/间/晚",
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
        description="餐饮，元/儿童",
    )
    transport_price: Decimal | None = Field(
            default=None, ge=0, decimal_places=2,
            description="交通，元/儿童",
        )
    guide_price: Decimal | None = Field(
        default=None, ge=0, decimal_places=2,
        description="导游，元/儿童",
    )
    ticket_price: Decimal | None = Field(
        default=None, ge=0, decimal_places=2,
        description="门票，元/儿童",
    )
    boat_price: Decimal | None = Field(
        default=None, ge=0, decimal_places=2,
        description="船票，元/儿童",
    )
    entertainment_price: Decimal | None = Field(
        default=None, ge=0, decimal_places=2,
        description="娱乐，元/儿童",)

class CalculateQuoteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    adults: int = Field(strict=True, ge=1, le=50)
    children: int = Field(strict=True, ge=0, le=50)
    room_items: list[AccommodationItemInput] | None = Field(
        default=None,
        description="住宿明细；空列表表示不住宿",
    )
    meal_price: Decimal | None = Field(
        default=None, ge=0, decimal_places=2,
        description="餐饮，元/成人",
    )
    transport_price: Decimal | None = Field(
        default=None, ge=0, decimal_places=2,
        description="交通，元/成人",
    )
    guide_price: Decimal | None = Field(
        default=None, ge=0, decimal_places=2,
        description="导游，元/成人",
    )
    ticket_price: Decimal | None = Field(
        default=None, ge=0, decimal_places=2,
        description="门票，元/成人",
    )
    boat_price: Decimal | None = Field(
        default=None, ge=0, decimal_places=2,
        description="船票，元/成人",
    )
    entertainment_price: Decimal | None = Field(
        default=None, ge=0, decimal_places=2,
        description="娱乐，元/成人",
    )
    child_prices: ChildPricesInput | None = Field(
    default=None,
    description="儿童单人费用",
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