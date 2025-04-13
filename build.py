import PyInstaller.__main__
import os
import sys
import platform
import shutil

# --- 配置 ---
APP_NAME = "JianYingBatchTool"  # 您可以修改最终生成的可执行文件名
ENTRY_POINT = os.path.join("app", "main.py") # 主程序入口文件
ICON_FILE = None # 例如: "path/to/your/icon.ico" 或设置为 None

# --- 清理旧的构建 ---
print("--- 正在清理旧的构建文件... ---")
DIST_FOLDER = 'dist'
BUILD_FOLDER = 'build'
SPEC_FILE = f"{APP_NAME}.spec"

if os.path.isdir(DIST_FOLDER):
    print(f"删除文件夹: {DIST_FOLDER}")
    shutil.rmtree(DIST_FOLDER)
if os.path.isdir(BUILD_FOLDER):
    print(f"删除文件夹: {BUILD_FOLDER}")
    shutil.rmtree(BUILD_FOLDER)
if os.path.isfile(SPEC_FILE):
    print(f"删除文件: {SPEC_FILE}")
    os.remove(SPEC_FILE)

print("清理完成.")

# --- 开始 PyInstaller 构建 ---
print("\n--- 正在启动 PyInstaller 构建... ---")

# 基本参数
pyinstaller_args = [
    '--name=%s' % APP_NAME,
    '--onefile',      # 打包成单个可执行文件
    '--windowed',     # GUI 应用，无控制台窗口
    # '--clean',      # PyInstaller 每次构建前清理缓存 (可选，我们已手动清理)
    '--noconfirm',    # 覆盖输出目录时不要求确认
    # '--log-level=INFO', # 设置日志级别 (DEBUG, INFO, WARN, ERROR, CRITICAL)
]

# 添加图标 (如果指定了)
if ICON_FILE and os.path.isfile(ICON_FILE):
    pyinstaller_args.append('--icon=%s' % ICON_FILE)
    print(f"使用图标: {ICON_FILE}")
else:
    print("未指定图标或图标文件不存在，将使用默认图标。")
    if ICON_FILE: # 如果指定了但文件不存在，给出警告
        print(f"警告: 指定的图标文件 '{ICON_FILE}' 不存在。")


# 添加隐藏导入 (帮助 PyInstaller 找到某些库)
# 这些是根据 requirements.txt 和常见问题添加的，可能需要根据实际错误调整
hidden_imports = [
    'PyQt6.sip',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'uiautomation',
    'pymediainfo', # 可能需要外部 MediaInfo.dll
    'ffmpeg',      # 包装器需要系统安装 ffmpeg
    'DrissionPage',
    'logging.handlers', # 用于 QueueHandler
    'queue',
    'multiprocessing', # main.py 中调用了 freeze_support
    'pkg_resources.py2_warn', # 常见问题修复
    # 明确添加应用子模块，有时有助于 PyInstaller 发现
    'app.core.orchestrator',
    'app.config',
    'app.util.logging_setup',
    'app.ui.main_window',
    # 如果运行时报告缺少其他模块，请添加到这里
]
for imp in hidden_imports:
    pyinstaller_args.append('--hidden-import=%s' % imp)

print(f"包含的隐藏导入: {', '.join(hidden_imports)}")

# 添加数据文件 (例如 JSON 模板)
data_files = [
    # (源文件路径, 打包后的目标目录)
    ('pyJianYingDraft/draft_content_template.json', 'pyJianYingDraft') 
]

# 根据操作系统使用正确的分隔符 (Windows用';', Linux/macOS用':')
data_separator = ';' if platform.system() == "Windows" else ':'
binary_separator = ';' if platform.system() == "Windows" else ':' # 二进制文件也需要分隔符

for src, dest in data_files:
    if os.path.exists(src):
        pyinstaller_args.append(f'--add-data={os.path.abspath(src)}{data_separator}{dest}')
        print(f"添加数据文件: {src} -> {dest}")
    else:
        print(f"警告: 要添加的数据文件 '{src}' 未找到，跳过此文件。")

# 添加二进制文件 (例如 ffmpeg)
binary_files = [
    ('app/ffmpeg.exe', '.'), # (源文件路径, 打包后的目标目录, '.' 表示根目录)
    ('app/ffprobe.exe', '.')
]

for src, dest in binary_files:
    if os.path.isfile(src):
        # 确保目标目录存在于 PyInstaller 参数中
        pyinstaller_args.append(f'--add-binary={os.path.abspath(src)}{binary_separator}{dest}')
        print(f"添加二进制文件: {src} -> {dest}")
    else:
        print(f"警告: 要添加的二进制文件 '{src}' 未找到，跳过此文件。")

# 平台特定的调整 (例如添加 DLL 或数据文件)
# if platform.system() == "Windows":
#     # 例如: 添加 MediaInfo.dll 到可执行文件目录
#     # mediainfo_dll_path = "path/to/MediaInfo.dll"
#     # if os.path.isfile(mediainfo_dll_path):
#     #     pyinstaller_args.append(f'--add-binary={os.path.abspath(mediainfo_dll_path)};.')
#     # else:
#     #     print("警告: 未找到 MediaInfo.dll，pymediainfo 可能无法工作。")
#     pass
# elif platform.system() == "Darwin": # macOS
#     pass
# elif platform.system() == "Linux":
#     pass

# 添加主程序入口点
pyinstaller_args.append(ENTRY_POINT)

print(f"将使用以下参数运行 PyInstaller: {' '.join(pyinstaller_args)}")

# --- 执行 PyInstaller ---
try:
    PyInstaller.__main__.run(pyinstaller_args)
    print("\n--- PyInstaller 构建成功完成 ---")
    print(f"可执行文件应该位于 '{DIST_FOLDER}' 文件夹中。")

    # --- 重要提醒 ---
    print("\n--- 重要提醒 ---")
    print("1. ffmpeg 和 ffprobe: 这两个工具已尝试打包进可执行文件。如果遇到问题，请确保它们位于可执行文件同目录下或系统 PATH 中。")
    # print("1. 运行时依赖: 请确保运行可执行文件的系统上安装了 'ffmpeg' 并已添加到系统 PATH 环境变量中。") # Bundled now
    print("2. pymediainfo: 如果使用了 'pymediainfo' 且遇到问题，可能需要将 'MediaInfo.dll' (或其他平台的相应库文件) 放置在生成的可执行文件旁边。")
    # print("2. 运行时依赖: 如果使用了 'pymediainfo'，可能需要将 'MediaInfo.dll' (或其他平台的相应库文件) 放置在生成的可执行文件旁边。")
    print("3. 测试: 请在干净的环境中（没有安装 Python 或项目依赖的环境）彻底测试生成的可执行文件，以确保所有功能正常并捕获任何运行时错误。")

except Exception as e:
    print("\n--- PyInstaller 构建失败 ---", file=sys.stderr)
    print(f"错误: {e}", file=sys.stderr)
    sys.exit(1) # 以错误码退出

sys.exit(0) # 正常退出 