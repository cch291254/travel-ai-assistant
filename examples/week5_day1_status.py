import requests

print("\n---状态码---")
status_url="https://httpbin.org/status/500"
status_response=requests.get(status_url,timeout=5)
status_code=status_response.status_code
print("状态码：",status_code)
if 200<=status_code<300:
    print("请求成功")
elif 400<=status_code<500:
    print("客户端请求错误")
elif 500<=status_code<600:
    print("服务器错误")



ur1="https://httpbin.org/ddelay/3"
try:
    response=requests.get(
        ur1,
        timeout=5,
    )
    print("请求成功")
except requests.Timeout:
    print("请求超时，请稍后重试")
except requests.RequestException as error:
    print("其他网络错误：",type(error).__name__)
print("程序继续运行")
