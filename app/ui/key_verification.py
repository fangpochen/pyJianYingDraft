import sys
import os
import json
import logging
import platform
import uuid
import socket
import requests
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QLineEdit, QPushButton, QLabel, QMessageBox, QCheckBox, QDialog)
from PyQt6.QtCore import Qt

# 导入现有的主窗口
from .main_window import MainWindow

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/key_verification.log', encoding='utf-8', mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('key_verification')

def verify_key(api_key):
    """验证API密钥有效性"""
    try:
        # 获取系统信息
        hostname = socket.gethostname()
        os_info = f"{platform.system()} {platform.release()}"
        
        # 获取CPU信息
        try:
            import cpuinfo
            cpu_info = cpuinfo.get_cpu_info()['brand_raw']
        except:
            cpu_info = "Unknown CPU"
        
        # 获取MAC地址
        mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff)
                        for elements in range(0,2*6,2)][::-1])

        url = f"https://api.cloudoption.site/api/v1/api-keys/verify"
        headers = {"Content-Type": "application/json"}
        payload = {
            "key": api_key,
            "machine_info": {
                "hostname": hostname,
                "os": os_info,
                "cpu": cpu_info,
                "mac": mac,
                "item": "clip"
            }
        }

        logger.info(f"正在验证密钥: {api_key}")
        logger.debug(f"发送验证请求: {payload}")
        
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        logger.info(f"密钥验证结果: {result}")
        return result.get("valid", False)
    except ImportError as e:
        logger.error(f"导入模块失败: {e}")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"API请求异常: {e}")
        return False
    except Exception as e:
        logger.error(f"验证过程中发生异常: {e}")
        return False

class KeyVerificationDialog(QDialog):
    """密钥验证对话框"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle('剪映批量处理工具 - 密钥验证')
        self.setFixedSize(400, 200)
        self.init_ui()
        self.load_saved_key()
        
    def init_ui(self):
        """初始化用户界面"""
        layout = QVBoxLayout()
        
        # 添加说明标签
        label = QLabel('请输入您的授权密钥:')
        layout.addWidget(label)
        
        # 密钥输入框
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("输入授权密钥...")
        layout.addWidget(self.key_input)
        
        # 记住密钥选项
        self.remember_checkbox = QCheckBox('记住密钥')
        self.remember_checkbox.setChecked(True)
        layout.addWidget(self.remember_checkbox)
        
        # 验证按钮
        self.verify_button = QPushButton('验证')
        self.verify_button.clicked.connect(self.verify_and_proceed)
        self.verify_button.setStyleSheet("background-color: lightblue;")
        layout.addWidget(self.verify_button)
        
        # 设置默认按钮，按回车键可以触发
        self.verify_button.setDefault(True)
        
        # 添加联系信息
        info_label = QLabel('使用有问题请联系客服获取帮助')
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info_label)
        
        self.setLayout(layout)
        
    def load_saved_key(self):
        """加载已保存的密钥"""
        try:
            if os.path.exists('config/saved_key.json'):
                with open('config/saved_key.json', 'r') as f:
                    data = json.load(f)
                    self.key_input.setText(data.get('key', ''))
                    self.remember_checkbox.setChecked(True)
                    logger.info("已加载保存的密钥")
        except Exception as e:
            logger.error(f"加载保存的密钥时出错: {e}")
    
    def save_key(self, key):
        """保存密钥到文件"""
        try:
            # 确保目录存在
            os.makedirs('config', exist_ok=True)
            with open('config/saved_key.json', 'w') as f:
                json.dump({'key': key}, f)
            logger.info("密钥已保存")
        except Exception as e:
            logger.error(f"保存密钥时出错: {e}")
    
    def verify_and_proceed(self):
        """验证密钥并进入主程序"""
        key = self.key_input.text().strip()
        if not key:
            QMessageBox.warning(self, '错误', '请输入密钥')
            return
        
        # 禁用按钮，防止重复点击
        self.verify_button.setEnabled(False)
        self.verify_button.setText("验证中...")
        QApplication.processEvents()  # 刷新UI
        
        if verify_key(key):
            logger.info("密钥验证成功")
            if self.remember_checkbox.isChecked():
                self.save_key(key)
            else:
                # 如果取消记住密钥，删除保存的文件
                if os.path.exists('config/saved_key.json'):
                    os.remove('config/saved_key.json')
                    logger.info("已删除保存的密钥")
                    
            self.accept()  # 关闭对话框并返回接受结果
        else:
            logger.warning("密钥验证失败")
            QMessageBox.critical(self, '错误', '无效的密钥，请检查后重试')
            self.verify_button.setEnabled(True)
            self.verify_button.setText("验证")
    
    def closeEvent(self, event):
        """重写关闭事件"""
        # 如果是用户手动关闭窗口，退出程序
        logger.info("用户关闭了验证窗口")

def verify_and_run():
    """验证密钥并运行主程序"""
    app = QApplication(sys.argv)
    
    # 显示验证窗口
    verification_dialog = KeyVerificationDialog()
    if verification_dialog.exec() == QDialog.DialogCode.Accepted:
        # 验证成功，启动主窗口
        logger.info("验证通过，启动主程序")
        main_window = MainWindow()
        main_window.show()
        return app.exec()
    else:
        # 验证失败或用户关闭了验证窗口
        logger.info("验证未通过或用户取消，程序退出")
        return 1
    
if __name__ == '__main__':
    sys.exit(verify_and_run()) 