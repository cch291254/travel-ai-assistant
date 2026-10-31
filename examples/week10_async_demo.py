import asyncio
import time


async def blocking_wait():
    #异步函数
    time.sleep(1)

async def async_wait():
    #等待期间，让出执行机会
    await asyncio.sleep(1)

async def main():
    #同时安排两个任务
    start=time.perf_counter()
    await asyncio.gather(blocking_wait(),blocking_wait())
    print(f"异步等待：{time.perf_counter()-start:.2f}秒")

    # 同时安排两个任务，任务内部使用异步等待。
    start = time.perf_counter()
    await asyncio.gather(async_wait(), async_wait())
    print(f"异步等待：{time.perf_counter() - start:.2f} 秒")

if __name__=="__main__":
    asyncio.run(main())