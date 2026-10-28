import logging                 # 导入日志模块
from pathlib import Path       # 处理日志目录和文件路径
from contextvars import ContextVar


#保留当前请求的编号
request_id_var=ContextVar("request_id",default="-")   #多个并发请求共用一个普通全局变量、相互覆盖。

#日志过滤器
class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id=request_id_var.get()
        return True



def setup_logging():
    # app 是统一的父记录器，接收 app.tools、app.tool_calling 等模块的日志。
    logger = logging.getLogger("app")
    logger.setLevel(logging.INFO)

    # 已经配置过就直接返回，避免重复添加处理器，造成一条日志输出多次。
    if logger.handlers:
        return

    # 日志目录固定在项目根目录下，不受启动命令所在目录影响。
    log_dir = Path(__file__).resolve().parents[1] / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # 统一格式：时间、日志级别、模块名称、具体内容。
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | "
        "request_id=%(request_id)s | %(message)s"

    )

    # 终端处理器：运行后端时，可以直接看到日志。
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(RequestIdFilter())  # 给终端日志补充编号,过滤

    # 文件处理器：使用 UTF-8 编码，把日志追加到 app.log。
    file_handler = logging.FileHandler(
        log_dir / "app.log",
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(RequestIdFilter())  # 给文件日志补充编号

    # 将两个处理器交给 app 记录器，统一负责输出。
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.propagate = False   # 到 app 这一层输出即可，避免继续向上传递造成重复。


# 直接运行本模块时，生成一条测试日志；被其他模块导入时不会执行。
if __name__ == "__main__":
    setup_logging()
    test_logger = logging.getLogger("app.demo")
    test_logger.info("日志配置测试成功")
