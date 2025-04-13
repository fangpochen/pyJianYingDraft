# 导入模块
import pyJianYingDraft as draft
import os # 用于路径处理

print("--- 剪映模板加载与复制脚本 --- (注意: 可能仅支持剪映 <= 5.9)")

# --- 配置参数 ---
# !! 重要：请将下方路径替换为剪映实际的草稿根文件夹路径
#          可以在剪映的 全局设置 -> 草稿位置 中找到
jianying_drafts_path = r"D:\DJianYingDrafts\JianyingPro Drafts" # 例如: r"C:\Users\YourUser\Documents\JianyingPro Drafts"

# !! 重要：请将下方名称替换为您想要作为模板的、已存在的草稿名称
template_draft_name = "简单测试_4940" # 例如: "通用片头模板"

# !! 重要：请为新复制出来的草稿指定一个名称
new_draft_name = "test" # 例如: "项目A_基于模板"

# 检查草稿文件夹路径是否存在
if not os.path.isdir(jianying_drafts_path):
    print(f"错误: 剪映草稿文件夹路径不存在或无效: {jianying_drafts_path}")
    print("请在脚本中修改 jianying_drafts_path 变量。")
    exit()

print(f"使用剪映草稿文件夹: {jianying_drafts_path}")
print(f"模板草稿名称: {template_draft_name}")
print(f"新草稿名称: {new_draft_name}")

try:
    # 初始化 Draft_folder 对象
    draft_folder = draft.Draft_folder(jianying_drafts_path)

    print(f"\n尝试复制草稿 '{template_draft_name}' 为新草稿 '{new_draft_name}'...")
    # 复制模板草稿，并返回可编辑的 Script_file 对象
    # 注意：此操作会直接在您的剪映草稿文件夹中创建新草稿的文件夹和文件
    script = draft_folder.duplicate_as_template(template_draft_name, new_draft_name)

    print("模板复制成功，现在可以对 'script' 对象进行编辑。")

    # --- 在此处添加对 script 对象的编辑操作 --- 
    # 例如: 替换素材、修改文本、添加新轨道/片段等
    # script.replace_material_by_name(...) 
    # script.replace_text(...) 
    # new_track = script.add_track(...)
    # script.add_segment(..., track_name=new_track.name)
    # ------------------------------------------
    print("示例：此处未进行编辑操作。")

    # 保存对新草稿的修改
    print("\n正在保存新草稿...")
    script.save()
    print(f"新草稿 '{new_draft_name}' 已保存。")
    print("您可以尝试在剪映中打开这个新草稿进行查看。")

except FileNotFoundError:
    print(f"错误: 未在 '{jianying_drafts_path}' 中找到名为 '{template_draft_name}' 的草稿文件夹。")
    print("请确保模板草稿名称正确且草稿确实存在。")
except ImportError:
    print("错误: 未能导入 pyJianYingDraft 库。请确保已正确安装。")
except AttributeError as e:
    print(f"错误: 调用库功能时遇到属性错误 - {e}。")
    print("这可能表示库的版本、API 或草稿文件结构与预期不符。请检查库文档或剪映版本兼容性。")
    # print(f"Draft_folder type: {type(draft_folder)}")
    # print(f"Draft_folder methods: {dir(draft_folder)}")
except Exception as e:
    print(f"执行过程中发生未知错误: {e}")
    # 如果需要详细调试信息，可以取消注释下一行
    # import traceback; traceback.print_exc()

print("\n脚本执行完毕。") 