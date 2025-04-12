# gui_app.py
# 主程序入口，包含Tkinter UI界面逻辑

import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
# import threading # No longer needed directly here
import os
import queue
import logging
import logging.handlers
import configparser # 导入配置解析器
import multiprocessing # 导入 multiprocessing

# --- 配置和日志文件名 ---
CONFIG_FILE = 'batch_tool_config.ini'
LOG_FILENAME = 'batch_tool.log'

# --- 后台处理逻辑导入 (修改为新的 orchestrator) ---
try:
    # Import the main function from the new orchestrator module
    from jianying_orchestrator import run_individual_video_processing
except ImportError:
    logging.basicConfig(level=logging.ERROR)
    # Update error message
    logging.exception("严重错误：无法导入 jianying_orchestrator.py。")
    messagebox.showerror("依赖错误", "无法导入 jianying_orchestrator.py。\n请确保该文件与 gui_app.py 在同一目录下。")
    # Rename the variable for clarity
    run_individual_video_processing = None

# --- 日志配置 (保持不变) ---
log_queue = queue.Queue(-1)
class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
    def emit(self, record):
        self.log_queue.put(self.format(record))

log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
# 设置全局日志级别为 INFO
logging.basicConfig(level=logging.INFO)
file_handler = logging.FileHandler(LOG_FILENAME, encoding='utf-8')
file_handler.setFormatter(log_formatter)
# 文件处理器的级别也设置为 INFO
file_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(file_handler)
queue_handler = QueueHandler(log_queue)
queue_handler.setFormatter(log_formatter)
# UI 队列处理器保持 INFO 级别
queue_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(queue_handler)

# --- 默认路径配置 (现在从 config 加载) ---
# 这些作为后备默认值，如果配置文件不存在或缺少键
DEFAULT_DRAFT_NAME = "简单测试_4940"
DEFAULT_DRAFT_FOLDER_PATH = "D:\\DJianYingDrafts\\JianyingPro Drafts"

class BatchToolApp:
    def __init__(self, root):
        self.root = root
        self.root.title("剪映批量处理工具 v1.2 (逐个处理)")
        self.root.geometry("700x550")
        self.config = configparser.ConfigParser()
        self.input_folder_var = tk.StringVar()
        self.output_folder_var = tk.StringVar()
        self.draft_folder_var = tk.StringVar()
        self.draft_name_var = tk.StringVar()
        self.delete_source_var = tk.BooleanVar(value=True)
        self.load_config()
        self.setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.process = None # 初始化进程对象引用
        logging.info("应用程序界面初始化完成")

    def setup_ui(self):
        """设置用户界面元素"""
        self.config_frame = tk.Frame(self.root, padx=10, pady=10)
        self.config_frame.pack(fill=tk.X)
        self.log_frame = tk.Frame(self.root, padx=10, pady=5)
        self.log_frame.pack(fill=tk.BOTH, expand=True)

        # --- 配置区域 --- 
        tk.Label(self.config_frame, text="输入文件夹 (包含批次子文件夹):", anchor="w").grid(row=0, column=0, sticky="w", pady=2)
        self.input_entry = tk.Entry(self.config_frame, textvariable=self.input_folder_var, width=60)
        self.input_entry.grid(row=0, column=1, sticky="ew", padx=5)
        self.input_button = tk.Button(self.config_frame, text="浏览...", command=self.select_input_folder)
        self.input_button.grid(row=0, column=2)

        tk.Label(self.config_frame, text="输出文件夹:", anchor="w").grid(row=1, column=0, sticky="w", pady=2)
        self.output_entry = tk.Entry(self.config_frame, textvariable=self.output_folder_var, width=60)
        self.output_entry.grid(row=1, column=1, sticky="ew", padx=5)
        self.output_button = tk.Button(self.config_frame, text="浏览...", command=self.select_output_folder)
        self.output_button.grid(row=1, column=2)

        tk.Label(self.config_frame, text="剪映草稿库路径:", anchor="w").grid(row=2, column=0, sticky="w", pady=2)
        self.draft_folder_entry = tk.Entry(self.config_frame, textvariable=self.draft_folder_var, width=60)
        self.draft_folder_entry.grid(row=2, column=1, sticky="ew", padx=5)
        self.draft_folder_button = tk.Button(self.config_frame, text="浏览...", command=self.select_draft_folder)
        self.draft_folder_button.grid(row=2, column=2)

        tk.Label(self.config_frame, text="目标草稿名称:", anchor="w").grid(row=3, column=0, sticky="w", pady=2)
        self.draft_name_entry = tk.Entry(self.config_frame, textvariable=self.draft_name_var, width=60)
        self.draft_name_entry.grid(row=3, column=1, sticky="ew", padx=5)

        # 新增：删除源文件勾选框
        self.delete_source_check = tk.Checkbutton(
            self.config_frame, 
            text="处理成功后删除源视频 (切割片段或原始视频)", 
            variable=self.delete_source_var
        )
        self.delete_source_check.grid(row=4, column=0, columnspan=1, sticky="w", pady=5, padx=5)

        self.start_button = tk.Button(self.config_frame, text="开始逐个处理视频任务", command=self.start_processing, width=15, height=2, bg="lightblue")
        self.start_button.grid(row=4, column=1, pady=10, sticky="e")
        if run_individual_video_processing is None:
            self.start_button.config(state=tk.DISABLED, text="依赖错误")
        self.config_frame.grid_columnconfigure(1, weight=1)

        # --- 日志区域 --- 
        tk.Label(self.log_frame, text="处理日志 (详细日志请查看 batch_tool.log):", anchor="w").pack(fill=tk.X, pady=(0, 5))
        self.log_text = scrolledtext.ScrolledText(self.log_frame, wrap=tk.WORD, state=tk.DISABLED, height=15)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.root.after(100, self.process_log_queue) # Start log queue polling

    def load_config(self):
        """加载配置文件中的路径和设置"""
        try:
            if os.path.exists(CONFIG_FILE):
                self.config.read(CONFIG_FILE, encoding='utf-8')
                logging.info(f"成功加载配置文件: {CONFIG_FILE}")
            else:
                 logging.info(f"配置文件 {CONFIG_FILE} 不存在，将使用默认值或空值。")

            self.input_folder_var.set(self.config.get('Paths', 'InputFolder', fallback=''))
            self.output_folder_var.set(self.config.get('Paths', 'OutputFolder', fallback=''))
            self.draft_folder_var.set(self.config.get('Paths', 'DraftFolder', fallback=DEFAULT_DRAFT_FOLDER_PATH))
            self.draft_name_var.set(self.config.get('Settings', 'DraftName', fallback=DEFAULT_DRAFT_NAME))

        except Exception as e:
             logging.exception("加载配置时出错")
             # Fallback to defaults on error
             self.input_folder_var.set('')
             self.output_folder_var.set('')
             self.draft_folder_var.set(DEFAULT_DRAFT_FOLDER_PATH)
             self.draft_name_var.set(DEFAULT_DRAFT_NAME)

    def save_config(self):
        """将当前的路径和设置保存到配置文件"""
        try:
            if 'Paths' not in self.config:
                self.config.add_section('Paths')
            if 'Settings' not in self.config:
                 self.config.add_section('Settings')

            self.config.set('Paths', 'InputFolder', self.input_folder_var.get())
            self.config.set('Paths', 'OutputFolder', self.output_folder_var.get())
            self.config.set('Paths', 'DraftFolder', self.draft_folder_var.get())
            self.config.set('Settings', 'DraftName', self.draft_name_var.get())

            with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
                self.config.write(configfile)
            logging.info(f"配置已保存到: {CONFIG_FILE}")
        except Exception as e:
            logging.exception("保存配置时出错")

    def on_closing(self):
        """关闭窗口时的处理程序"""
        logging.info("应用程序正在关闭，保存配置...")
        self.save_config()
        # 尝试终止正在运行的子进程
        if self.process and self.process.is_alive():
            logging.warning("窗口关闭时后台进程仍在运行，尝试终止...")
            try:
                self.process.terminate() # 尝试终止
                self.process.join(timeout=1) # 等待一小段时间让其结束
                if self.process.is_alive():
                    logging.warning("后台进程未能立即终止。")
                else:
                    logging.info("后台进程已终止。")
            except Exception as e:
                logging.error(f"尝试终止后台进程时出错: {e}")
        self.root.destroy()

    def select_folder(self, folder_var):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            folder_var.set(folder_selected)

    def select_input_folder(self): self.select_folder(self.input_folder_var)
    def select_output_folder(self): self.select_folder(self.output_folder_var)
    def select_draft_folder(self): self.select_folder(self.draft_folder_var)

    def process_log_queue(self):
        try:
            while True:
                record = log_queue.get_nowait()
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, record + "\n")
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_log_queue)

    def processing_finished(self):
         # 检查进程是否真的结束了 (以防万一)
         if self.process and self.process.is_alive():
              logging.warning("processing_finished 被调用，但后台进程仍在运行？！？")
              # 可能需要再次安排检查
              self.root.after(500, self.check_process_status)
              return
         # 清理进程引用
         self.process = None
         self.start_button.config(state=tk.NORMAL)
         messagebox.showinfo("完成", "逐个处理已完成！请查看UI日志和 batch_tool.log 获取详细信息。")

    def start_processing(self):
        # --- 检查是否已有进程在运行 ---
        if self.process and self.process.is_alive():
             messagebox.showwarning("运行中", "一个处理任务已经在后台运行，请等待其完成。")
             return

        input_folder = self.input_folder_var.get()
        output_folder = self.output_folder_var.get()
        draft_folder_path = self.draft_folder_var.get()
        draft_name = self.draft_name_var.get()
        delete_source = self.delete_source_var.get()

        # --- Validation --- 
        if not input_folder or not os.path.isdir(input_folder):
            messagebox.showerror("错误", "请选择有效的输入文件夹！")
            return
        if not output_folder:
             messagebox.showerror("错误", "请指定输出文件夹！")
             return
        if not os.path.exists(output_folder):
             if messagebox.askyesno("确认", f"输出文件夹 '{output_folder}' 不存在，是否创建？"):
                 try:
                     os.makedirs(output_folder)
                     logging.info(f"已创建输出文件夹: {output_folder}")
                 except Exception as e:
                     logging.exception(f"无法创建输出文件夹")
                     messagebox.showerror("错误", f"无法创建输出文件夹: {e}")
                     return
             else:
                 return
        elif not os.path.isdir(output_folder):
             messagebox.showerror("错误", f"指定的输出路径 '{output_folder}' 已存在但不是文件夹！")
             return
        if not draft_folder_path or not os.path.isdir(draft_folder_path):
            messagebox.showerror("错误", "请提供有效的剪映草稿库路径！")
            return
        if not draft_name:
            messagebox.showerror("错误", "请输入目标草稿名称！")
            return
        if run_individual_video_processing is None:
            messagebox.showerror("依赖错误", "后台处理模块未能加载，无法启动处理。")
            return

        # --- Start Processing --- 
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.insert(tk.END, "开始逐个处理视频任务...\n")
        self.log_text.config(state=tk.DISABLED)
        self.start_button.config(state=tk.DISABLED)

        logging.info("准备启动后台逐个视频处理...")
        logging.info(f"  输入文件夹: {input_folder}")
        logging.info(f"  输出文件夹: {output_folder}")
        logging.info(f"  草稿库路径: {draft_folder_path}")
        logging.info(f"  目标草稿名: {draft_name}")
        logging.info(f"  处理后删除源文件: {'是' if delete_source else '否'}")

        # --- 使用 multiprocessing 启动后台进程 ---
        try:
             self.process = multiprocessing.Process(
                 target=run_individual_video_processing,
                 args=(input_folder, output_folder, draft_name, draft_folder_path,
                       delete_source),
                 daemon=True
             )
             self.process.start()
             logging.info(f"后台处理进程已启动 (PID: {self.process.pid}) - 正在逐个处理视频")
             self.check_process_status()

        except Exception as e:
            logging.exception("启动后台处理进程时发生错误")
            messagebox.showerror("启动错误", f"无法启动后台进程: {e}")
            self.start_button.config(state=tk.NORMAL)

    def check_process_status(self):
        """定期检查后台进程是否仍在运行"""
        if self.process is None:
             # 进程已经结束或从未启动
             return

        if self.process.is_alive():
            # 进程仍在运行，安排下一次检查
            self.root.after(500, self.check_process_status) # 每 500ms 检查一次
        else:
            # 进程已结束
            logging.info(f"后台处理进程 (PID: {self.process.pid}) 已结束。退出码: {self.process.exitcode}")
            if self.process.exitcode != 0:
                 logging.warning(f"后台进程退出码非零 ({self.process.exitcode})，可能表示发生错误。请检查 batch_tool.log。")
            # 调用完成处理函数
            self.processing_finished()

if __name__ == "__main__":
    # --- multiprocessing 在 Windows 上的注意事项 ---
    # Windows 需要这个保护来防止子进程重新导入并执行主模块代码
    multiprocessing.freeze_support()

    # 确保在高DPI屏幕上显示正常 (Windows)
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    app = BatchToolApp(root)
    root.mainloop() 