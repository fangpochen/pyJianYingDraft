# app/ui/main_window.py
import sys
import os
import queue
import logging
import random  # 添加random库用于随机选择模板
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QPlainTextEdit,
    QCheckBox, QMessageBox, QGridLayout, QSpacerItem, QSizePolicy, QSlider,
    QButtonGroup, QRadioButton, QScrollArea, QGroupBox  # 添加QScrollArea和QGroupBox用于模板选择区域
)
from PyQt6.QtCore import QThread, pyqtSignal, QObject, QTimer, Qt

# 导入核心处理函数和配置、日志工具
try:
    # 注意相对导入路径
    from ..core.orchestrator import run_individual_video_processing
    from ..core.draft_exporter import export_clean_draft
    from ..config import load_config, save_config
    from ..util.logging_setup import log_queue # 使用 setup_logging 中定义的队列
except ImportError as e:
    # 如果直接运行此文件进行测试，导入会失败，提供备用方案或提示
    print(f"Import Error: {e}. Make sure the script is run as part of the package.")
    # Fallback for direct execution (less ideal)
    run_individual_video_processing = None
    export_clean_draft = None
    load_config = None
    save_config = None
    log_queue = queue.Queue() # Dummy queue

logger = logging.getLogger(__name__)

# --- 后台工作线程 ---
class WorkerSignals(QObject):
    ''' 定义工作线程可发出的信号 '''
    finished = pyqtSignal(bool, str) # 发送 bool 表示成功/失败，str 表示消息
    progress = pyqtSignal(str)       # 发送字符串日志消息
    # 可以添加其他信号，例如进度百分比等

class ProcessingWorker(QObject):
    ''' 执行后台处理任务的 Worker '''
    signals = WorkerSignals()

    def __init__(self, input_folder, output_folder, draft_name, draft_folder_path, delete_source, num_segments, keep_bgm, bgm_volume=100, main_track_volume=100, process_mode="split", target_videos_count=1, process_by_subfolder=False, videos_per_subfolder=0, selected_templates=[]):
        super().__init__()
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.draft_name = draft_name
        self.draft_folder_path = draft_folder_path
        self.delete_source = delete_source
        self.num_segments = num_segments
        self.keep_bgm = keep_bgm
        self.bgm_volume = bgm_volume
        self.main_track_volume = main_track_volume
        self.process_mode = process_mode  # 新增：处理模式参数
        self.target_videos_count = target_videos_count  # 新增：目标生成视频数量
        self.process_by_subfolder = process_by_subfolder  # 新增：是否按子目录循环处理
        self.videos_per_subfolder = videos_per_subfolder  # 新增：每个子目录处理的视频数量
        self.selected_templates = selected_templates  # 新增：选择的模板列表，用于每个视频任务随机选择
        self.is_cancelled = False

    def run(self):
        ''' 执行实际的处理任务，并处理返回结果 '''
        final_success = False
        final_message = "处理未启动"
        try:
            if run_individual_video_processing is None:
                 raise RuntimeError("核心处理函数未能加载")

            # --- 调用实际处理函数，并捕获其返回的字典 --- 
            logger.info("Worker 开始调用 run_individual_video_processing...")
            result_dict = run_individual_video_processing(
                self.input_folder, 
                self.output_folder, 
                self.draft_name, 
                self.draft_folder_path, 
                self.delete_source,
                self.num_segments,
                self.keep_bgm,  # 传递keep_bgm参数
                self.bgm_volume,  # 传递bgm_volume参数
                self.main_track_volume,  # 传递main_track_volume参数
                self.process_mode,  # 传递处理模式参数
                self.target_videos_count,  # 传递目标生成视频数量参数
                self.process_by_subfolder,  # 传递是否按子目录循环处理参数
                self.videos_per_subfolder,   # 传递每个子目录处理的视频数量参数
                self.selected_templates  # 传递选择的模板列表，用于每个视频任务随机选择
            )
            logger.info(f"run_individual_video_processing 调用完成，返回: {result_dict}")
            # --- 结束调用 --- 

            # 根据返回的字典设置最终状态和消息
            final_success = result_dict.get('success', False)
            final_message = result_dict.get('message', '处理完成但未收到明确消息')

            # 可以在这里添加逻辑，例如如果 tasks_found 为 0，修改消息
            if final_success and result_dict.get('tasks_found', -1) == 0:
                 # 即使 success 为 True，但如果没找到任务，修改消息
                 # final_message = "未找到可处理的视频任务。" # 或者让 orchestrator 返回这个消息
                 pass # 假设 orchestrator 返回的消息已包含此信息

        except Exception as e:
            # 捕获调用 run_individual_video_processing 本身可能抛出的异常
            # (理论上 orchestrator 应该在其内部处理异常并返回失败字典，但作为保险)
            logger.exception("后台处理任务执行期间发生意外错误")
            final_message = f"处理过程中发生意外错误: {e}"
            final_success = False
        finally:
            if not self.is_cancelled:
                # 使用从 result_dict 或异常处理中获取的状态和消息
                self.signals.finished.emit(final_success, final_message)

    def cancel(self):
        self.is_cancelled = True
        # 可能需要更复杂的取消逻辑来中断 run_individual_video_processing
        logger.warning("后台任务被请求取消 (简单标记，可能无法立即停止)")


# --- 主窗口 ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("剪映批量处理工具 v2.1 (PyQt6)")
        self.setGeometry(100, 100, 850, 800)  # 将窗口高度从700增加到800

        self.config_data = {}
        self.worker_thread = None
        self.processing_worker = None
        self.log_timer = QTimer(self) # 用于轮询日志队列
        
        # 存储模板复选框的字典
        self.template_checkboxes = {}
        # 存储上次选择的模板列表
        self.selected_templates = []

        self.init_ui()
        self.load_initial_config()
        self.setup_log_polling()

        # 确保在依赖错误时禁用按钮
        if run_individual_video_processing is None:
             self.start_button.setEnabled(False)
             self.start_button.setText("任务处理依赖错误")
             QMessageBox.critical(self, "依赖错误",
                                  "无法导入核心处理逻辑 (app/core/orchestrator.py)。\n"
                                  "请确保所有依赖项已安装且文件结构正确。")
        # 新增：检查导出函数依赖
        if export_clean_draft is None:
             # 假设 self.export_json_button 已在 init_ui 中创建
             if hasattr(self, 'export_json_button'):
                 self.export_json_button.setEnabled(False)
                 self.export_json_button.setText("Zip导出依赖错误")
                 # 可以选择也弹出一个警告，或者只禁用按钮
                 # QMessageBox.critical(self, "依赖错误",
                 #                      "无法导入草稿导出逻辑 (app/core/draft_exporter.py)。")
                 
        # 删除硬编码设置BGM音量为0的代码
        # self.bgm_volume_slider.setValue(0)
        # self.update_volume_label(0)
        # logger.info("BGM音量已设置为0（静音）")

    def init_ui(self):
        """初始化用户界面布局和组件"""
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- 配置区域 ---
        config_layout = QGridLayout()
        config_layout.setSpacing(10)

        # 输入文件夹
        config_layout.addWidget(QLabel("输入文件夹 (含子目录):"), 0, 0)
        self.input_entry = QLineEdit()
        config_layout.addWidget(self.input_entry, 0, 1)
        self.input_button = QPushButton("浏览...")
        self.input_button.clicked.connect(self.select_input_folder)
        config_layout.addWidget(self.input_button, 0, 2)

        # 输出文件夹
        config_layout.addWidget(QLabel("输出文件夹:"), 1, 0)
        self.output_entry = QLineEdit()
        config_layout.addWidget(self.output_entry, 1, 1)
        self.output_button = QPushButton("浏览...")
        self.output_button.clicked.connect(self.select_output_folder)
        config_layout.addWidget(self.output_button, 1, 2)

        # 草稿库路径
        config_layout.addWidget(QLabel("剪映草稿库路径:"), 2, 0)
        self.draft_folder_entry = QLineEdit()
        config_layout.addWidget(self.draft_folder_entry, 2, 1)
        self.draft_folder_button = QPushButton("浏览...")
        self.draft_folder_button.clicked.connect(self.select_draft_folder)
        config_layout.addWidget(self.draft_folder_button, 2, 2)

        # 草稿名称
        config_layout.addWidget(QLabel("目标草稿名称:"), 3, 0)
        self.draft_name_entry = QLineEdit()
        config_layout.addWidget(self.draft_name_entry, 3, 1, 1, 2) # Span across 2 columns
        
        # --- 新增：随机模板选择区域 ---
        config_layout.addWidget(QLabel("或选择随机模板:"), 4, 0)
        template_buttons_layout = QHBoxLayout()
        
        # 刷新模板按钮
        self.refresh_templates_button = QPushButton("刷新模板列表")
        self.refresh_templates_button.clicked.connect(self.refresh_templates)
        template_buttons_layout.addWidget(self.refresh_templates_button)
        
        # 全选/取消全选按钮
        self.select_all_button = QPushButton("全选")
        self.select_all_button.clicked.connect(self.select_all_templates)
        template_buttons_layout.addWidget(self.select_all_button)
        
        self.deselect_all_button = QPushButton("取消全选")
        self.deselect_all_button.clicked.connect(self.deselect_all_templates)
        template_buttons_layout.addWidget(self.deselect_all_button)
        
        template_buttons_layout.addStretch()
        config_layout.addLayout(template_buttons_layout, 4, 1, 1, 2)
        
        # 创建模板选择区域
        templates_group = QGroupBox("可选模板列表 (勾选后将随机使用其中一个)")
        templates_layout = QVBoxLayout(templates_group)
        
        # 使用滚动区域来容纳模板复选框
        self.templates_scroll_area = QScrollArea()
        self.templates_scroll_area.setWidgetResizable(True)
        # 设置最小高度，增加可视区域大小
        self.templates_scroll_area.setMinimumHeight(150)  # 增加模板区域的最小高度
        self.templates_container = QWidget()
        self.templates_container_layout = QVBoxLayout(self.templates_container)
        self.templates_container_layout.setSpacing(5)
        self.templates_container_layout.addStretch()
        
        self.templates_scroll_area.setWidget(self.templates_container)
        templates_layout.addWidget(self.templates_scroll_area)
        
        # 添加模板区域到主配置中
        config_layout.addWidget(templates_group, 5, 0, 1, 3)
        
        # --- 新增：处理模式选择 ---
        config_layout.addWidget(QLabel("处理模式:"), 6, 0)
        process_mode_layout = QHBoxLayout()
        
        self.mode_group = QButtonGroup(self)
        self.split_mode_radio = QRadioButton("分割素材后替换")
        self.merge_mode_radio = QRadioButton("直接素材替换")
        self.split_mode_radio.setChecked(True)  # 默认选中分割模式
        
        self.mode_group.addButton(self.split_mode_radio)
        self.mode_group.addButton(self.merge_mode_radio)
        
        process_mode_layout.addWidget(self.split_mode_radio)
        process_mode_layout.addWidget(self.merge_mode_radio)
        process_mode_layout.addStretch()
        
        config_layout.addLayout(process_mode_layout, 6, 1, 1, 2)
        
        # 切换文本标签的显示
        self.split_mode_radio.toggled.connect(self.update_segments_label)
        self.split_mode_radio.toggled.connect(self.update_button_text)
        
        # --- 修改：分割/融合段数 ---
        self.segments_label = QLabel("替换素材段数:")
        config_layout.addWidget(self.segments_label, 7, 0)
        self.num_segments_entry = QLineEdit()
        self.num_segments_entry.setPlaceholderText("默认为 1 (不分割)") # 添加提示
        config_layout.addWidget(self.num_segments_entry, 7, 1, 1, 2) # Span across 2 columns
        
        # --- 新增：目标生成视频数量 ---
        config_layout.addWidget(QLabel("目标生成视频数量:"), 8, 0)
        self.target_videos_count_entry = QLineEdit()
        self.target_videos_count_entry.setPlaceholderText("默认为 1 (不组合)")
        config_layout.addWidget(self.target_videos_count_entry, 8, 1, 1, 2)
        
        # --- 新增：按子目录循环处理和每个子目录处理视频数量 ---
        subfolder_layout = QHBoxLayout()
        self.process_by_subfolder_check = QCheckBox("按子目录循环处理")
        subfolder_layout.addWidget(self.process_by_subfolder_check)
        
        subfolder_layout.addWidget(QLabel("每个子目录处理视频数量:"))
        self.videos_per_subfolder_entry = QLineEdit()
        self.videos_per_subfolder_entry.setPlaceholderText("默认为0 (不限制)")
        self.videos_per_subfolder_entry.setMaximumWidth(150)  # 限制输入框宽度，使其不会占据太大空间
        subfolder_layout.addWidget(self.videos_per_subfolder_entry)
        
        subfolder_layout.addStretch()
        config_layout.addLayout(subfolder_layout, 9, 0, 1, 3)  # 添加到第9行
        
        # --- 新增：BGM音量控制（从原来的第9行调整到第10行） ---
        config_layout.addWidget(QLabel("BGM音量:"), 10, 0)
        bgm_volume_layout = QHBoxLayout()
        
        # 创建音量滑动条
        self.bgm_volume_slider = QSlider()
        self.bgm_volume_slider.setOrientation(Qt.Orientation.Horizontal)  # 水平方向
        self.bgm_volume_slider.setMinimum(0)
        self.bgm_volume_slider.setMaximum(100)
        self.bgm_volume_slider.setValue(0)  # 默认0%（静音）
        self.bgm_volume_slider.setFixedWidth(300)
        bgm_volume_layout.addWidget(self.bgm_volume_slider)
        
        # 添加音量数值显示标签
        self.bgm_volume_label = QLabel("0%")
        bgm_volume_layout.addWidget(self.bgm_volume_label)
        
        # 当滑动条值改变时更新标签
        self.bgm_volume_slider.valueChanged.connect(self.update_volume_label)
        
        # 添加音量控制布局到主配置布局
        config_layout.addLayout(bgm_volume_layout, 10, 1, 1, 2)
        # --- BGM音量控制结束 ---

        # --- 新增：主轨道音量控制（从原来的第10行调整到第11行） ---
        config_layout.addWidget(QLabel("主轨道音量:"), 11, 0)
        main_volume_layout = QHBoxLayout()
        
        # 创建音量滑动条
        self.main_volume_slider = QSlider()
        self.main_volume_slider.setOrientation(Qt.Orientation.Horizontal)  # 水平方向
        self.main_volume_slider.setMinimum(0)
        self.main_volume_slider.setMaximum(100)
        self.main_volume_slider.setValue(100)  # 默认100%
        self.main_volume_slider.setFixedWidth(300)
        main_volume_layout.addWidget(self.main_volume_slider)
        
        # 添加音量数值显示标签
        self.main_volume_label = QLabel("100%")
        main_volume_layout.addWidget(self.main_volume_label)
        
        # 当滑动条值改变时更新标签
        self.main_volume_slider.valueChanged.connect(self.update_main_volume_label)
        
        # 添加音量控制布局到主配置布局
        config_layout.addLayout(main_volume_layout, 11, 1, 1, 2)
        # --- 主轨道音量控制结束 ---

        # --- 调整行号到 12 ---
        # 删除源文件选项和使用模板BGM选项
        checkbox_layout = QHBoxLayout()
        
        self.delete_source_check = QCheckBox("处理成功后删除源视频")
        self.delete_source_check.setChecked(True) # 设置默认选中
        checkbox_layout.addWidget(self.delete_source_check)
        
        self.keep_bgm_check = QCheckBox("使用模板中的BGM")
        self.keep_bgm_check.setChecked(True)  # 默认选中
        checkbox_layout.addWidget(self.keep_bgm_check)
        
        config_layout.addLayout(checkbox_layout, 12, 0, 1, 3)  # 放在音量滑动条下方，跨越3列

        # --- 调整行号到 13 ---
        # 开始按钮
        self.start_button = QPushButton("开始分割素材后替换处理")
        self.start_button.setFixedHeight(40) # Make button taller
        self.start_button.setStyleSheet("background-color: lightblue; font-weight: bold;")
        self.start_button.clicked.connect(self.start_processing)
        config_layout.addWidget(self.start_button, 13, 1, 1, 2) # Place below checkbox

        # --- 调整行号到 14 ---
        # 导出纯净草稿按钮
        self.export_json_button = QPushButton("导出纯净草稿为 Zip")
        self.export_json_button.setFixedHeight(30) # Standard height
        self.export_json_button.clicked.connect(self.export_draft_json)
        config_layout.addWidget(self.export_json_button, 14, 1, 1, 2) 

        # 设置列伸展，让输入框占据更多空间
        config_layout.setColumnStretch(1, 1)

        main_layout.addLayout(config_layout)
        main_layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        # --- 日志区域 ---
        log_label = QLabel("处理日志 (详细日志请查看 logs/batch_tool.log):")
        main_layout.addWidget(log_label)
        self.log_text_edit = QPlainTextEdit()
        self.log_text_edit.setReadOnly(True)
        self.log_text_edit.setStyleSheet("background-color: #f0f0f0;") # Light gray background
        main_layout.addWidget(self.log_text_edit)

    def select_folder(self, line_edit_widget):
        """通用函数：打开文件夹选择对话框并更新 QLineEdit"""
        current_path = line_edit_widget.text()
        if not current_path or not os.path.isdir(current_path):
             # 如果当前路径无效或为空，尝试获取用户目录
             current_path = os.path.expanduser("~")

        folder_path = QFileDialog.getExistingDirectory(
            self,
            "选择文件夹",
            current_path
        )
        if folder_path: # 如果用户选择了文件夹而不是取消
            line_edit_widget.setText(folder_path)

    def select_input_folder(self):
        self.select_folder(self.input_entry)

    def select_output_folder(self):
        self.select_folder(self.output_entry)

    def select_draft_folder(self):
        self.select_folder(self.draft_folder_entry)

    def load_initial_config(self):
        """加载初始配置并更新 UI"""
        if load_config:
            self.config_data = load_config()
            self.input_entry.setText(self.config_data.get('Paths', {}).get('InputFolder', ''))
            self.output_entry.setText(self.config_data.get('Paths', {}).get('OutputFolder', ''))
            self.draft_folder_entry.setText(self.config_data.get('Paths', {}).get('DraftFolder', ''))
            self.draft_name_entry.setText(self.config_data.get('Settings', {}).get('DraftName', ''))
            
            # 新增：加载处理模式配置
            process_mode = self.config_data.get('Settings', {}).get('ProcessMode', 'split')
            if process_mode == 'merge':
                self.merge_mode_radio.setChecked(True)
            else:
                self.split_mode_radio.setChecked(True)
            
            # 新增：加载分割段数配置
            self.num_segments_entry.setText(str(self.config_data.get('Settings', {}).get('NumSegments', 1))) # 默认为 1
            
            # 新增：加载目标生成视频数量配置
            self.target_videos_count_entry.setText(str(self.config_data.get('Settings', {}).get('TargetVideosCount', 1))) # 默认为 1
            
            # 新增：加载按子目录处理配置
            process_by_subfolder = self.config_data.get('Settings', {}).get('ProcessBySubfolder', False)
            self.process_by_subfolder_check.setChecked(process_by_subfolder)
            
            # 新增：加载每个子目录处理视频数量配置
            videos_per_subfolder = self.config_data.get('Settings', {}).get('VideosPerSubfolder', 0)
            self.videos_per_subfolder_entry.setText(str(videos_per_subfolder))
            
            # 新增：加载BGM音量配置
            bgm_volume = self.config_data.get('Settings', {}).get('BGMVolume', 100)
            self.bgm_volume_slider.setValue(bgm_volume)
            self.update_volume_label(bgm_volume)
            
            # 新增：加载主轨道音量配置
            main_volume = self.config_data.get('Settings', {}).get('MainTrackVolume', 100)
            self.main_volume_slider.setValue(main_volume)
            self.update_main_volume_label(main_volume)

            # --- 修改: 明确处理 DeleteSource ---
            # 1. 尝试从配置中读取 Settings 部分
            settings = self.config_data.get('Settings', {})
            # 2. 检查 DeleteSource键是否存在
            if 'DeleteSource' in settings:
                # 如果存在，使用配置文件中的值
                delete_src = settings['DeleteSource']
                logger.info(f"从配置文件加载 DeleteSource: {delete_src}")
            else:
                # 如果不存在，设置默认值为 True (勾选)
                delete_src = True 
                logger.info("配置文件中未找到 DeleteSource，默认设置为 True")
            
            # 3. 确保转换为布尔值并更新复选框状态
            try:
                # 尝试更健壮地转换常见表示 False 的字符串
                if isinstance(delete_src, str) and delete_src.lower() in ('false', '0', 'no', 'off'):
                    checked_state = False
                else:
                    checked_state = bool(delete_src) # 其他情况（包括True, 1, 'true'等及非字符串）按bool处理
                self.delete_source_check.setChecked(checked_state)
            except Exception as e:
                 logger.error(f"转换 DeleteSource ('{delete_src}') 为布尔值时出错: {e}，将默认为 True")
                 self.delete_source_check.setChecked(True) # 出错时保险起见，默认为 True
            # --- 结束修改 ---
            
            # --- 新增: 加载 KeepBGM 配置 ---
            if 'KeepBGM' in settings:
                keep_bgm = settings['KeepBGM']
                logger.info(f"从配置文件加载 KeepBGM: {keep_bgm}")
            else:
                keep_bgm = True  # 默认保留BGM
                logger.info("配置文件中未找到 KeepBGM，默认设置为 True")
            
            try:
                if isinstance(keep_bgm, str) and keep_bgm.lower() in ('false', '0', 'no', 'off'):
                    checked_state = False
                else:
                    checked_state = bool(keep_bgm)
                self.keep_bgm_check.setChecked(checked_state)
            except Exception as e:
                logger.error(f"转换 KeepBGM ('{keep_bgm}') 为布尔值时出错: {e}，将默认为 True")
                self.keep_bgm_check.setChecked(True)
            # --- 结束新增 ---

            # 新增：加载上次选择的模板列表
            self.selected_templates = self.config_data.get('Templates', {}).get('SelectedTemplates', [])
            logger.info(f"从配置加载了 {len(self.selected_templates)} 个上次选择的模板")

            logger.info("UI 已从配置文件更新。")
        else:
            logger.error("配置加载函数未找到，无法加载初始配置。")
            QMessageBox.warning(self, "配置错误", "无法加载配置加载函数 (app/config.py)。")

    def save_current_config(self):
        """从 UI 获取当前值并保存配置"""
        if save_config:
            if 'Paths' not in self.config_data: self.config_data['Paths'] = {}
            if 'Settings' not in self.config_data: self.config_data['Settings'] = {}
            if 'Templates' not in self.config_data: self.config_data['Templates'] = {}

            self.config_data['Paths']['InputFolder'] = self.input_entry.text()
            self.config_data['Paths']['OutputFolder'] = self.output_entry.text()
            self.config_data['Paths']['DraftFolder'] = self.draft_folder_entry.text()
            self.config_data['Settings']['DraftName'] = self.draft_name_entry.text()
            self.config_data['Settings']['DeleteSource'] = self.delete_source_check.isChecked()
            # 新增：保存是否使用BGM配置
            self.config_data['Settings']['KeepBGM'] = self.keep_bgm_check.isChecked()
            # 新增：保存BGM音量配置
            self.config_data['Settings']['BGMVolume'] = self.bgm_volume_slider.value()
            # 新增：保存主轨道音量配置
            self.config_data['Settings']['MainTrackVolume'] = self.main_volume_slider.value()
            # 新增：保存处理模式
            self.config_data['Settings']['ProcessMode'] = "split" if self.split_mode_radio.isChecked() else "merge"
            # 新增：保存分割段数配置
            try:
                num_segments = int(self.num_segments_entry.text().strip())
                if num_segments <= 0:
                    logger.warning(f"无效的分割段数 '{self.num_segments_entry.text().strip()}', 将保存为 1")
                    num_segments = 1
            except ValueError:
                logger.warning(f"无法将分割段数 '{self.num_segments_entry.text().strip()}' 解析为整数，将保存为 1")
                num_segments = 1
            self.config_data['Settings']['NumSegments'] = num_segments

            # 新增：保存目标生成视频数量配置
            try:
                target_videos_count = int(self.target_videos_count_entry.text().strip())
                if target_videos_count <= 0:
                    logger.warning(f"无效的目标生成视频数量 '{self.target_videos_count_entry.text().strip()}', 将保存为 1")
                    target_videos_count = 1
            except ValueError:
                logger.warning(f"无法将目标生成视频数量 '{self.target_videos_count_entry.text().strip()}' 解析为整数，将保存为 1")
                target_videos_count = 1
            self.config_data['Settings']['TargetVideosCount'] = target_videos_count
            
            # 新增：保存按子目录处理配置
            self.config_data['Settings']['ProcessBySubfolder'] = self.process_by_subfolder_check.isChecked()
            
            # 新增：保存每个子目录处理视频数量配置
            try:
                videos_per_subfolder = int(self.videos_per_subfolder_entry.text().strip() or "0")
                if videos_per_subfolder < 0:
                    logger.warning(f"无效的每个子目录处理视频数量 '{self.videos_per_subfolder_entry.text().strip()}', 将保存为 0")
                    videos_per_subfolder = 0
            except ValueError:
                logger.warning(f"无法将每个子目录处理视频数量 '{self.videos_per_subfolder_entry.text().strip()}' 解析为整数，将保存为 0")
                videos_per_subfolder = 0
            self.config_data['Settings']['VideosPerSubfolder'] = videos_per_subfolder

            # 新增：保存选择的模板列表
            self.config_data['Templates']['SelectedTemplates'] = self.selected_templates

            save_config(self.config_data)
        else:
            logger.error("配置保存函数未找到，无法保存配置。")
            # 不需要在关闭时弹窗，日志已记录

    def setup_log_polling(self):
        """设置定时器以轮询日志队列并更新 UI"""
        self.log_timer.timeout.connect(self.process_log_queue)
        self.log_timer.start(100) # 每 100 毫秒检查一次队列

    def process_log_queue(self):
        """从队列中获取日志消息并添加到日志区域"""
        try:
            while True: # 处理队列中的所有当前消息
                record = log_queue.get_nowait()
                self.log_text_edit.appendPlainText(record) # 追加文本
                # log_queue.task_done() # 对于简单的 Queue，task_done 不是必需的
        except queue.Empty:
            pass # 队列为空时不做任何事
        except Exception as e:
             print(f"Error processing log queue: {e}") # 打印到控制台以防 UI 卡死
             logger.error(f"处理日志队列时出错: {e}", exc_info=True)

    def start_processing(self):
        """开始处理任务：验证输入、创建Worker、启动线程"""
        # 检查依赖
        if run_individual_video_processing is None:
            QMessageBox.critical(self, "依赖错误", "核心处理函数未加载。无法执行任务。")
            return
        
        # 检查当前状态
        if self.worker_thread is not None and self.worker_thread.isRunning():
            QMessageBox.warning(self, "任务进行中", "已有任务正在处理中，请等待当前任务完成。")
            return

        # 获取并验证输入
        input_folder = self.input_entry.text().strip()
        output_folder = self.output_entry.text().strip()
        draft_folder_path = self.draft_folder_entry.text().strip()
        
        # --- 修改：处理随机模板选择 ---
        selected_templates = self.get_selected_templates()
        self.selected_templates = selected_templates  # 保存当前选择，用于下次刷新时恢复勾选状态
        
        # 如果有选择模板，从中随机选择一个；否则使用手动输入的模板名
        draft_name = self.draft_name_entry.text().strip()
        final_template = draft_name
        
        if selected_templates:
            final_template = random.choice(selected_templates)
            logger.info(f"从 {len(selected_templates)} 个选中的模板中随机选择: {final_template}")
        else:
            # 如果没有选择随机模板，检查是否输入了模板名称
            if not draft_name:
                QMessageBox.critical(self, "错误", "请输入目标草稿名称或选择至少一个随机模板！")
                return
            logger.info(f"使用手动指定的模板: {final_template}")
        
        # 获取其他选项
        delete_source = self.delete_source_check.isChecked()
        keep_bgm = self.keep_bgm_check.isChecked()
        bgm_volume = self.bgm_volume_slider.value()
        main_track_volume = self.main_volume_slider.value()
        
        # 获取处理模式
        process_mode = "split" if self.split_mode_radio.isChecked() else "merge"
        
        # 获取段数
        num_segments_text = self.num_segments_entry.text().strip()
        if not num_segments_text:
            num_segments = 1 if process_mode == "split" else 0  # 默认值
        else:
            try:
                num_segments = int(num_segments_text)
                if num_segments < 1:
                    QMessageBox.warning(self, "输入错误", f"替换素材段数必须大于0。")
                    return
            except ValueError:
                QMessageBox.warning(self, "输入错误", f"替换素材段数必须是整数。")
                return
                
        # 获取目标生成视频数量
        target_videos_count_text = self.target_videos_count_entry.text().strip()
        if not target_videos_count_text:
            target_videos_count = 1  # 默认值
        else:
            try:
                target_videos_count = int(target_videos_count_text)
                if target_videos_count < 1:
                    QMessageBox.warning(self, "输入错误", f"目标生成视频数量必须大于0。")
                    return
            except ValueError:
                QMessageBox.warning(self, "输入错误", f"目标生成视频数量必须是整数。")
                return
        
        # 获取是否按子目录处理
        process_by_subfolder = self.process_by_subfolder_check.isChecked()
        
        # 获取每个子目录处理视频数量
        videos_per_subfolder_text = self.videos_per_subfolder_entry.text().strip()
        if not videos_per_subfolder_text:
            videos_per_subfolder = 0  # 默认值，表示不限制
        else:
            try:
                videos_per_subfolder = int(videos_per_subfolder_text)
                if videos_per_subfolder < 0:
                    QMessageBox.warning(self, "输入错误", f"每个子目录处理视频数量不能为负数。")
                    return
            except ValueError:
                QMessageBox.warning(self, "输入错误", f"每个子目录处理视频数量必须是整数。")
                return

        # --- 验证输入 --- 
        if not input_folder or not os.path.isdir(input_folder):
            QMessageBox.critical(self, "错误", "请选择有效的输入文件夹！")
            return
        if not output_folder:
             QMessageBox.critical(self, "错误", "请指定输出文件夹！")
             return
        # 尝试创建输出文件夹 (提前检查)
        try:
            os.makedirs(output_folder, exist_ok=True)
        except Exception as e:
            logger.exception(f"无法创建输出文件夹: {output_folder}")
            QMessageBox.critical(self, "错误", f"无法创建输出文件夹 '{output_folder}':\n{e}")
            return
        if not draft_folder_path or not os.path.isdir(draft_folder_path):
            QMessageBox.critical(self, "错误", "请提供有效的剪映草稿库路径！")
            return
        if not draft_name:
            QMessageBox.critical(self, "错误", "请输入目标草稿名称！")
            return

        # --- 准备并启动后台线程 --- 
        self.start_button.setEnabled(False)
        process_mode_text = "分割素材后替换" if process_mode == "split" else "直接素材替换"
        self.start_button.setText(f"{process_mode_text}处理中...")
        self.log_text_edit.clear() # 清空上次日志
        
        # 修改初始日志，包含模板信息
        if selected_templates:
            self.log_text_edit.appendPlainText(f"开始{process_mode_text}处理，使用随机选择的模板: {final_template}") 
        else:
            self.log_text_edit.appendPlainText(f"开始{process_mode_text}处理，使用指定的模板: {final_template}")
        
        QApplication.processEvents() # 确保 UI 更新

        logging.info("准备启动后台视频处理...")
        logging.info(f"  输入文件夹: {input_folder}")
        logging.info(f"  输出文件夹: {output_folder}")
        logging.info(f"  草稿库路径: {draft_folder_path}")
        
        # 添加模板选择信息到日志
        if selected_templates:
            logging.info(f"  选择了 {len(selected_templates)} 个模板")
            logging.info(f"  随机选择的模板: {final_template}")
        else:
            logging.info(f"  使用指定模板: {final_template}")
            
        logging.info(f"  处理后删除源文件: {'是' if delete_source else '否'}")
        logging.info(f"  处理模式: {process_mode_text}")
        logging.info(f"  替换素材段数: {num_segments}")
        logging.info(f"  目标生成视频数量: {target_videos_count}")
        logging.info(f"  使用模板BGM: {'是' if keep_bgm else '否'}")
        logging.info(f"  BGM音量: {bgm_volume}%")  # 记录BGM音量设置
        logging.info(f"  主轨道音量: {main_track_volume}%")  # 记录主轨道音量设置
        logging.info(f"  按子目录循环处理: {'是' if process_by_subfolder else '否'}")
        logging.info(f"  每个子目录处理视频数量: {videos_per_subfolder if videos_per_subfolder > 0 else '不限制'}")

        # 创建worker - 使用随机或指定的模板名称
        self.processing_worker = ProcessingWorker(
            input_folder, 
            output_folder, 
            final_template,  # 使用最终确定的模板名称
            draft_folder_path, 
            delete_source, 
            num_segments,
            keep_bgm,
            bgm_volume,
            main_track_volume,
            process_mode,
            target_videos_count,
            process_by_subfolder,  # 新增：是否按子目录循环处理
            videos_per_subfolder,   # 新增：每个子目录处理视频数量
            selected_templates  # 新增：选择的模板列表，用于每个视频任务随机选择
        )
        self.worker_thread = QThread(self) # Pass parent to help with lifetime management
        self.processing_worker.moveToThread(self.worker_thread)

        # 连接信号槽
        self.processing_worker.signals.finished.connect(self.on_processing_finished)
        # 连接线程生命周期管理
        self.worker_thread.started.connect(self.processing_worker.run)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater) # 请求删除线程对象
        self.processing_worker.signals.finished.connect(self.worker_thread.quit) # 请求线程退出事件循环
        # 请求删除 worker 对象，应该在线程结束后进行，可以连接到 finished 信号
        self.worker_thread.finished.connect(self.processing_worker.deleteLater)

        # 启动线程
        self.worker_thread.start()
        logging.info("后台处理线程已启动。")

    def on_processing_finished(self, success, message):
        """后台任务完成时的处理"""
        logger.info(f"后台任务完成信号接收: success={success}, message='{message}'")
        self.start_button.setEnabled(True)
        # 更新按钮文字为当前模式
        self.update_button_text()

        # 根据成功状态和消息内容显示不同的弹窗
        if success:
            # 即使成功，消息也可能包含警告或"未找到任务"等信息
            QMessageBox.information(self, "处理完成", 
                                      message + "\n\n请查看UI日志和 logs/batch_tool.log 获取详细信息。")
        else:
            QMessageBox.critical(self, "处理失败", 
                                   "处理过程中发生错误。\n" + message + "\n\n请检查UI日志和 logs/batch_tool.log 获取详细信息。")

        # 清理引用 (线程和 worker 会通过 deleteLater 自行清理)
        self.worker_thread = None
        self.processing_worker = None
        logger.info("处理完成，UI已更新。")

    def closeEvent(self, event):
        """重写关闭事件处理程序"""
        logger.info("应用程序正在关闭...")
        
        # 尝试停止后台线程（如果仍在运行）
        force_quit = False
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(self, '确认退出',
                                           "素材处理仍在后台运行，确定要强制退出吗？\n（后台处理将被尝试终止，可能导致数据不一致）",
                                           QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                           QMessageBox.StandardButton.No)

            if reply == QMessageBox.StandardButton.Yes:
                logger.warning("用户选择在处理过程中强制退出，尝试终止后台任务...")
                if self.processing_worker:
                    self.processing_worker.cancel() # 尝试标记取消
                self.worker_thread.quit() # 请求退出事件循环
                if not self.worker_thread.wait(1000): # 等待最多1秒
                     logger.warning("后台线程未能及时停止。应用程序将强制退出。")
                force_quit = True
                event.accept() # 接受关闭事件
            else:
                event.ignore() # 忽略关闭事件，保持窗口打开
                return # 不执行后续的保存和停止操作
        else:
            force_quit = True # 没有任务在运行，可以安全退出
            event.accept() # 没有后台任务，正常接受关闭

        if force_quit:
            # 只有在确认可以退出时才保存配置和停止定时器
            self.save_current_config() # 保存配置
            self.log_timer.stop() # 停止日志轮询定时器
            logger.info("配置已保存，日志轮询已停止。应用程序退出。")
            super().closeEvent(event) # 调用父类方法执行实际关闭

    # --- 新增：导出纯净草稿 JSON 的槽函数 --- 
    def export_draft_json(self):
        """处理"导出纯净草稿为 Zip"按钮点击事件"""
        logger.info("'导出纯净草稿为 Zip' 按钮被点击。")

        draft_folder = self.draft_folder_entry.text().strip()
        draft_name = self.draft_name_entry.text().strip()
        keep_bgm = self.keep_bgm_check.isChecked()  # 获取当前 KeepBGM 状态
        bgm_volume = self.bgm_volume_slider.value()  # 获取当前BGM音量值

        # 1. 验证输入
        if not draft_folder or not os.path.isdir(draft_folder):
            QMessageBox.warning(self, "输入错误", "请输入有效的剪映草稿库路径。")
            return
        if not draft_name:
            QMessageBox.warning(self, "输入错误", "请输入要导出的目标草稿名称。")
            return
        if export_clean_draft is None:
             QMessageBox.critical(self, "功能错误", "草稿导出功能未能正确加载。")
             return

        # 2. 弹出文件保存对话框
        default_filename = os.path.join(os.path.expanduser("~"), f"{draft_name}_clean.zip")
        export_path, _ = QFileDialog.getSaveFileName(
            self,
            "选择 Zip 导出路径",
            default_filename,
            "Zip 压缩包 (*.zip)"
        )

        # 3. 如果用户选择了路径，则调用核心函数
        if export_path:
            logger.info(f"用户选择导出 Zip 路径: {export_path}")
            try:
                # 调用核心导出函数，同时传递BGM音量参数
                logger.info(f"导出时设置BGM音量为: {bgm_volume}%")
                result = export_clean_draft(draft_folder, draft_name, export_path, 
                                           keep_bgm=keep_bgm,
                                           bgm_volume=bgm_volume)

                # 4. 显示结果消息框
                if result.get('success'):
                    QMessageBox.information(self, "导出成功", result.get('message', "操作成功完成。"))
                else:
                    QMessageBox.critical(self, "导出失败", result.get('message', "发生未知错误。"))
            except Exception as e:
                # 捕获调用 export_clean_draft 本身的意外错误
                logger.exception("调用 export_clean_draft 时发生意外错误")
                QMessageBox.critical(self, "导出异常", f"导出过程中发生意外错误: {e}")
        else:
            logger.info("用户取消了导出操作。")
    # ------------------------------------------

    def update_volume_label(self, value):
        """更新BGM音量标签显示"""
        self.bgm_volume_label.setText(f"{value}%")
        
    def update_main_volume_label(self, value):
        """更新主轨道音量标签显示"""
        self.main_volume_label.setText(f"{value}%")

    def update_segments_label(self):
        """根据选择的处理模式更新分割/融合段数标签"""
        if self.split_mode_radio.isChecked():
            self.segments_label.setText("替换素材段数:")
            self.num_segments_entry.setPlaceholderText("默认为 1 (不分割)")
        else:
            self.segments_label.setText("素材替换段数:")
            self.num_segments_entry.setPlaceholderText("默认为 1")
    
    def update_button_text(self):
        """根据选择的处理模式更新按钮文字"""
        if self.split_mode_radio.isChecked():
            self.start_button.setText("开始分割素材后替换处理")
        else:
            self.start_button.setText("开始直接素材替换处理")
            
    # --- 新增：模板相关方法 ---
    def refresh_templates(self):
        """刷新剪映草稿文件夹中的模板列表"""
        # 清除当前的模板复选框
        for checkbox in self.template_checkboxes.values():
            self.templates_container_layout.removeWidget(checkbox)
            checkbox.deleteLater()
        self.template_checkboxes.clear()
        
        # 获取草稿文件夹路径
        draft_folder = self.draft_folder_entry.text().strip()
        if not draft_folder or not os.path.isdir(draft_folder):
            QMessageBox.warning(self, "路径错误", "请输入有效的剪映草稿文件夹路径")
            return
        
        # 查找草稿文件夹中的所有草稿
        try:
            templates = self.get_draft_templates(draft_folder)
            if not templates:
                QMessageBox.information(self, "无结果", "在指定路径未找到剪映草稿文件夹")
                return
                
            # 添加复选框到滚动区域
            for template_name in sorted(templates):
                checkbox = QCheckBox(template_name)
                # 如果是上次选择的模板，默认勾选
                if template_name in self.selected_templates:
                    checkbox.setChecked(True)
                self.template_checkboxes[template_name] = checkbox
                # 在添加拉伸前插入
                self.templates_container_layout.insertWidget(
                    self.templates_container_layout.count() - 1, checkbox)
            
            # 添加一个标签显示模板数量
            template_count_label = QLabel(f"已加载 {len(templates)} 个模板")
            self.templates_container_layout.insertWidget(
                self.templates_container_layout.count() - 1, template_count_label)
                
            QMessageBox.information(self, "刷新成功", f"成功加载 {len(templates)} 个模板")
            
        except Exception as e:
            logger.exception("刷新模板列表时出错")
            QMessageBox.critical(self, "刷新失败", f"刷新模板列表时出错: {e}")
    
    def get_draft_templates(self, draft_folder):
        """获取剪映草稿文件夹中的所有草稿名称"""
        templates = []
        
        try:
            # 遍历草稿文件夹下的所有子文件夹
            for item in os.listdir(draft_folder):
                item_path = os.path.join(draft_folder, item)
                if os.path.isdir(item_path):
                    # 检查是否包含draft_content.json文件，这是剪映草稿的标志
                    if os.path.exists(os.path.join(item_path, "draft_content.json")):
                        templates.append(item)
        except Exception as e:
            logger.error(f"获取草稿模板列表时出错: {e}")
            raise
            
        return templates
    
    def select_all_templates(self):
        """选择所有模板"""
        for checkbox in self.template_checkboxes.values():
            checkbox.setChecked(True)
    
    def deselect_all_templates(self):
        """取消选择所有模板"""
        for checkbox in self.template_checkboxes.values():
            checkbox.setChecked(False)
    
    def get_selected_templates(self):
        """获取当前选中的模板列表"""
        selected = []
        for name, checkbox in self.template_checkboxes.items():
            if checkbox.isChecked():
                selected.append(name)
        return selected

# --- 用于直接运行测试 UI (可选) ---
# if __name__ == '__main__':
#     # 需要先配置日志
#     from ..util.logging_setup import setup_logging
#     test_log_queue = queue.Queue()
#     setup_logging(ui_queue=test_log_queue) # 配置日志以发送到队列
#
#     app = QApplication(sys.argv)
#     mainWin = MainWindow()
#     # 将测试队列传递给 MainWindow 以便它能处理日志
#     # (更好的方式是 MainWindow 自己管理队列或通过信号传递)
#     # 这里简化处理，假设 MainWindow 能访问 setup_logging 定义的 log_queue
#     mainWin.show()
#     sys.exit(app.exec()) 