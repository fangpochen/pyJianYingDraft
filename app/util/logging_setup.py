# app/util/logging_setup.py
import logging
import logging.handlers
import queue
import os

# --- 日志文件名 (相对于项目根目录) ---
LOG_FOLDER = 'logs'
LOG_FILENAME = os.path.join(LOG_FOLDER, 'batch_tool.log')

# 确保日志目录存在
os.makedirs(LOG_FOLDER, exist_ok=True)

# 用于从其他线程/进程传递日志记录到主线程 (例如 UI)
log_queue = queue.Queue(-1)

class QueueHandler(logging.Handler):
    """将日志记录放入队列以便在其他线程中处理 (例如更新UI)"""
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        # 格式化记录并放入队列
        # 注意：格式化现在在这里完成，确保放入队列的是字符串
        self.log_queue.put(self.format(record))

def setup_logging(log_level=logging.INFO, ui_queue=None):
    """配置全局日志记录

    Args:
        log_level: 全局日志记录级别 (例如 logging.INFO, logging.DEBUG).
        ui_queue: 可选的队列，用于将格式化后的日志消息发送给UI线程。
                  如果提供，将添加一个 QueueHandler。
    """
    # 移除所有现有的处理器，以防被多次调用
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 基本配置设置日志级别
    # 注意：basicConfig 只能被调用一次，如果根 logger 已有处理器，它就不起作用。
    # 因此，我们在移除处理器后调用它，或者直接配置根 logger。
    # logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    # 手动设置根 logger
    root_logger.setLevel(log_level)
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')

    # 文件处理器
    try:
        file_handler = logging.FileHandler(LOG_FILENAME, encoding='utf-8', mode='a') # 追加模式
        file_handler.setFormatter(log_formatter)
        file_handler.setLevel(log_level) # 文件处理器也遵循全局级别
        root_logger.addHandler(file_handler)
    except Exception as e:
        # 如果文件处理器创建失败，至少打印错误到控制台
        print(f"[ERROR] Failed to create log file handler for {LOG_FILENAME}: {e}")
        # Optionally raise the error or fallback to a StreamHandler
        # import sys
        # stream_handler = logging.StreamHandler(sys.stderr)
        # stream_handler.setFormatter(log_formatter)
        # root_logger.addHandler(stream_handler)

    # 队列处理器 (如果提供了UI队列)
    if ui_queue:
        queue_handler = QueueHandler(ui_queue)
        queue_handler.setFormatter(log_formatter)
        # UI 队列处理器通常也使用与根 logger 相同的级别
        # 或者可以设置为 DEBUG 以捕获所有消息供 UI 显示
        queue_handler.setLevel(log_level)
        root_logger.addHandler(queue_handler)

    logging.info("日志系统已配置。")
    logging.info(f"详细日志将写入: {os.path.abspath(LOG_FILENAME)}")

# --- Example Usage (可以取消注释进行测试) ---
# if __name__ == '__main__':
#     test_queue = queue.Queue()
#     setup_logging(log_level=logging.DEBUG, ui_queue=test_queue)
#
#     logger_main = logging.getLogger('main_test')
#     logger_util = logging.getLogger('util_test')
#
#     logger_main.debug("这是一条调试信息。")
#     logger_main.info("这是一条普通信息。")
#     logger_util.warning("这是一条警告信息。")
#     logger_util.error("这是一条错误信息。")
#
#     print("\n检查日志文件和队列内容...")
#     print(f"日志文件: {LOG_FILENAME}")
#     print("队列内容:")
#     while not test_queue.empty():
#         print(f"  - {test_queue.get()}") 