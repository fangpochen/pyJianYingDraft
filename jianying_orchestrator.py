# jianying_orchestrator.py
# 负责协调整个视频处理流程：获取任务 -> 切割 -> 剪映处理 -> 删除

import os
import time
import logging
import traceback

# --- Import necessary functions from other modules ---
try:
    # Functions for finding tasks and splitting videos
    from video_processor import find_video_tasks, split_video_ffmpeg
except ImportError:
    logging.exception("严重错误：无法导入 video_processor.py。")
    find_video_tasks = None
    split_video_ffmpeg = None

try:
    # Function for interacting with Jianying
    from jianying_utils import process_videos
except ImportError:
    # This is critical, log and set to None
    logging.exception("严重错误：无法导入 jianying_utils.py 或其核心函数 process_videos。")
    process_videos = None

logger = logging.getLogger(__name__)

def run_individual_video_processing(input_folder, output_folder, draft_name, draft_folder_path, delete_source):
    """
    Main function to process each video file individually.
    Orchestrates finding tasks, splitting, processing via Jianying, and cleanup.

    Args:
        input_folder (str): Root input directory with subfolders containing videos.
        output_folder (str): Root output directory where processed videos will be saved
                             (organized by subfolder).
        draft_name (str): Name of the Jianying draft template to use.
        draft_folder_path (str): Path to the Jianying draft library.
        delete_source (bool): Whether to delete the original video and its split
                              segments after successful processing.
    """
    # --- Dependency Check ---
    if not find_video_tasks or not split_video_ffmpeg:
        logger.critical("视频处理模块 (video_processor.py) 未完全加载，无法继续。")
        return
    if not process_videos:
        logger.critical("剪映处理模块 (jianying_utils.py) 或其核心函数 process_videos 未加载，无法继续。")
        return

    logger.info("========= 开始逐个视频处理 =========")
    start_time = time.time()
    total_tasks_found = 0
    successful_tasks = 0
    failed_tasks = 0
    split_failures = 0
    jianying_failures = 0

    # 1. Find all individual video tasks
    logger.info("--- 阶段 1: 查找所有独立的视频任务 ---")
    video_tasks = find_video_tasks(input_folder)
    total_tasks_found = len(video_tasks)

    if total_tasks_found == 0:
        logger.info("未找到任何需要处理的视频任务，处理结束。")
        logger.info("====================================")
        return

    logger.info(f"共找到 {total_tasks_found} 个视频任务，准备开始逐个处理...")

    # 2. Process each task individually
    logger.info("\n--- 阶段 2: 逐个处理视频任务 ---")
    logger.warning("请确保剪映专业版已打开并处于主界面，否则后续导出可能会失败！")
    # Consider adding a small delay here if needed for UI readiness
    # time.sleep(3)

    for i, task in enumerate(video_tasks):
        task_start_time = time.time()
        original_video_path = task['original_path']
        subfolder_name = task['subfolder_name']
        output_base_name = task['output_base_name'] # Base name for export/splits
        task_identifier = f"任务 {i+1}/{total_tasks_found}: {os.path.basename(original_video_path)} (来自: {subfolder_name})"

        logger.info(f"\n--- 开始处理 {task_identifier} ---")

        # --- Determine output directory for this specific task ---
        # Splits go into a subfolder within the main output, named after the original video
        split_output_dir = os.path.join(output_folder, subfolder_name, f"{output_base_name}_splits")
        # Final exported video goes directly into the subfolder named after the batch/original subfolder
        final_export_dir = os.path.join(output_folder, subfolder_name)
        final_export_filename = f"{output_base_name}.mp4" # Exported file uses original base name
        final_export_path = os.path.join(final_export_dir, final_export_filename)

        logger.info(f"  原始视频: {original_video_path}")
        logger.info(f"  切割片段输出目录: {split_output_dir}")
        logger.info(f"  最终导出目录: {final_export_dir}")
        logger.info(f"  最终导出文件名: {final_export_filename}")

        split_video_paths = None
        processing_result = {"success": False, "error": "未开始处理"}

        try:
            # --- Step 2a: Split the video (if necessary) ---
            logger.info("  步骤 2a: 准备/切割视频...")
            split_start_time = time.time()
            # Pass the specific output directory for this video's splits
            split_video_paths = split_video_ffmpeg(original_video_path, split_output_dir)
            split_duration = time.time() - split_start_time
            logger.info(f"  视频准备/切割完成，耗时: {split_duration:.2f}秒")

            if not split_video_paths:
                logger.error(f"  {task_identifier} 的视频切割失败，跳过此任务。")
                split_failures += 1
                failed_tasks += 1
                continue # Move to the next task

            logger.info(f"  最终用于处理的片段 ({len(split_video_paths)}): {', '.join(os.path.basename(p) for p in split_video_paths)}")

            # --- Step 2b: Process with Jianying ---
            logger.info("  步骤 2b: 调用剪映处理...")
            jy_start_time = time.time()
            processing_result = process_videos(
                video_paths=split_video_paths, # Use the split paths
                draft_name=draft_name,
                draft_folder_path=draft_folder_path,
                export_video=True, # Always export in this flow
                export_path=final_export_dir,
                export_filename=final_export_filename
            )
            jy_duration = time.time() - jy_start_time
            logger.info(f"  剪映处理完成，耗时: {jy_duration:.2f}秒")

            if processing_result["success"]:
                logger.info(f"  {task_identifier} 剪映处理成功。")
                successful_tasks += 1

                # --- Step 2c: Delete source and splits if requested ---
                if delete_source:
                    logger.info("  步骤 2c: 选项已启用，准备删除源文件和切割片段...")
                    # Delete the original video file
                    try:
                        if os.path.exists(original_video_path):
                            os.remove(original_video_path)
                            logger.info(f"    已删除原始视频文件: {original_video_path}")
                        else:
                            logger.warning(f"    原始视频文件已不存在，跳过删除: {original_video_path}")
                    except OSError as remove_error:
                        logger.error(f"    删除原始视频文件失败: {original_video_path} - {remove_error}", exc_info=True)

                    # Delete the split video files
                    if split_video_paths:
                        deleted_split_count = 0
                        logger.info(f"    准备删除切割片段 ({len(split_video_paths)} 个)...")
                        for split_file in split_video_paths:
                             # Only delete if it's not the original file itself (in case num_segments=1)
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
                         # Optional: Try to remove the split directory if empty
                        try:
                            if os.path.exists(split_output_dir) and not os.listdir(split_output_dir):
                                os.rmdir(split_output_dir)
                                logger.info(f"    已删除空的切割片段目录: {split_output_dir}")
                        except OSError as rmdir_error:
                            logger.warning(f"    删除切割片段目录失败（可能非空或权限问题）: {split_output_dir} - {rmdir_error}")

                else:
                    logger.info("  步骤 2c: 选项未启用，跳过删除源文件和切割片段。")

            else: # Jianying processing failed
                logger.error(f"  {task_identifier} 剪映处理失败: {processing_result.get('error', '未知错误')}")
                jianying_failures += 1
                failed_tasks += 1
                # Do not delete source/splits if Jianying part failed

        except Exception as task_error:
            logger.exception(f"处理 {task_identifier} 时发生顶层意外错误")
            failed_tasks += 1
            # Ensure counts reflect the failure stage if possible
            if split_video_paths is None: # Failed during or before split
                 split_failures +=1
            elif not processing_result["success"]: # Failed during jianying
                 jianying_failures +=1

        task_duration = time.time() - task_start_time
        logger.info(f"--- {task_identifier} 处理结束 | 耗时: {task_duration:.2f}秒 ---")


    # 3. Final Summary
    end_time = time.time()
    total_time = end_time - start_time
    logger.info("\n========= 逐个视频处理完成 =========")
    logger.info(f"总任务数 (扫描到): {total_tasks_found}")
    logger.info(f"成功处理任务数: {successful_tasks}")
    logger.info(f"失败处理任务数: {failed_tasks}")
    logger.info(f"  - 因切割失败: {split_failures}")
    logger.info(f"  - 因剪映处理失败: {jianying_failures}")
    logger.info(f"总耗时: {total_time:.2f} 秒")
    if total_tasks_found > 0:
        avg_time = total_time / total_tasks_found
        logger.info(f"平均任务耗时: {avg_time:.2f} 秒/任务")
    logger.info("====================================")

# --- Entry point for direct execution (if needed for testing) ---
# if __name__ == "__main__":
#     # Setup basic logging for testing
#     logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
#     # Example usage: Replace paths and names accordingly
#     test_input = "path/to/your/input_folder"
#     test_output = "path/to/your/output_folder"
#     test_draft = "Your_Template_Draft_Name"
#     test_draft_lib = "D:/DJianYingDrafts/JianyingPro Drafts" # Example
#     test_delete = False
#
#     run_individual_video_processing(test_input, test_output, test_draft, test_draft_lib, test_delete) 