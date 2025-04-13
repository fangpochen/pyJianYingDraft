# app/main.py
import sys
import multiprocessing
import logging # 需要 logging 来获取 logger
import os # 需要 os 来处理路径

# --- 调整 PYTHONPATH (如果需要，以便从根目录运行) ---
# 如果直接运行 python app/main.py，可能需要将项目根目录添加到 sys.path
# current_dir = os.path.dirname(os.path.abspath(__file__))
# project_root = os.path.dirname(current_dir)
# if project_root not in sys.path:
#     sys.path.insert(0, project_root)

# 导入 PyQt6 相关
from PyQt6.QtWidgets import QApplication

# 导入项目模块
try:
    # 使用绝对导入路径 (假设 app 是可查找的包)
    from app.ui.main_window import MainWindow
    from app.util.logging_setup import setup_logging, log_queue # 导入队列以便传递
except ImportError as e:
     print(f"Fatal Import Error: {e}. Cannot start the application.")
     print("Ensure you are running this from the project root directory using 'python -m app.main' or have installed the package.")
     # Log the current sys.path for debugging
     print("Current sys.path:", sys.path)
     sys.exit(1) # 退出，因为没有 UI 或日志无法启动

# 获取 logger 实例，用于记录启动过程中的信息
# 注意：在 setup_logging 调用前，日志可能不会输出到文件或队列
logger = logging.getLogger(__name__)

def main():
    # --- Windows 多进程支持 --- 
    # (如果 run_individual_video_processing 使用 multiprocessing，则需要)
    # 如果不确定，保留它通常是安全的
    multiprocessing.freeze_support()
    logger.debug("Multiprocessing freeze_support() called (if applicable).")

    # --- 配置日志 --- 
    # setup_logging 会配置根 logger，并将 QueueHandler 添加到根 logger
    # 它使用在 logging_setup.py 中定义的 log_queue
    try:
        setup_logging(log_level=logging.INFO, ui_queue=log_queue)
        logger.info("应用程序启动，日志系统已配置。")
    except Exception as log_setup_err:
        # 如果日志设置失败，至少打印到控制台
        print(f"FATAL: Failed to setup logging: {log_setup_err}")
        # 可能需要退出，因为日志对于调试至关重要
        # sys.exit(1)

    # --- 创建 Qt 应用和主窗口 --- 
    try:
        app = QApplication(sys.argv)
        logger.debug("QApplication instance created.")

        # --- 高 DPI 支持 (可选, 但推荐) --- 
        # Qt 通常能自动处理，但可以显式启用
        try:
            # 检查是否为 Windows (ctypes 在其他系统上不可用)
             if sys.platform == "win32":
                 from ctypes import windll
                 # 参数 1 表示 System DPI Aware, 2 表示 Per-Monitor DPI Aware v2
                 # Per-Monitor 通常更好，但 System Aware 兼容性更广
                 # 尝试设置为 Per-Monitor v2 (需要 Windows 10 Creators Update 或更高)
                 try:
                      result = windll.shcore.SetProcessDpiAwareness(2)
                      logger.info(f"尝试设置 DPI Awareness (2=Per Monitor v2): Result={result}")
                 except AttributeError:
                      logger.warning("SetProcessDpiAwareness(2) 不可用，尝试 System Aware (1)")
                      try:
                           result = windll.shcore.SetProcessDpiAwareness(1)
                           logger.info(f"尝试设置 DPI Awareness (1=System Aware): Result={result}")
                      except AttributeError:
                            logger.warning("SetProcessDpiAwareness(1) 也不可用，跳过 DPI 设置。")
             # 对于 macOS 和 Linux，Qt 通常处理得更好
        except ImportError:
            logger.warning("无法导入 ctypes，跳过 Windows DPI 设置。")
        except Exception as dpi_err:
             logger.warning(f"设置 DPI 感知时出错: {dpi_err}")


        main_window = MainWindow()
        logger.debug("MainWindow instance created.")
        main_window.show()
        logger.info("主窗口已显示。启动 Qt 事件循环...")

        # 启动 Qt 事件循环
        sys.exit(app.exec())

    except Exception as app_err:
         logger.critical("启动应用程序时发生未处理的异常", exc_info=True)
         # 尝试显示错误给用户（如果可能）
         try:
              from PyQt6.QtWidgets import QMessageBox
              # 创建临时的 QApplication 以显示消息框（如果主 app 创建失败）
              temp_app = QApplication.instance() or QApplication([])
              QMessageBox.critical(None, "启动错误", f"应用程序启动失败:\n{app_err}")
         except:
              pass # 如果连消息框都无法显示，则没办法了
         sys.exit(1)

if __name__ == "__main__":
    main() 