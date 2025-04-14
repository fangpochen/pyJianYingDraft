# app/core/draft_exporter.py
import os
import json
import shutil
import logging

logger = logging.getLogger(__name__)

def export_clean_draft(jianying_drafts_folder: str, draft_name: str, export_zip_path: str, keep_bgm: bool = True) -> dict:
    """导出指定草稿的整个文件夹为 Zip 压缩包，但前提是其中不包含复合片段。

    Args:
        jianying_drafts_folder: 剪映草稿库的根文件夹路径。
        draft_name: 要导出的草稿在剪映中显示的名称。
        export_zip_path: 导出的 .zip 文件应保存的完整路径。
        keep_bgm: 是否保留草稿中的BGM音频轨道，默认为True。

    Returns:
        一个字典，包含 'success' (bool) 和 'message' (str)。
    """
    logger.info(f"请求导出纯净草稿文件夹为 Zip: '{draft_name}' 从 '{jianying_drafts_folder}' 到 '{export_zip_path}'")
    logger.info(f"保留BGM设置: {keep_bgm}")

    draft_folder_path = os.path.join(jianying_drafts_folder, draft_name)
    source_json_path = os.path.join(draft_folder_path, 'draft_content.json')

    # 1. 检查草稿文件夹和 JSON 文件是否存在 (JSON 文件存在性也间接确认文件夹基本有效)
    if not os.path.isdir(draft_folder_path):
        msg = f"错误：未找到名为 '{draft_name}' 的草稿文件夹于 '{jianying_drafts_folder}'"
        logger.error(msg)
        return {'success': False, 'message': msg}
    if not os.path.isfile(source_json_path):
        # 虽然我们要打包整个文件夹，但 draft_content.json 的存在是草稿有效性的基本标志
        msg = f"错误：在草稿文件夹 '{draft_folder_path}' 中未找到 draft_content.json 文件。无法确认是否为有效草稿。"
        logger.error(msg)
        return {'success': False, 'message': msg}

    logger.info(f"找到源草稿文件夹: {draft_folder_path}")

    try:
        # 2. 读取并解析 JSON 文件以检查复合片段
        with open(source_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info("draft_content.json 文件读取并解析成功。")

        # 3. 检查是否存在复合片段 ('combination')
        has_combination = False
        materials = data.get('materials', {})
        draft_materials = materials.get('drafts', [])

        if isinstance(draft_materials, list):
            for item in draft_materials:
                if isinstance(item, dict) and item.get('type') == 'combination':
                    has_combination = True
                    logger.warning(f"检测到复合片段 (combination): id={item.get('id', 'N/A')}")
                    break
        else:
            logger.warning("JSON 结构异常：'materials.drafts' 不是一个列表。跳过复合片段检查。")

        # 4. 如果不保留BGM，移除所有BGM轨道
        if not keep_bgm:
            logger.info("根据设置，将移除BGM轨道...")
            try:
                # 获取轨道信息
                tracks = data.get('tracks', [])
                audio_tracks = [track for track in tracks if track.get('type') == 'audio']
                bgm_tracks = []
                
                # 查找所有可能是BGM的轨道
                for track in audio_tracks:
                    track_name = track.get('name', '').lower()
                    # 通过轨道名称判断是否为BGM轨道
                    if any(keyword in track_name for keyword in ['bgm', '音乐', 'music']):
                        bgm_tracks.append(track)
                        logger.info(f"找到可能的BGM轨道: {track.get('name')} (id: {track.get('id')})")
                
                # 移除BGM轨道
                if bgm_tracks:
                    for bgm_track in bgm_tracks:
                        tracks.remove(bgm_track)
                        logger.info(f"已移除BGM轨道: {bgm_track.get('name')}")
                    
                    # 更新JSON数据中的轨道列表
                    data['tracks'] = tracks
                    
                    # 写回JSON文件
                    with open(source_json_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False)
                    logger.info("更新后的JSON已写回文件")
                else:
                    logger.info("未找到BGM轨道，无需移除")
            except Exception as e:
                logger.warning(f"移除BGM轨道过程中出错: {e}")
                # 继续执行，不因为BGM处理失败而中断整个流程

        # 5. 根据检查结果决定是否导出
        if has_combination:
            msg = f"导出失败：草稿 '{draft_name}' 包含复合片段 (combination)，不支持导出。"
            logger.error(msg)
            return {'success': False, 'message': msg}
        else:
            logger.info("未检测到复合片段，准备压缩草稿文件夹...")
            # 6. 压缩整个草稿文件夹
            try:
                # shutil.make_archive 需要目标路径（不含扩展名）和格式
                # 我们先获取用户指定的 zip 路径的目录和不带扩展名的基本名称
                archive_base_path = os.path.splitext(export_zip_path)[0]
                archive_format = 'zip'

                # 执行压缩：(目标基本路径, 格式, 源文件夹路径)
                result_path = shutil.make_archive(archive_base_path, archive_format, draft_folder_path)
                
                # 检查结果路径是否与预期一致 (shutil 会自动添加 .zip)
                if os.path.abspath(result_path) == os.path.abspath(export_zip_path):
                    msg = f"成功将纯净草稿 '{draft_name}' 文件夹导出为 Zip 压缩包到:\n{export_zip_path}"
                    if not keep_bgm:
                        msg += "\n注意：已移除BGM轨道"
                    logger.info(msg)
                    return {'success': True, 'message': msg}
                else:
                    # 理论上不应发生，除非路径处理或 make_archive 行为异常
                    msg = f"警告：压缩完成，但最终路径 '{result_path}' 与预期 '{export_zip_path}' 不符。请检查文件。"
                    logger.warning(msg)
                    # 仍然认为是成功，但给出警告
                    return {'success': True, 'message': msg + "\n(路径不符警告)"}

            except Exception as zip_err:
                msg = f"错误：压缩草稿文件夹时出错: {zip_err}"
                logger.exception(msg)
                return {'success': False, 'message': msg}

    except json.JSONDecodeError as json_err:
        msg = f"错误：解析 JSON 文件 '{source_json_path}' 时失败: {json_err}"
        logger.exception(msg)
        return {'success': False, 'message': msg}
    except IOError as io_err:
        msg = f"错误：读取 JSON 文件 '{source_json_path}' 时发生 IO 错误: {io_err}"
        logger.exception(msg)
        return {'success': False, 'message': msg}
    except Exception as e:
        msg = f"导出过程中发生未知错误: {e}"
        logger.exception(msg)
        return {'success': False, 'message': msg}

# 可选：添加一个简单的命令行测试入口
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    # --- 请修改以下路径进行测试 --- 
    test_drafts_folder = r"D:\DJianYingDrafts\JianyingPro Drafts" # 修改为你的草稿库路径
    test_draft_name_clean = "test"  # 修改为一个不含复合片段的草稿名
    test_draft_name_combo = "含有复合片段的草稿名" # 修改为一个含有复合片段的草稿名
    test_export_path_clean = r"./test_clean_export.zip" # <--- 改为 .zip
    test_export_path_combo = r"./test_combo_export.zip" # <--- 改为 .zip

    print("\n--- 测试导出无复合片段的草稿为 Zip ---")
    result_clean = export_clean_draft(test_drafts_folder, test_draft_name_clean, test_export_path_clean, keep_bgm=True)
    print(f"结果: {result_clean}")
    if result_clean['success']:
        print(f"检查 Zip 文件是否存在: {os.path.exists(test_export_path_clean)}")

    print("\n--- 测试导出含复合片段的草稿为 Zip --- ")
    result_combo = export_clean_draft(test_drafts_folder, test_draft_name_combo, test_export_path_combo, keep_bgm=True)
    print(f"结果: {result_combo}")
    if not result_combo['success']:
        print(f"检查 Zip 文件是否未生成 (预期): {not os.path.exists(test_export_path_combo)}") 