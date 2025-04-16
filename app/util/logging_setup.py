# app/util/logging_setup.py
# 优化日志配置，确保所有模块的日志都进入UI队列

import logging
import logging.handlers
import os
import queue
import sys
import time

# 创建一个全局的日志队列，用于向UI传递日志记录
log_queue = queue.Queue()

class QueueHandler(logging.Handler):
    """将日志记录发送到队列的处理程序"""
    
    def __init__(self, queue):
        super().__init__()
        self.queue = queue
        
    def emit(self, record):
        try:
            # 格式化记录为文本
            msg = self.format(record)
            # 将格式化后的消息放入队列
            self.queue.put(msg)
        except Exception:
            self.handleError(record)

def setup_logging(log_level=logging.INFO, ui_queue=None, log_file_name='batch_tool.log'):
    """设置日志记录
    
    Args:
        log_level: 日志级别
        ui_queue: 用于向UI传递日志的队列
        log_file_name: 日志文件名
    """
    # 确保日志目录存在
    os.makedirs('logs', exist_ok=True)
    
    # 使用传入的队列或默认队列
    queue_to_use = ui_queue if ui_queue is not None else log_queue
    
    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # 清除已有的处理程序，避免重复配置
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 创建文件处理程序
    file_handler = logging.FileHandler(f'logs/{log_file_name}', encoding='utf-8')
    file_handler.setLevel(log_level)
    
    # 创建控制台处理程序
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    
    # 创建队列处理程序，用于向UI传递日志
    queue_handler = QueueHandler(queue_to_use)
    queue_handler.setLevel(log_level)
    
    # 设置格式化器
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    queue_handler.setFormatter(formatter)
    
    # 添加处理程序到根日志记录器
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(queue_handler)
    
    # 设置非root日志记录器 (重要!) - 确保所有模块都能记录到队列
    # 特别是我们重点关注的模块
    for module_name in ['app.util.jianying_export', 'app.core.orchestrator', 'app.core.processor']:
        module_logger = logging.getLogger(module_name)
        module_logger.setLevel(log_level)
        # 确保传播设置为True，这样它就会传递给root logger
        module_logger.propagate = True
    
    # 记录一条消息表示日志系统已经设置好了
    logging.info("日志系统已配置，级别：%s，文件：logs/%s，队列处理程序已添加", 
                logging.getLevelName(log_level), log_file_name)
    
    return root_logger

# 如果直接运行此文件，设置日志记录系统（用于测试）
if __name__ == '__main__':
    setup_logging()
    logging.debug("这是一条测试DEBUG消息")
    logging.info("这是一条测试INFO消息")
    logging.warning("这是一条测试WARNING消息")
    logging.error("这是一条测试ERROR消息")
    
    # 从队列中获取消息（模拟UI操作）
    print("\n从队列中获取的消息:")
    try:
        while True:
            message = log_queue.get_nowait()
            print(f"队列消息: {message}")
    except queue.Empty:
        print("队列为空") 