# app/ui/config_dialog.py
import os
import sys
import json
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt

logger = logging.getLogger(__name__)

class ConfigDialog(QDialog):
    """用于配置 Chrome 浏览器路径的对话框 (DrissionPage)"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Chrome 浏览器配置 (DrissionPage)')
        self.setFixedWidth(550)
        self.setModal(True) # 设置为模态对话框

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Chrome路径输入
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText('请输入 Chrome/Edge 浏览器可执行文件路径 (chrome.exe / msedge.exe)')
        browse_btn = QPushButton('浏览')
        browse_btn.clicked.connect(self.browse_chrome)
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(browse_btn)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch() # 将按钮推到右边
        save_btn = QPushButton('保存配置')
        save_btn.clicked.connect(self.save_drission_config)
        cancel_btn = QPushButton('取消')
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)

        # 添加到主布局
        layout.addLayout(path_layout)
        layout.addLayout(btn_layout)

        # 尝试加载现有 DrissionPage 配置
        self.load_existing_drission_config()

    def browse_chrome(self):
        # 允许选择 exe 文件
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Chrome/Edge 浏览器可执行文件",
            "C:/Program Files", # 默认打开目录
            "浏览器可执行文件 (*.exe)"
        )
        if file_path:
            self.path_input.setText(file_path.replace('/', '\\')) # 转换为 Windows 路径格式

    def load_existing_drission_config(self):
        """尝试加载 DrissionPage 的浏览器路径配置"""
        try:
            from DrissionPage import ChromiumOptions
            co = ChromiumOptions() # 加载默认配置
            browser_path = co.browser_path
            if browser_path:
                logger.info(f"从 DrissionPage 配置加载到浏览器路径: {browser_path}")
                self.path_input.setText(browser_path)
            else:
                logger.info("DrissionPage 配置文件中未找到浏览器路径。")
        except ImportError:
             logger.error("无法导入 DrissionPage，无法加载配置。")
        except Exception as e:
             logger.warning(f"加载 DrissionPage 配置时出错: {e}")

    def save_drission_config(self):
        """保存浏览器路径到 DrissionPage 的默认配置文件"""
        browser_path = self.path_input.text().strip()
        if not browser_path:
            QMessageBox.warning(self, '警告', '请输入浏览器可执行文件路径！')
            return

        # 简单验证路径
        if not os.path.exists(browser_path) or not os.path.isfile(browser_path) or not browser_path.lower().endswith(('.exe')):
            QMessageBox.warning(self, '警告', '指定的浏览器路径无效或不存在！\n请确保它指向一个 .exe 文件。 ')
            return

        try:
            from DrissionPage import ChromiumOptions
            co = ChromiumOptions() # 创建/加载默认配置对象
            co.set_browser_path(browser_path) # 设置路径
            config_save_path = co.save() # 保存到默认位置
            logger.info(f"浏览器路径已保存到 DrissionPage 配置文件: {config_save_path}")
            QMessageBox.information(self, '成功', f'浏览器路径已保存到:\n{config_save_path}')
            self.accept() # 关闭对话框并返回接受状态
        except ImportError:
            logger.error("无法导入 DrissionPage，保存配置失败。")
            QMessageBox.critical(self, '错误', '无法导入 DrissionPage 库，无法保存配置。')
        except Exception as e:
            logger.exception("保存 DrissionPage 配置时发生错误")
            QMessageBox.critical(self, '错误', f'保存配置失败：{str(e)}')

# --- 用于直接测试对话框 (可选) ---
# if __name__ == '__main__':
#     from PyQt6.QtWidgets import QApplication
#     logging.basicConfig(level=logging.INFO)
#     app = QApplication(sys.argv)
#     dialog = ConfigDialog()
#     if dialog.exec():
#         print("配置已保存")
#     else:
#         print("配置未保存")
#     sys.exit() 