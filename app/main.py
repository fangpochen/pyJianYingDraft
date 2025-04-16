#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
剪映批量处理工具
主入口程序
"""

import sys
import os
import logging
from PyQt6.QtWidgets import QApplication

# 确保日志目录存在
os.makedirs('logs', exist_ok=True)

# 导入密钥验证模块
from app.ui.key_verification import verify_and_run

if __name__ == "__main__":
    try:
        sys.exit(verify_and_run())
    except Exception as e:
        # 记录未捕获的异常
        logging.error(f"程序启动失败: {e}", exc_info=True)
        sys.exit(1) 