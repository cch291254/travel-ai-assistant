import requests
import time

url="https://httpbin.org/post"
payload={
    "question":"推荐杭州三日游",
    "customer_count":4,
}
# try:
#     response=requests.post(
#         url,
#         json=payload,
#         timeout=5,
#     )
#     print("状态码：",response.status_code)
#     response.raise_for_status()
#     print("请求成功")
#     data=response.json()
#     received_data=data["json"]
#     print("服务器收到的问题：",received_data)
#     print("问题：",received_data["question"])
# except requests.exceptions.RequestException as error:
#     print("请求失败：", error)


def should_retry(status_code):
    retryable_codes = [429, 500, 502, 503, 504]
    if status_code in retryable_codes:
        return True
    return False
# status_codes = [200, 400, 401, 404, 429, 500, 503]
# for status_code in status_codes:
#     result = should_retry(status_code)
#     print(status_code, result)

url="https://httpbin.org/post"
payload={
    "question":"推荐杭州三日游",
    "customer_count":4,
}
question=payload["question"].strip()
max_input_chars=20
if len(question)==0:
    print("问题不能为空")
elif 0<len(question)<=max_input_chars:
    max_attempts=3
    payload["question"]=question
    for attempt in range(max_attempts):
        try:
            response=requests.post(
                url,
                json=payload,
                timeout=5
            )
            status_code=response.status_code
            print("第",attempt+1,"次请求，状态码：",status_code)
            result=should_retry(status_code)
            if status_code==200:
                data=response.json()
                received_data=data["json"]
                print(received_data)
                break
            elif result==False:
                print("不允许重试")
                print("错误内容",response.text)
                break
            elif attempt+1==max_attempts:
                print("重复次数耗尽")
                print("错误内容：",response.text)
                break
            else:
                print("准备重试")
                time.sleep(1)
        except requests.exceptions.RequestException as error:
            print("网络请求错误：",error)

            if attempt+1==max_attempts:
                print("重复次数耗尽")
                break

            print("准备重试")
            time.sleep(1)
else:
    print("问题过长")
