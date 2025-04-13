# 导入模块
import os
import platform
# 导入批量导出功能所需的模块
# 注意：我们不再需要导入 pyJianYingDraft 的其他部分，因为不加载草稿了
from pyJianYingDraft import Jianying_controller, Export_resolution, Export_framerate

print("--- 剪映草稿导出脚本 --- (仅限 Windows, 剪映 <= 6.x)")

# --- 添加批量导出逻辑 ---
if platform.system() == "Windows":
    try:
        print("正在初始化剪映控制器... 请确保剪映已打开并位于主目录页。")
        ctrl = Jianying_controller()

        # --- 配置导出参数 --- 
        # !! 重要：请将下方草稿名称替换为剪映中显示的实际草稿名称
        draft_name_to_export = "<请替换为剪映中的草稿名称>" # 例如: "我的项目草稿"
        # !! 重要：请将下方路径替换为您希望导出视频的目标文件路径或文件夹路径
        export_target_path = r"<请替换为导出视频的目标路径>" # 例如: r"C:\exports\my_video.mp4"

        print(f"准备导出草稿: '{draft_name_to_export}'")
        print(f"导出目标: '{export_target_path}'")
        print("导出过程将控制鼠标键盘，请勿操作电脑...")

        # 执行导出 (默认分辨率和帧率)
        # ctrl.export_draft(draft_name_to_export, export_target_path)

        # 执行导出 (指定1080P分辨率, 24帧率)
        ctrl.export_draft(draft_name_to_export, export_target_path,
                          resolution=Export_resolution.RES_1080P,
                          framerate=Export_framerate.FR_24)

        print(f"草稿 '{draft_name_to_export}' 导出任务已启动。")
        # 注意：此函数调用后脚本可能立即结束，但剪映的导出过程仍在后台进行。
        # pyJianYingDraft 可能不包含等待导出完成的机制。

    except ImportError:
        print("错误: 导出功能所需的 uiautomation 库未能导入。")
        print("请确保已正确安装，并使用兼容的 Python 版本 (如 3.8, 3.10, 3.11)。")
    except Exception as e:
        print(f"导出过程中发生错误: {e}")
        print("请检查：")
        print("  1. 剪映是否已打开并停留在主目录页？")
        print("  2. 剪映版本是否为 6.x 或更低版本？")
        print("  3. 是否有导出该草稿的权限？")
        print("  4. 草稿名称是否填写正确？")
        # 如果需要详细调试信息，可以取消注释下一行
        # import traceback; traceback.print_exc()
else:
    print("跳过导出步骤：此功能仅支持 Windows 系统。")

print("\n脚本执行完毕。")
