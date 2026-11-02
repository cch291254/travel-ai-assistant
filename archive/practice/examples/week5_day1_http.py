import requests
url="https://httpbin.org/get"
params={
    "city":"hangzhou",
    "days":3,
    }
headers={
    "Accept":"applcation/json",
    "x-Project":"travel-ai-assistant"}
response=requests.get(
    url,
    params=params,
    headers=headers,
    timeout=5,
    )
data=response.json()
print("请求地址:",response.url)
print("状态码:",response.status_code)
print("查询参数：",data["args"])   
print("项目标识：",data["headers"].get("x-Project"))
print("响应类型:",response.headers.get("content-type"))
print(
    "本地发送的项目标识：",
    response.request.headers.get("X-Project"),
)

print("\n---post实验---")
post_url="https://httpbin.org/post"
payload={"question":"推荐杭州三日游线路","customer_count":4}
post_response=requests.post(post_url,
json=payload,
timeout=5,)
post_data=post_response.json()
print("post状态码：",post_response.status_code)
print("服务器收到的body:",post_data["json"])
print("请求内容类型：",post_response.request.headers.get("content-type"))




