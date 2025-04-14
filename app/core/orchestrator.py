# app/core/orchestrator.py
# 负责协调整个视频处理流程：获取任务 -> 切割 -> 剪映处理 -> 删除

import os
import time
import logging
import traceback

# --- Import necessary functions from other modules ---
try:
    # Update imports for new structure
    from .processor import find_video_tasks, split_video_ffmpeg, get_video_duration
except ImportError:
    logging.exception("严重错误：无法导入 processor.py。")
    find_video_tasks = None
    split_video_ffmpeg = None
    get_video_duration = None

try:
    # Update imports for new structure
    from ..util.jianying import process_videos
except ImportError:
    # This is critical, log and set to None
    logging.exception("严重错误：无法导入 util/jianying.py 或其核心函数 process_videos。")
    process_videos = None

logger = logging.getLogger(__name__)

def run_individual_video_processing(input_folder, output_folder, draft_name, draft_folder_path, delete_source, num_segments, keep_bgm=True, bgm_volume=100, main_track_volume=100):
    """
    Main function to process each video file individually.
    Orchestrates finding tasks, splitting, processing via Jianying, and cleanup.

    Args:
        input_folder (str): Root input directory with subfolders containing videos.
        output_folder (str): Root output directory where processed videos will be saved
                             (organized by subfolder).
        draft_name (str): Name of the Jianying draft template to use.
        draft_folder_path (str): Path to the Jianying draft library.
        delete_source (bool): Whether to delete the original video after successful processing.
                              Split segments are always deleted on success.
        num_segments (int): The number of segments to logically split the video into.
        keep_bgm (bool): Whether to keep the background music from the draft template. Defaults to True.
        bgm_volume (int): BGM音量，取值范围0-100，默认为100（原始音量）。
        main_track_volume (int): 主轨道音量，取值范围0-100，默认为100（原始音量）。

    Returns:
        dict: A dictionary containing processing results:
              {'success': bool, 'message': str, 'tasks_found': int, 'tasks_processed': int, 'tasks_failed': int}
    """
    # --- 结果统计初始化 ---
    result_summary = {
        'success': False, 
        'message': '处理未开始', 
        'tasks_found': 0, 
        'tasks_processed': 0, 
        'tasks_failed': 0
    }

    # --- Dependency Check ---
    if not find_video_tasks or not split_video_ffmpeg or not get_video_duration:
        err_msg = "核心依赖 (processor.py) 未完全加载，无法继续。"
        logger.critical(err_msg)
        result_summary['message'] = err_msg
        return result_summary # 返回失败
    if not process_videos:
        err_msg = "核心依赖 (jianying.py) 或其核心函数 process_videos 未加载，无法继续。"
        logger.critical(err_msg)
        result_summary['message'] = err_msg
        return result_summary # 返回失败

    logger.info("========= 开始逐个视频处理 =========")
    start_time = time.time()
    successful_tasks = 0
    failed_tasks = 0
    split_failures = 0
    jianying_failures = 0

    try:
        # 1. Find all individual video tasks
        logger.info("--- 阶段 1: 查找所有独立的视频任务 ---")
        video_tasks = find_video_tasks(input_folder)
        tasks_found = len(video_tasks)
        result_summary['tasks_found'] = tasks_found

        if tasks_found == 0:
            msg = "未找到任何需要处理的视频任务，处理结束。"
            logger.info(msg)
            logger.info("====================================")
            result_summary['success'] = True # 没有错误发生，所以算成功
            result_summary['message'] = msg
            return result_summary # 返回成功，但任务数为 0

        logger.info(f"共找到 {tasks_found} 个视频任务，准备开始逐个处理...")

        # 2. Process each task individually
        logger.info("\n--- 阶段 2: 逐个处理视频任务 ---")
        logger.warning("请确保剪映专业版已打开并处于主界面，否则后续导出可能会失败！")

        for i, task in enumerate(video_tasks):
            task_start_time = time.time()
            original_video_path = task['original_path']
            subfolder_name = task['subfolder_name']
            output_base_name = task['output_base_name'] # Base name for export/splits
            task_identifier = f"任务 {i+1}/{tasks_found}: {os.path.basename(original_video_path)} (来自: {subfolder_name})"

            logger.info(f"\n--- 开始处理 {task_identifier} ---")

            # --- Determine output directory for this specific task ---
            base_output_dir = os.path.join(output_folder, subfolder_name)
            try:
                os.makedirs(base_output_dir, exist_ok=True)
            except OSError as e:
                 logger.error(f"无法创建基础输出目录 {base_output_dir}: {e}", exc_info=True)
                 failed_tasks += 1
                 continue # Skip this task if base output dir cannot be created

            split_output_dir = os.path.join(base_output_dir, f"{output_base_name}_splits")
            final_export_dir = base_output_dir
            final_export_filename = f"{output_base_name}.mp4"
            final_export_path = os.path.join(final_export_dir, final_export_filename)

            logger.info(f"  原始视频: {original_video_path}")
            logger.info(f"  切割片段输出目录: {split_output_dir}")
            logger.info(f"  最终导出目录: {final_export_dir}")
            logger.info(f"  最终导出文件名: {final_export_filename}")

            split_video_paths = None
            original_duration_sec = None
            processing_success_flag = False # 用于标记单个任务是否成功

            try:
                # --- Step 2a(i): Get Original Video Duration ---
                try:
                    logger.info("  步骤 2a(i): 获取原始视频时长...")
                    original_duration_sec = get_video_duration(original_video_path)
                    if original_duration_sec is not None:
                        logger.info(f"    原始视频时长: {original_duration_sec:.2f} 秒")
                    else:
                        logger.warning(f"  无法获取原始视频 '{os.path.basename(original_video_path)}' 的时长。返回值为 None。")
                        logger.warning("  将无法调整模板时长，导出视频可能包含黑屏或被截断。")
                except Exception as dur_err:
                    logger.warning(f"  获取原始视频 '{os.path.basename(original_video_path)}' 时长时发生错误: {dur_err}", exc_info=True)
                    logger.warning("  将无法调整模板时长，导出视频可能包含黑屏或被截断。")
                    original_duration_sec = None

                # --- Step 2a(ii): Split the video (if necessary) ---
                logger.info("  步骤 2a(ii): 准备/切割视频...")
                split_start_time = time.time()
                split_video_paths = split_video_ffmpeg(
                    original_video_path, 
                    split_output_dir, 
                    num_segments=num_segments,
                    volume_level=main_track_volume
                )
                split_duration = time.time() - split_start_time
                logger.info(f"  视频准备/切割完成，耗时: {split_duration:.2f}秒")

                if not split_video_paths:
                    logger.error(f"  {task_identifier} 的视频切割失败，跳过此任务。")
                    split_failures += 1
                    raise RuntimeError("视频切割失败") # 抛出异常以便外层捕获

                logger.info(f"  最终用于处理的片段 ({len(split_video_paths)}): {', '.join(os.path.basename(p) for p in split_video_paths)}")

                # --- Step 2b: Process with Jianying (Pass duration) ---
                logger.info("  步骤 2b: 调用剪映处理...")
                jy_start_time = time.time()
                # 确保bgm_volume参数值是正确的
                logger.info(f"  传递BGM音量设置: {bgm_volume}%")
                # 调用剪映处理函数
                jy_result = process_videos(
                    video_paths=split_video_paths,
                    draft_name=draft_name,
                    draft_folder_path=draft_folder_path,
                    export_video=True,
                    export_path=final_export_dir,
                    export_filename=final_export_filename,
                    original_duration_seconds=original_duration_sec,
                    keep_bgm=keep_bgm,
                    bgm_volume=bgm_volume,  # 确保音量设置正确传递
                    main_track_volume=main_track_volume
                )
                jy_duration = time.time() - jy_start_time
                logger.info(f"  剪映处理完成，耗时: {jy_duration:.2f}秒")

                if jy_result["success"]:
                    logger.info(f"  {task_identifier} 剪映处理成功。")
                    processing_success_flag = True # 标记成功
                    successful_tasks += 1

                    # --- Step 2c: Delete source and splits --- 
                    logger.info("  步骤 2c(i): 准备删除切割片段...")
                    if split_video_paths:
                        deleted_split_count = 0
                        logger.info(f"    准备删除 {len(split_video_paths)} 个切割片段...")
                        for split_file in split_video_paths:
                            if split_file != original_video_path:
                                try:
                                    if os.path.exists(split_file):
                                        os.remove(split_file)
                                        logger.info(f"      已删除切割片段: {split_file}")
                                        deleted_split_count += 1
                                    else:
                                         logger.warning(f"      切割片段已不存在，跳过删除: {split_file}")
                                except OSError as remove_split_error:
                                    logger.error(f"      删除切割片段失败: {split_file} - {remove_split_error}", exc_info=True)
                        logger.info(f"    切割片段删除完成: 成功删除 {deleted_split_count} 个。")
                        try:
                            if os.path.exists(split_output_dir) and os.path.isdir(split_output_dir) and not os.listdir(split_output_dir):
                                os.rmdir(split_output_dir)
                                logger.info(f"    已删除空的切割片段目录: {split_output_dir}")
                            elif not os.path.exists(split_output_dir):
                                logger.warning(f"    切割片段目录已不存在，无需删除: {split_output_dir}")
                        except OSError as rmdir_error:
                            logger.warning(f"    删除切割片段目录失败（可能非空或权限问题）: {split_output_dir} - {rmdir_error}")
                    else:
                        logger.info("    未找到切割片段信息，跳过删除切割片段。")

                    if delete_source:
                        logger.info("  步骤 2c(ii): 选项已启用，准备删除原始视频文件...")
                        try:
                            if os.path.exists(original_video_path):
                                os.remove(original_video_path)
                                logger.info(f"    已删除原始视频文件: {original_video_path}")
                            else:
                                logger.warning(f"    原始视频文件已不存在，跳过删除: {original_video_path}")
                        except OSError as remove_error:
                            logger.error(f"    删除原始视频文件失败: {original_video_path} - {remove_error}", exc_info=True)
                    else:
                        logger.info("  步骤 2c(ii): 选项未启用，跳过删除原始视频文件。")

                else: # Jianying processing failed
                    error_msg_jy = jy_result.get('error', '未知剪映错误')
                    logger.error(f"  {task_identifier} 剪映处理失败: {error_msg_jy}")
                    jianying_failures += 1
                    raise RuntimeError(f"剪映处理失败: {error_msg_jy}") # 抛出异常

            except Exception as task_error:
                # 捕获当前任务处理过程中的所有异常 (切割失败, 剪映处理失败等)
                logger.exception(f"处理 {task_identifier} 时发生错误")
                failed_tasks += 1
                # 错误类型判断已在上面处理 (split_failures, jianying_failures)

            task_duration = time.time() - task_start_time
            status_str = "成功" if processing_success_flag else "失败"
            logger.info(f"--- {task_identifier} 处理结束 [{status_str}] | 耗时: {task_duration:.2f}秒 ---")
            # 循环继续处理下一个任务

        # --- 循环结束后 --- 
        result_summary['tasks_processed'] = successful_tasks
        result_summary['tasks_failed'] = failed_tasks
        result_summary['success'] = (failed_tasks == 0) # 只有所有任务都成功才算整体成功
        
        final_message = f"处理完成: 共找到 {tasks_found} 个任务, 成功 {successful_tasks} 个, 失败 {failed_tasks} 个 (切割失败: {split_failures}, 剪映失败: {jianying_failures})。"
        if failed_tasks > 0:
             final_message += " 请检查日志获取失败详情。"
        result_summary['message'] = final_message
        logger.info(final_message)

    except Exception as main_loop_error:
        # 捕获查找任务或循环本身之外的错误
        logger.exception("处理主循环发生意外错误")
        result_summary['success'] = False
        result_summary['message'] = f"发生意外错误: {main_loop_error}"
        # 更新失败计数 (如果适用)
        result_summary['tasks_failed'] = tasks_found - successful_tasks # 估算值

    # --- 3. Final Summary Log --- 
    end_time = time.time()
    total_time = end_time - start_time
    logger.info("\n========= 逐个视频处理完成 =========")
    logger.info(f"总任务数 (扫描到): {tasks_found}")
    logger.info(f"成功处理任务数: {successful_tasks}")
    logger.info(f"失败处理任务数: {failed_tasks}")
    logger.info(f"  - 因切割失败: {split_failures}")
    logger.info(f"  - 因剪映处理失败: {jianying_failures}")
    logger.info(f"总耗时: {total_time:.2f} 秒")
    if tasks_found > 0:
        avg_time = total_time / tasks_found
        logger.info(f"平均任务耗时: {avg_time:.2f} 秒/任务")
    logger.info("====================================")

    return result_summary # 返回包含详细结果的字典

# --- Entry point for direct execution (if needed for testing) ---
# if __name__ == "__main__":
#     # Setup basic logging for testing
#     # Ensure logging is configured appropriately before calling
#     # from ..util.logging_setup import setup_logging
#     # setup_logging()
#     # Example usage: Replace paths and names accordingly
#     test_input = "path/to/your/input_folder"
#     test_output = "path/to/your/output_folder"
#     test_draft = "Your_Template_Draft_Name"
#     test_draft_lib = "D:/DJianYingDrafts/JianyingPro Drafts" # Example
#     test_delete = False
#
#     run_individual_video_processing(test_input, test_output, test_draft, test_draft_lib, test_delete) 