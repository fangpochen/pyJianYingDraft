# batch_processor.py
# 负责后台批量处理逻辑 (扫描、分组、调用核心函数)

import os
import threading
import time
import logging # 导入 logging
import traceback # 用于记录详细错误

# 尝试导入
try:
    # 同时导入两个需要的函数
    from jianying_utils import process_videos, prepare_video_paths_for_batch
except ImportError:
    # 在模块级别记录错误，如果导入失败，后续函数会检查 process_videos 是否为 None
    logging.exception("严重错误：无法导入 jianying_utils.py。请确保文件存在且在同一目录。")
    process_videos = None
    prepare_video_paths_for_batch = None # 也要设为 None

# 获取该模块的 logger 实例
logger = logging.getLogger(__name__)

# 支持的视频文件扩展名
SUPPORTED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv'}

def find_video_batches(input_folder):
    """
    扫描输入文件夹，按子文件夹查找并组织视频批次。
    使用标准 logging。

    Args:
        input_folder (str): 输入目录。

    Returns:
        list: 批次信息列表。
    """
    batches = []
    logger.info(f"开始扫描输入文件夹: {input_folder}")
    if not input_folder or not os.path.isdir(input_folder):
        logger.error(f"输入文件夹路径无效或不存在: '{input_folder}'")
        return batches

    try:
        for item_name in os.listdir(input_folder):
            item_path = os.path.join(input_folder, item_name)
            if os.path.isdir(item_path):
                batch_name = item_name
                logger.info(f"发现批次文件夹: {batch_name}")
                video_files = []
                try:
                    for sub_item_name in os.listdir(item_path):
                        sub_item_path = os.path.join(item_path, sub_item_name)
                        if os.path.isfile(sub_item_path):
                            _, ext = os.path.splitext(sub_item_name)
                            if ext.lower() in SUPPORTED_VIDEO_EXTENSIONS:
                                video_files.append(sub_item_path)
                except PermissionError:
                     logger.warning(f"没有权限访问子文件夹 '{batch_name}' 的内容，跳过此批次。")
                     continue
                except Exception as list_subdir_error:
                     logger.warning(f"访问子文件夹 '{batch_name}' 内容时出错: {list_subdir_error}，跳过此批次。")
                     continue

                if video_files:
                    video_files.sort()
                    logger.info(f"  批次 '{batch_name}' 找到 {len(video_files)} 个视频文件:")
                    max_log_files = 5
                    for i, vf in enumerate(video_files):
                        if i < max_log_files:
                             logger.info(f"    - {os.path.basename(vf)}")
                        elif i == max_log_files:
                             logger.info(f"    - ... (还有 {len(video_files) - max_log_files} 个)")
                    batches.append({'batch_name': batch_name, 'video_files': video_files})
                else:
                    logger.info(f"  信息：批次文件夹 '{batch_name}' 中未找到支持的视频文件 ({', '.join(SUPPORTED_VIDEO_EXTENSIONS)})。")
            else:
                 logger.debug(f"跳过非目录项目 '{item_name}'") # 使用 DEBUG 级别
                 pass
    except PermissionError:
         logger.error(f"没有权限访问输入文件夹: {input_folder}")
    except Exception as e:
        logger.exception(f"扫描文件夹时发生意外错误") # 使用 exception 记录堆栈

    if not batches:
        logger.info("扫描完成，未在输入文件夹中找到任何包含支持格式视频的子文件夹批次。")

    return batches

def run_batch_processing(input_folder, output_folder, draft_name, draft_folder_path):
    """
    执行批量处理的主函数 (在单独线程中运行)。
    使用标准 logging，不再需要 log_callback。

    Args:
        input_folder (str): 输入目录。
        output_folder (str): 输出目录。
        draft_name (str): 草稿名称。
        draft_folder_path (str): 草稿库路径。
    """
    # 检查依赖
    if process_videos is None or prepare_video_paths_for_batch is None:
        logger.critical("核心处理函数未能完全加载 (process_videos 或 prepare_video_paths_for_batch 为 None)，无法继续批量处理。")
        return

    logger.info("========= 开始批量处理 =========")
    total_batches = 0
    successful_batches = 0
    failed_batches = 0
    start_time = time.time()

    # 1. 查找视频批次
    video_batches = find_video_batches(input_folder) # 移除 log_callback
    total_batches = len(video_batches)

    if total_batches == 0:
        logger.info("未找到可处理的视频批次，批量处理结束。")
        logger.info("===================================")
        return

    logger.info(f"共找到 {total_batches} 个视频批次，准备开始处理...")

    # --- 阶段 1: 准备所有批次的视频路径 (执行切割等) ---
    logger.info("\n--- 阶段 1: 准备视频路径 (执行必要的切割) ---")
    prepared_batches = []
    preparation_failed_count = 0
    prep_start_time = time.time()
    for i, batch_info in enumerate(video_batches):
        batch_name = batch_info['batch_name']
        original_video_files = batch_info['video_files']
        logger.info(f"准备批次 {i+1}/{total_batches}: {batch_name}")

        # 调用新的准备函数，传入原始路径和输出文件夹（用于存放切割片段）
        final_video_files = prepare_video_paths_for_batch(original_video_files, output_folder)

        if final_video_files is None:
            logger.error(f"批次 '{batch_name}' 的视频准备/切割失败，将跳过此批次。")
            preparation_failed_count += 1
            # 可以选择在这里将 batch_info 标记为失败，或直接不加入 prepared_batches
        else:
            # 更新批次信息中的视频文件列表
            batch_info['video_files'] = final_video_files
            prepared_batches.append(batch_info)
            logger.info(f"批次 '{batch_name}' 准备完成，最终使用 {len(final_video_files)} 个视频文件。")

    prep_end_time = time.time()
    logger.info(f"--- 阶段 1 完成 | 耗时: {prep_end_time - prep_start_time:.2f}秒 | 成功准备 {len(prepared_batches)} 个批次 | 失败 {preparation_failed_count} 个批次 ---")

    if not prepared_batches:
        logger.info("没有成功准备的批次，批量处理结束。")
        logger.info("===================================")
        return

    # --- 阶段 2: 依次处理准备好的批次 (加载草稿、替换、导出) ---
    logger.info("\n--- 阶段 2: 处理并导出准备好的批次 (需要剪映运行并处于主界面) ---")
    logger.warning("请确保剪映专业版已打开并处于主界面，否则导出可能会失败！")
    # 可以选择在这里加一个短暂的暂停，给用户时间检查剪映状态
    # time.sleep(5)
    # --- 添加强制等待 --- 
    # input("*** 请确保剪映已打开并处于主界面，然后按 Enter 键继续处理... ***") # 移除 input()，子进程无法交互

    total_processed_batches = len(prepared_batches)
    process_start_time = time.time()

    for i, batch_info in enumerate(prepared_batches):
        batch_name = batch_info['batch_name']
        video_files = batch_info['video_files'] # 使用准备好的路径列表
        logger.info(f"\n--- 处理批次 {i+1}/{total_processed_batches}: {batch_name} ---")

        # 确定导出文件名 (确保文件名合法)
        safe_batch_name = "".join(c for c in batch_name if c.isalnum() or c in (' ', '_', '-')).rstrip()
        export_filename = f"{safe_batch_name}.mp4" if safe_batch_name else f"批次_{i+1}.mp4"
        logger.info(f"导出文件名将为: {export_filename}")

        try:
            # 调用核心处理函数，传入准备好的 video_files
            result = process_videos(
                video_paths=video_files,
                draft_name=draft_name,
                draft_folder_path=draft_folder_path,
                export_video=True,
                export_path=output_folder,
                export_filename=export_filename
            )

            if result["success"]:
                successful_batches += 1
                # process_videos 内部已有成功日志
            else:
                failed_batches += 1
                # process_videos 内部已有失败日志

        except Exception as e:
            failed_batches += 1
            logger.exception(f"处理批次 '{batch_name}' 时发生顶层意外错误") # 使用 exception

    # 3. 输出最终总结
    end_time = time.time()
    total_time = end_time - start_time
    logger.info("\n========= 批量处理完成 ==========")
    logger.info(f"总批次数 (扫描到): {total_batches}")
    logger.info(f"准备失败批次数: {preparation_failed_count}")
    logger.info(f"实际处理批次数: {total_processed_batches}")
    logger.info(f"成功处理批次数: {successful_batches}")
    logger.info(f"失败处理批次数: {failed_batches}")
    logger.info(f"总耗时: {total_time:.2f} 秒")
    logger.info(f"  - 阶段1 (准备/切割) 耗时: {prep_end_time - prep_start_time:.2f} 秒")
    if total_processed_batches > 0: # 避免除零
        logger.info(f"  - 阶段2 (处理/导出) 耗时: {end_time - process_start_time:.2f} 秒")
    logger.info("===================================")

# 注意：这个文件主要是被 gui_app.py 调用，通常不直接运行。
# 如果需要独立测试，可以添加 if __name__ == "__main__": 块来配置 logging 并调用 run_batch_processing

# 如果需要独立测试，可以添加 if __name__ == "__main__": 块来配置 logging 并调用 run_batch_processing
# if __name__ == "__main__":
#     import logging
#     logging.basicConfig(level=logging.DEBUG)
#     run_batch_processing("path_to_input_folder", "path_to_output_folder", "draft_name", "path_to_draft_folder") 