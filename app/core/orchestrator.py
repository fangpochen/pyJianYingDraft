# app/core/orchestrator.py
# 负责协调整个视频处理流程：获取任务 -> 切割 -> 剪映处理 -> 删除

import os
import time
import logging
import traceback
import re
import random
import uuid
import datetime
# Added copy for deep copying material list
import copy

# --- Import necessary functions from other modules ---
try:
    # Update imports for new structure
    from .processor import find_video_tasks, split_video_ffmpeg, merge_videos_ffmpeg, get_video_duration, SUPPORTED_VIDEO_EXTENSIONS
except ImportError:
    logging.exception("严重错误：无法导入 processor.py。")
    find_video_tasks = None
    split_video_ffmpeg = None
    merge_videos_ffmpeg = None
    get_video_duration = None
    SUPPORTED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv'}  # 设置默认值，防止导入失败

try:
    # Update imports for new structure
    from ..util.jianying import process_videos
except ImportError:
    # This is critical, log and set to None
    logging.exception("严重错误：无法导入 util/jianying.py 或其核心函数 process_videos。")
    process_videos = None

logger = logging.getLogger(__name__)

# Helper function to delete source files safely
def _delete_source_files(files_to_delete, task_identifier="任务"):
    """Safely delete a list of source files."""
    deleted_count = 0
    for file_path in files_to_delete:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"({task_identifier}) 已删除源素材: {file_path}")
                deleted_count += 1
            else:
                logger.warning(f"({task_identifier}) 尝试删除源素材时未找到文件: {file_path}")
        except Exception as e:
            logger.warning(f"({task_identifier}) 删除源素材失败: {file_path} - {e}")
    return deleted_count

def run_individual_video_processing(input_folder, output_folder, draft_name, draft_folder_path, delete_source, num_segments, keep_bgm=True, bgm_volume=100, main_track_volume=100, process_mode="split", target_videos_count=1, process_by_subfolder=False, videos_per_subfolder=0, selected_templates=None):
    """
    Main function to process each video file individually.
    Orchestrates finding tasks, splitting, processing via Jianying, and cleanup.
    ***MODIFIED: Scans materials once; implements per-cycle subfolder limit.***

    Args:
        input_folder (str): Root input directory with subfolders containing videos.
        output_folder (str): Root output directory where processed videos will be saved
                             (organized by subfolder).
        draft_name (str): Name of the Jianying draft template to use.
        draft_folder_path (str): Path to the Jianying draft library.
        delete_source (bool): Whether to delete the original video(s) after successful processing.
        num_segments (int): The number of segments to split into (split mode) OR
                             the number of material videos to use per output video (merge mode).
        keep_bgm (bool): Whether to keep the background music from the draft template. Defaults to True.
        bgm_volume (int): BGM音量，取值范围0-100，默认为100（原始音量）。
        main_track_volume (int): 主轨道音量，取值范围0-100，默认为100（原始音量）。
        process_mode (str): 处理模式，可选值为"split"（分割）或"merge"（融合），默认为"split"。
        target_videos_count (int): 目标生成视频数量，用于排列组合，默认为1（不组合）。
        process_by_subfolder (bool): 是否按子目录循环处理，默认为False。
        videos_per_subfolder (int): 每个子目录处理视频数量，默认为0（不限制）。
        ***MODIFIED INTERPRETATION: This limit is now applied PER CYCLE through subfolders.***
        selected_templates (list): 选中的模板列表，如果提供且包含多个模板，将为每个视频任务随机选择一个模板。

    Returns:
        dict: A dictionary containing processing results:
              {'success': bool, 'message': str, 'materials_found': int, 'tasks_processed': int, 'tasks_failed': int}
    """
    # --- 结果统计初始化 ---
    result_summary = {
        'success': False,
        'message': '处理未开始',
        'materials_found': 0, # Renamed from tasks_found for clarity
        'tasks_processed': 0,
        'tasks_failed': 0
    }

    # --- Dependency Check ---
    if not find_video_tasks or not get_video_duration:
        err_msg = "核心依赖 (processor.py) 未完全加载，无法继续。"
        logger.critical(err_msg)
        result_summary['message'] = err_msg
        return result_summary # 返回失败
    
    if process_mode == "split" and not split_video_ffmpeg:
        err_msg = "分割模式所需的依赖 (split_video_ffmpeg) A未加载，无法继续。"
        logger.critical(err_msg)
        result_summary['message'] = err_msg
        return result_summary # 返回失败
    
    if process_mode == "merge" and not merge_videos_ffmpeg:
        err_msg = "融合模式所需的依赖 (merge_videos_ffmpeg) 未加载，无法继续。"
        logger.critical(err_msg)
        result_summary['message'] = err_msg
        return result_summary # 返回失败
    
    if not process_videos:
        err_msg = "核心依赖 (jianying.py) 或其核心函数 process_videos 未加载，无法继续。"
        logger.critical(err_msg)
        result_summary['message'] = err_msg
        return result_summary # 返回失败

    logger.info(f"========= 开始视频{'分割' if process_mode == 'split' else '融合'}处理 (内存管理模式) =========")
    start_time = time.time()
    successful_tasks = 0
    failed_tasks = 0
    split_merge_failures = 0
    jianying_failures = 0
    materials_not_found_failures = 0 # New counter for when materials run out

    try:
        # --- MODIFICATION START: Scan materials once ---
        logger.info("\n--- 阶段 1: 扫描并加载所有素材到内存 ---")
        available_materials = {} # Dictionary: subfolder_name -> list of material paths
        total_materials_found = 0
        try:
            # Use find_video_tasks to get the initial structure
            # Note: find_video_tasks returns a list of dicts, one per *video file* found
            all_found_videos = find_video_tasks(input_folder)
            if not all_found_videos:
                 logger.warning("未找到任何视频素材文件，任务完成")
                 result_summary = {
                    'success': True,
                    'message': "未找到任何视频素材文件，请检查输入路径。",
                    'materials_found': 0,
                    'tasks_processed': 0,
                    'tasks_failed': 0
                 }
                 return result_summary

            # Group materials by subfolder
            for video_info in all_found_videos:
                subfolder = video_info['subfolder_name']
                material_path = video_info['original_path']
                if subfolder not in available_materials:
                    available_materials[subfolder] = []
                available_materials[subfolder].append(material_path)
                total_materials_found += 1

            logger.info(f"扫描完成，共加载 {total_materials_found} 个视频素材分布在 {len(available_materials)} 个子目录中。")
            # Log initial counts per subfolder
            for sf, mats in available_materials.items():
                 logger.info(f"  - 子目录 '{sf}': {len(mats)} 个素材")

            # Determine the total number of videos to generate/tasks to run
            # In merge mode, it's target_videos_count.
            # In split mode, it's the total number of unique video files found.
            global_target_count = target_videos_count if process_mode == "merge" else total_materials_found
            logger.info(f"[全局统计] 处理模式: {process_mode}，目标视频/任务数量: {global_target_count}")

        except Exception as e:
            logger.exception(f"扫描或加载素材时出错: {e}")
            error_msg = f"视频素材扫描/加载阶段错误: {e}"
            result_summary = {
                'success': False,
                'message': error_msg,
                'materials_found': 0,
                'tasks_processed': 0,
                'tasks_failed': 0
            }
            return result_summary
        # --- MODIFICATION END: Scan materials once ---

        # --- 阶段 2: 逐个处理视频素材 (从内存中取用) ---
        logger.info("\n--- 阶段 2: 按需处理视频素材 (从内存中取用) ---")
        if not process_videos: # Double check dependency after logging start
             # This check might be redundant if done earlier, but safer
             raise RuntimeError("核心依赖 (jianying.py) 未加载。")
        logger.warning("请确保剪映专业版已打开并处于主界面，否则后续导出可能会失败！")

        # Global count for generated videos/processed tasks
        total_processed = 0

        # --- MODIFICATION START: Rework processing loops to use available_materials ---
        if process_by_subfolder:
            subfolder_list = list(available_materials.keys())
            if not subfolder_list:
                logger.warning("未找到任何包含素材的子目录（内存列表为空），无法处理。")
                result_summary['message'] = "未找到任何包含素材的子目录。"
                result_summary['materials_found'] = 0
                result_summary['tasks_processed'] = 0
                result_summary['tasks_failed'] = 0
                result_summary['success'] = True
                # The function will return result_summary later
            else:
                # Remove total count tracking per subfolder, limit is now per cycle
                processed_any_task_overall = False # Track if we ever processed anything

                logger.info(f"按子目录处理已启用，将按顺序尝试以下子目录: {', '.join(subfolder_list)}")
                logger.info(f"每个子目录在每一轮循环中最多处理 {videos_per_subfolder if videos_per_subfolder > 0 else '不限制'} 个任务。")

                # Outer loop: continue until global target is met
                while total_processed < global_target_count:
                    logger.info(f"\n--- 开始新一轮子目录处理循环 (当前进度: {total_processed}/{global_target_count}) ---")
                    
                    # 重要修复：每轮循环重置此标志
                    processed_in_this_cycle = False
                    
                    # Inner loop: iterate through each subfolder for this cycle
                    for current_subfolder in subfolder_list:
                        # Check if global target is already met within this cycle
                        if total_processed >= global_target_count:
                            break

                        # 检查子目录是否有足够素材
                        materials_in_sf = available_materials.get(current_subfolder, [])
                        if (process_mode == "merge" and len(materials_in_sf) < num_segments) or \
                           (process_mode == "split" and len(materials_in_sf) < 1):
                            logger.info(f"子目录 '{current_subfolder}' 素材不足 ({len(materials_in_sf)}个)，跳过此子目录。")
                            continue
                            
                        # Process up to `videos_per_subfolder` tasks for this subfolder IN THIS CYCLE
                        processed_count_this_subfolder_this_cycle = 0
                        logger.info(f"开始处理子目录 '{current_subfolder}' (剩余素材: {len(materials_in_sf)})")
                        
                        while (videos_per_subfolder <= 0 or processed_count_this_subfolder_this_cycle < videos_per_subfolder):
                            # 再次检查素材是否足够
                            materials_in_sf = available_materials.get(current_subfolder, [])
                            if (process_mode == "merge" and len(materials_in_sf) < num_segments) or \
                               (process_mode == "split" and len(materials_in_sf) < 1):
                                logger.info(f"  子目录 '{current_subfolder}' 素材已不足，处理了 {processed_count_this_subfolder_this_cycle} 个视频后切换下一个子目录。")
                                break

                            # Check again if global target met after processing within the same subfolder
                            if total_processed >= global_target_count:
                                break

                            task_materials_to_use = []
                            task_identifier_base = f"子目录: {current_subfolder}" # Base identifier

                            # --- Logic for MERGE mode ---
                            if process_mode == "merge":
                                 if len(materials_in_sf) >= num_segments:
                                     # *** Randomly sample materials ***
                                     task_materials_to_use = random.sample(materials_in_sf, num_segments)
                                     # *** REMOVE consumed materials from memory (by value) ***
                                     for item in task_materials_to_use:
                                         try:
                                             available_materials[current_subfolder].remove(item)
                                         except ValueError:
                                             # This should ideally not happen if sampling from the list
                                             logger.warning(f"({task_identifier_base}) 尝试从内存移除素材 {item} 时未找到，可能已被消耗？")
                                     logger.info(f"({task_identifier_base}) 从内存中为下一个合并任务随机选取了 {num_segments} 个素材。剩余 {len(available_materials[current_subfolder])} 个。")
                                     task_identifier = f"{task_identifier_base} - 合并任务 {total_processed + 1}"
                                 else:
                                     # Not enough materials in this subfolder for a merge task
                                     logger.info(f"({task_identifier_base}) 素材不足，跳过此子目录。")
                                     break # 跳出当前子目录的处理循环
                            # --- Logic for SPLIT mode ---
                            elif process_mode == "split":
                                 if len(materials_in_sf) >= 1:
                                     # *** Randomly choose ONE material ***
                                     chosen_material = random.choice(materials_in_sf)
                                     task_materials_to_use = [chosen_material]
                                     # *** REMOVE consumed material from memory (by value) ***
                                     try:
                                         available_materials[current_subfolder].remove(chosen_material)
                                     except ValueError:
                                         logger.warning(f"({task_identifier_base}) 尝试从内存移除素材 {chosen_material} 时未找到，可能已被消耗？")
                                     task_identifier = f"{task_identifier_base} - 分割任务: {os.path.basename(task_materials_to_use[0])}"
                                     logger.info(f"({task_identifier_base}) 从内存中为下一个分割任务随机选取了素材 '{os.path.basename(task_materials_to_use[0])}'。剩余 {len(available_materials[current_subfolder])} 个。")
                                 else:
                                     # No materials left in this subfolder for a split task
                                     logger.info(f"({task_identifier_base}) 素材不足，跳过此子目录。")
                                     break # 跳出当前子目录的处理循环
                            # --- Logic for other modes (if any) ---
                            else:
                                 logger.error(f"未知的处理模式: {process_mode}")
                                 failed_tasks += 1
                                 break # 跳出当前子目录的处理循环

                            # --- If we got materials, process the task ---
                            if task_materials_to_use:
                                 task_start_time = time.time()
                                 logger.info(f"开始处理 {task_identifier}")

                                 # Prepare task dictionary (simpler for merge, specific for split)
                                 task_info = {'subfolder_name': current_subfolder}
                                 if process_mode == 'split':
                                     task_info['original_path'] = task_materials_to_use[0] # Only one path needed for split
                                 # 'original_path' isn't strictly needed for merge in process_single_task anymore

                                 result = process_single_task(
                                     task_info,
                                     output_folder,
                                     draft_name,
                                     draft_folder_path,
                                     delete_source,
                                     num_segments,
                                     keep_bgm,
                                     bgm_volume,
                                     main_track_volume,
                                     process_mode,
                                     selected_templates,
                                     # Pass the specific materials for this task (critical for merge)
                                     material_paths_for_task=task_materials_to_use
                                 )

                                 task_end_time = time.time()
                                 task_duration = task_end_time - task_start_time

                                 # Increment the total processed count HERE
                                 total_processed += 1

                                 # 重要修复：标记已处理任务
                                 processed_in_this_cycle = True
                                 processed_any_task_overall = True
                                 processed_count_this_subfolder_this_cycle += 1 # Increment count for this subfolder *in this cycle*

                                 if result['success']:
                                     successful_tasks += 1
                                     # Deletion is now handled inside process_single_task if successful
                                 else:
                                     failed_tasks += 1
                                     # Increment specific failure counters if available in result
                                     if result.get('failure_type') == 'split_merge':
                                         split_merge_failures += 1
                                     elif result.get('failure_type') == 'jianying':
                                         jianying_failures += 1
                                     elif result.get('failure_type') == 'materials_not_found': # Should not happen here if logic is correct
                                         materials_not_found_failures += 1

                                 logger.info(f"完成处理 {task_identifier} - 耗时: {task_duration:.2f}秒")
                                 logger.info(f"子目录 '{current_subfolder}' 内存剩余: {len(available_materials.get(current_subfolder, []))} (本轮已处理: {processed_count_this_subfolder_this_cycle}/{videos_per_subfolder if videos_per_subfolder > 0 else '∞'}) (总进度: {total_processed}/{global_target_count})")

                                 # If target reached, break the inner loop
                                 if total_processed >= global_target_count:
                                     break
                            else:
                                 # 没有获取到素材，跳出当前子目录的处理循环
                                 logger.warning(f"({task_identifier_base}) 未能获取素材，跳过此子目录。")
                                 break

                        # 达到此子目录配额或素材用尽，输出日志并继续下一个子目录
                        if processed_count_this_subfolder_this_cycle > 0:
                            logger.info(f"子目录 '{current_subfolder}' 已处理 {processed_count_this_subfolder_this_cycle} 个视频，达到配额或素材已用尽，切换到下一个子目录。")
                        # If global target met, break the subfolder iteration for this cycle
                        if total_processed >= global_target_count:
                            break

                    # --- End of inner for loop (iterating through subfolders in a cycle) ---

                    # If target reached, break the outer loop
                    if total_processed >= global_target_count:
                         logger.info(f"已达到全局目标数量 ({global_target_count})，处理完成。")
                         break

                    # 重要修复：检查这一轮是否有任何进展
                    if not processed_in_this_cycle:
                        logger.warning("本轮循环未处理任何新视频。检查所有子目录均没有足够素材用于处理。")
                        # 检查是否还有任何子目录有足够素材
                        any_subfolder_has_materials = False
                        for sf in subfolder_list:
                            sf_materials = available_materials.get(sf, [])
                            if (process_mode == "merge" and len(sf_materials) >= num_segments) or \
                               (process_mode == "split" and len(sf_materials) >= 1):
                                any_subfolder_has_materials = True
                                break
                        
                        if not any_subfolder_has_materials:
                            logger.warning("所有子目录均无足够素材，无法继续处理。提前结束处理。")
                            materials_not_found_failures += (global_target_count - total_processed)
                            failed_tasks += (global_target_count - total_processed)
                            break
                        
                        # 如果仍有子目录有素材，但本轮没有处理任何视频，可能是其他原因导致的
                        # 这里不退出，给下一轮循环一次机会
                        logger.info("尽管本轮未处理视频，但检测到仍有子目录有足够素材，将尝试下一轮循环。")

                # Log if processing stopped early due to lack of materials
                if total_processed < global_target_count and not processed_any_task_overall:
                     logger.warning(f"按子目录处理提前终止，未能完成所有目标任务 ({total_processed}/{global_target_count})。")
                elif total_processed < global_target_count:
                     logger.warning(f"按子目录处理完成，但未能达到目标任务数量 ({total_processed}/{global_target_count})，可能是因为素材不足或子目录限制。")

        else: # Original sequential processing (NOT by subfolder), adapted for memory management
            logger.info("按素材顺序处理 (非按子目录循环)...")
            # Flatten the available materials into a single list of (subfolder, path) tuples
            # Order might be arbitrary depending on initial dict iteration
            all_materials_flat = []
            # Iterate through a *copy* of keys if modifying dict, but here we consume list
            subfolders_in_order = list(available_materials.keys()) # Get a fixed order
            for sf in subfolders_in_order:
                # We need to iterate through materials *within* each subfolder sequentially
                # This requires consuming from available_materials[sf] list
                 pass # This simple sequential logic needs rethinking for memory management

            # --- REVISED Sequential Logic ---
            logger.info("按素材顺序处理 (非按子目录循环) - 从内存中消耗...")
            # We need to decide how to handle 'merge' vs 'split' sequentially from memory
            processed_tasks_sequential = 0

            if process_mode == 'split':
                 # Process each material file found sequentially as a split task
                 logger.info("顺序分割模式：将处理内存中的每个素材文件。")
                 # Need a stable order to iterate through subfolders and then materials
                 subfolders_seq = list(available_materials.keys())
                 for subfolder in subfolders_seq:
                     materials_in_sf = available_materials.get(subfolder, [])
                     # Process all materials originally found in this subfolder
                     # Use a copy of the list to iterate while modifying the original
                     mats_to_process_in_sf = list(materials_in_sf) # Copy for iteration
                     for material_path in mats_to_process_in_sf:
                         if processed_tasks_sequential >= global_target_count: break

                         # Check if this material still exists in the live list (it should, initially)
                         if material_path in available_materials.get(subfolder, []):
                              # Consume it
                              available_materials[subfolder].remove(material_path)
                              task_identifier = f"顺序分割任务: {os.path.basename(material_path)} (来自: {subfolder})"
                              logger.info(f"开始处理 {task_identifier}")
                              task_start_time = time.time()

                              task_info = {'subfolder_name': subfolder, 'original_path': material_path}

                              result = process_single_task(
                                  task_info, output_folder, draft_name, draft_folder_path, delete_source,
                                  num_segments, keep_bgm, bgm_volume, main_track_volume, process_mode,
                                  selected_templates, material_paths_for_task=[material_path] # Pass single path
                              )
                              task_end_time = time.time()
                              task_duration = task_end_time - task_start_time
                              processed_tasks_sequential += 1

                              if result['success']: successful_tasks += 1
                              else: failed_tasks += 1 # Add failure type counts later if needed

                              logger.info(f"完成处理 {task_identifier} - 耗时: {task_duration:.2f}秒 (进度: {processed_tasks_sequential}/{global_target_count})")
                         else:
                              # Should not happen if logic is correct
                              logger.warning(f"尝试处理素材 {material_path} 时发现其已从内存列表中移除，跳过。")

                     if processed_tasks_sequential >= global_target_count: break
                 total_processed = processed_tasks_sequential

            elif process_mode == 'merge':
                 # Sequentially create merge combinations until target is met
                 logger.info(f"顺序合并模式：将尝试从内存中创建 {global_target_count} 个组合，每个组合需要 {num_segments} 个素材。")
                 combinations_created = 0
                 # We need a strategy to pick materials sequentially across subfolders
                 # Simple approach: flatten all available, then consume chunks
                 all_available_flat = []
                 subfolders_seq = list(available_materials.keys())
                 for sf in subfolders_seq:
                      all_available_flat.extend([(sf, path) for path in available_materials.get(sf, [])])

                 if len(all_available_flat) < num_segments * global_target_count:
                      needed = num_segments * global_target_count
                      logger.warning(f"内存中总素材数量 ({len(all_available_flat)}) 不足以生成目标 {global_target_count} 个视频 (每个需 {num_segments} 个，共需 {needed} 个)。将生成尽可能多的视频。")
                      global_target_count = len(all_available_flat) // num_segments # Adjust target

                 current_material_index = 0
                 while combinations_created < global_target_count:
                     # Check if enough materials remain *overall*
                     if (len(all_available_flat) - current_material_index) < num_segments:
                         logger.warning(f"剩余素材 ({len(all_available_flat) - current_material_index}) 不足以创建下一个视频组合 (需要 {num_segments} 个)。")
                         materials_not_found_failures += 1
                         failed_tasks += 1
                         break # Stop processing combinations

                     # Select next chunk of materials
                     materials_for_this_combo_tuples = all_available_flat[current_material_index : current_material_index + num_segments]
                     materials_for_this_combo_paths = [path for sf, path in materials_for_this_combo_tuples]
                     # Represent the source subfolder (e.g., from the first material)
                     source_subfolder_repr = materials_for_this_combo_tuples[0][0] if materials_for_this_combo_tuples else "未知"

                     task_identifier = f"顺序合并任务 {combinations_created + 1} (源自: {source_subfolder_repr} 等)"
                     logger.info(f"开始处理 {task_identifier}")
                     logger.info(f"  使用素材: {', '.join(os.path.basename(p) for p in materials_for_this_combo_paths)}")
                     task_start_time = time.time()

                     # We need to remove these used materials from the original `available_materials` dict
                     consumed_this_task = []
                     for sf, path in materials_for_this_combo_tuples:
                         if path in available_materials.get(sf, []):
                             available_materials[sf].remove(path)
                             consumed_this_task.append(path)
                         else:
                             logger.error(f"严重错误：尝试从内存中移除素材 {path} (来自 {sf}) 时未找到！")
                             # Decide how to handle this - fail the task?
                     if len(consumed_this_task) != num_segments:
                          logger.error(f"未能成功从内存中消耗所有所需素材用于任务 {combinations_created + 1}。")
                          failed_tasks += 1
                          # Skip processing this combination? Or proceed with what was consumed?
                          # For safety, skip:
                          current_material_index += num_segments # Still advance index past attempted chunk
                          continue


                     # Prepare task_info (subfolder_name is less critical here)
                     task_info = {'subfolder_name': source_subfolder_repr}

                     result = process_single_task(
                         task_info, output_folder, draft_name, draft_folder_path, delete_source,
                         num_segments, keep_bgm, bgm_volume, main_track_volume, process_mode,
                         selected_templates, material_paths_for_task=consumed_this_task # Pass the consumed paths
                     )
                     task_end_time = time.time()
                     task_duration = task_end_time - task_start_time
                     combinations_created += 1
                     total_processed += 1 # Increment overall processed count

                     if result['success']: successful_tasks += 1
                     else: failed_tasks += 1 # Add failure type counts later if needed

                     logger.info(f"完成处理 {task_identifier} - 耗时: {task_duration:.2f}秒 (进度: {combinations_created}/{global_target_count})")

                     current_material_index += num_segments # Move index for next chunk

                 # End while loop for sequential merge

            else: # Unknown mode sequentially
                 logger.error(f"顺序处理中遇到未知模式: {process_mode}")


        # --- MODIFICATION END: Rework processing loops ---


        # --- 阶段 3: 总结与清理 ---
        logger.info("\n--- 阶段 3: 处理总结 ---")
        end_time = time.time()
        total_duration = end_time - start_time

        result_summary['materials_found'] = total_materials_found # Total initially found
        result_summary['tasks_processed'] = total_processed # Actual videos generated / tasks run
        result_summary['tasks_failed'] = failed_tasks
        # Report remaining materials
        remaining_materials_count = sum(len(mats) for mats in available_materials.values())
        logger.info(f"处理结束后，内存中剩余素材总数: {remaining_materials_count}")
        result_summary['materials_remaining'] = remaining_materials_count

        # Adjust summary messages
        if failed_tasks == 0 and total_processed >= global_target_count:
            result_summary['success'] = True
            mode_desc = "分割" if process_mode == 'split' else "融合"
            by_subfolder_desc = "按子目录" if process_by_subfolder else "按顺序"
            result_summary['message'] = f"{by_subfolder_desc}{mode_desc}处理完成: 共找到 {total_materials_found} 个素材, 成功完成 {total_processed}/{global_target_count} 个目标视频/任务！"
        elif failed_tasks == 0 and total_processed < global_target_count:
             result_summary['success'] = True # Considered success if no errors, but target not met
             mode_desc = "分割" if process_mode == 'split' else "融合"
             by_subfolder_desc = "按子目录" if process_by_subfolder else "按顺序"
             result_summary['message'] = f"{by_subfolder_desc}{mode_desc}处理完成，但素材不足: 共找到 {total_materials_found} 个素材, 成功完成 {total_processed}/{global_target_count} 个目标视频/任务。"

        else: # Some tasks failed
            result_summary['success'] = False
            fail_details = []
            if split_merge_failures > 0: fail_details.append(f"{split_merge_failures} 个素材准备/分割失败")
            if jianying_failures > 0: fail_details.append(f"{jianying_failures} 个剪映处理/导出失败")
            if materials_not_found_failures > 0: fail_details.append(f"{materials_not_found_failures} 个因素材不足失败")
            other_failures = failed_tasks - split_merge_failures - jianying_failures - materials_not_found_failures
            if other_failures > 0: fail_details.append(f"{other_failures} 个其他/未知错误")
            fail_reason_str = ", ".join(fail_details) if fail_details else f"{failed_tasks} 个任务失败"

            mode_desc = "分割" if process_mode == 'split' else "融合"
            by_subfolder_desc = "按子目录" if process_by_subfolder else "按顺序"
            result_summary['message'] = f"{by_subfolder_desc}{mode_desc}处理部分失败: 目标 {global_target_count} 个视频/任务, 实际处理 {total_processed} 个, 其中 {fail_reason_str}。"


        logger.info(f"\n========= 视频{'分割' if process_mode == 'split' else '融合'}处理完成 (内存管理模式) =========")
        logger.info(f"总素材文件数 (扫描到): {total_materials_found}")
        logger.info(f"目标视频/任务数: {global_target_count}")
        logger.info(f"实际处理视频/任务数: {total_processed}")
        logger.info(f"  - 成功: {successful_tasks}")
        logger.info(f"  - 失败: {failed_tasks}")

        # Log specific failure counts if any occurred
        if failed_tasks > 0:
            if split_merge_failures > 0: logger.info(f"    - 因分割/融合失败: {split_merge_failures}")
            if jianying_failures > 0: logger.info(f"    - 因剪映处理失败: {jianying_failures}")
            if materials_not_found_failures > 0: logger.info(f"    - 因素材不足失败: {materials_not_found_failures}")
            if other_failures > 0: logger.info(f"    - 因其他/未知错误: {other_failures}")

        # Log subfolder details if processed that way
        if process_by_subfolder:
             logger.info("\n--- 按子目录循环处理统计 ---")
             # Log initial counts vs remaining counts
             remaining_counts = {sf: len(mats) for sf, mats in available_materials.items()} # Get remaining counts
             logger.info(f"处理后各子目录剩余素材数:")
             for sf, remaining_count in remaining_counts.items():
                 logger.info(f"  - 子目录 '{sf}': 剩余 {remaining_count} 个素材")


        logger.info(f"总耗时: {total_duration:.2f} 秒")
        if total_processed > 0:
            avg_task_time = total_duration / total_processed
            logger.info(f"平均任务处理耗时: {avg_task_time:.2f} 秒/任务")
        logger.info("====================================")

        return result_summary

    except Exception as e:
        logger.error(f"处理过程中发生未预料的严重错误: {traceback.format_exc()}")
        result_summary['success'] = False
        result_summary['message'] = f"发生严重错误: {e}"
        # Update counts based on what happened before the crash
        result_summary['tasks_processed'] = total_processed # Total attempted
        result_summary['tasks_failed'] = failed_tasks + 1 # Count the crash as a failure
        # Add subfolder info if applicable (might be incomplete if crash early)
        if process_by_subfolder:
             result_summary['process_by_subfolder'] = True

        return result_summary

# MODIFIED process_single_task to accept material_paths_for_task
def process_single_task(task, output_folder, draft_name, draft_folder_path, delete_source=False,
                       num_segments=1, keep_bgm=True, bgm_volume=100, main_track_volume=100,
                       process_mode="split", selected_templates=None, material_paths_for_task=None):
    """处理单个任务（一个目标视频）。
       在'split'模式下处理单个源视频。
       在'merge'模式下处理从内存传入的一组素材。

    Args:
        task (dict): 包含任务信息的字典，至少包含 subfolder_name。
                     在'split'模式下，还必须包含 original_path。
        output_folder (str): 输出文件夹根目录。
        draft_name (str): 剪映草稿名称。
        draft_folder_path (str): 剪映草稿库路径。
        delete_source (bool, optional): 是否在处理后删除源文件(组)。
        num_segments (int, optional): 'split'模式下切割片段数，'merge'模式下预期素材数。
        keep_bgm (bool, optional): 是否保留BGM。
        bgm_volume (int, optional): BGM音量(0-100)。
        main_track_volume (int, optional): 主轨道音量(0-100)。
        process_mode (str, optional): 处理模式 'split' 或 'merge'。
        selected_templates (list, optional): 选定的模板列表。
        material_paths_for_task (list, optional): 【新增】在'merge'模式下，明确传入此次任务使用的素材路径列表。
                                                  在'split'模式下，通常只包含一个路径（即task['original_path']）。

    Returns:
        dict: 包含处理结果的字典 {'success': bool, 'failure_type': str or None}
    """
    task_subfolder = task.get('subfolder_name', '未知子目录')
    # Determine a base identifier for logging, using the first material if available
    log_identifier_base = os.path.basename(material_paths_for_task[0]) if material_paths_for_task else "未知素材"
    if process_mode == 'split' and 'original_path' in task:
         log_identifier_base = os.path.basename(task['original_path'])

    logger.info(f"开始处理单个任务 ({process_mode}模式): {log_identifier_base} (来自子目录: {task_subfolder})")
    result = {
        'success': False,
        'failure_type': None # 'split_merge', 'jianying', 'materials_not_found'
    }
    created_split_files = [] # Track files created by split
    files_to_delete_on_success = [] # Track source files to delete if successful

    try:
        # --- SPLIT Mode Logic ---
        if process_mode == "split":
            source_video_path = task.get('original_path')
            if not source_video_path or not os.path.exists(source_video_path):
                 logger.error(f"分割模式错误：任务信息缺少有效源视频路径 'original_path' 或文件不存在: {source_video_path}")
                 result['failure_type'] = 'materials_not_found'
                 return result

            files_to_delete_on_success.append(source_video_path) # Mark original for deletion on success

            filename_without_ext = os.path.splitext(os.path.basename(source_video_path))[0]
            # Use a timestamp/UUID for split dir to avoid collisions if same filename is processed twice? Unlikely needed now.
            split_output_dir = os.path.join(output_folder, task_subfolder, f"{filename_without_ext}_splits_{uuid.uuid4().hex[:8]}")
            final_export_dir = os.path.join(output_folder, task_subfolder)
            # Make export filename unique to prevent overwrites if source names clash across runs
            export_filename = f"{filename_without_ext}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"
            target_export_path = os.path.join(final_export_dir, export_filename)

            os.makedirs(split_output_dir, exist_ok=True)
            os.makedirs(final_export_dir, exist_ok=True)

            original_duration_sec = None
            try:
                original_duration_sec = get_video_duration(source_video_path)
                if original_duration_sec is not None: logger.info(f"原始视频时长: {original_duration_sec:.2f}秒")
            except Exception as e:
                logger.warning(f"获取视频 '{source_video_path}' 时长时出错: {e}")

            logger.info(f"分割视频为 {num_segments} 个片段: {os.path.basename(source_video_path)}")
            created_split_files = split_video_ffmpeg(
                source_video_path,
                split_output_dir,
                num_segments=num_segments,
                volume_level=main_track_volume # Apply main track volume during split? Or let jianying handle? Assuming here.
            )

            if not created_split_files:
                logger.error("视频分割失败")
                result['failure_type'] = 'split_merge'
                # Cleanup potentially empty split dir?
                try: os.rmdir(split_output_dir)
                except OSError: pass
                return result

            logger.info(f"分割后的片段: {', '.join(os.path.basename(p) for p in created_split_files)}")

            # Random template selection (same as before)
            task_draft_name = draft_name
            if selected_templates and len(selected_templates) > 0:
                 # Ensure draft_name is in the pool if not already
                 template_pool = list(set(selected_templates + ([draft_name] if draft_name not in selected_templates else [])))
                 task_draft_name = random.choice(template_pool)
                 logger.info(f"随机选择模板: {task_draft_name}")

            # Call Jianying processing
            logger.info(f"开始剪映处理 (使用模板: {task_draft_name})...")
            jy_result = process_videos(
                video_paths=created_split_files, # Use the generated splits
                draft_name=task_draft_name,
                draft_folder_path=draft_folder_path,
                export_video=True,
                export_path=os.path.dirname(target_export_path),
                export_filename=os.path.basename(target_export_path),
                original_duration_seconds=original_duration_sec, # Pass original duration if available
                keep_bgm=keep_bgm,
                bgm_volume=bgm_volume,
                main_track_volume=main_track_volume # Let Jianying apply main volume to combined track
            )

            if jy_result["success"]:
                logger.info(f"剪映处理成功: {target_export_path}")
                result['success'] = True
            else:
                error_msg = jy_result.get('error', '未知错误')
                logger.error(f"剪映处理失败: {error_msg}")
                result['failure_type'] = 'jianying'

        # --- MERGE Mode Logic ---
        elif process_mode == "merge":
            if not material_paths_for_task:
                 logger.error("合并模式错误：未提供素材路径列表 (material_paths_for_task)")
                 result['failure_type'] = 'materials_not_found'
                 return result
            if len(material_paths_for_task) < num_segments:
                 logger.error(f"合并模式错误：提供的素材数量 ({len(material_paths_for_task)}) 少于需要的数量 ({num_segments})")
                 result['failure_type'] = 'materials_not_found'
                 # Mark these insufficient materials for deletion? Or leave them? Assume leave them.
                 return result
            if len(material_paths_for_task) > num_segments:
                 logger.warning(f"合并模式注意：提供的素材数量 ({len(material_paths_for_task)}) 多于需要的数量 ({num_segments})，将只使用前 {num_segments} 个。")
                 material_paths_for_task = material_paths_for_task[:num_segments] # Use only the required number

            # Mark these specific materials for deletion on success
            files_to_delete_on_success.extend(material_paths_for_task)

            # Create unique export filename based on the first material and timestamp
            first_material_name = os.path.splitext(os.path.basename(material_paths_for_task[0]))[0] if material_paths_for_task else "merged"
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            unique_filename = f"{first_material_name}_{timestamp}.mp4" # Assuming mp4 output
            export_subfolder_path = os.path.join(output_folder, task_subfolder)
            target_export_path = os.path.join(export_subfolder_path, unique_filename)

            os.makedirs(export_subfolder_path, exist_ok=True)

            logger.info(f"开始直接素材替换处理，使用 {len(material_paths_for_task)} 个指定素材。")

            # Random template selection (same as split)
            task_draft_name = draft_name
            if selected_templates and len(selected_templates) > 0:
                 template_pool = list(set(selected_templates + ([draft_name] if draft_name not in selected_templates else [])))
                 task_draft_name = random.choice(template_pool)
                 logger.info(f"随机选择模板: {task_draft_name}")

            try:
                # Call Jianying processing with the provided list of materials
                jy_result = process_videos(
                    video_paths=material_paths_for_task, # Use the provided list
                    draft_name=task_draft_name,
                    draft_folder_path=draft_folder_path,
                    export_video=True,
                    export_path=os.path.dirname(target_export_path),
                    export_filename=os.path.basename(target_export_path),
                    keep_bgm=keep_bgm,
                    bgm_volume=bgm_volume,
                    main_track_volume=main_track_volume,
                    segments_to_replace=num_segments # Confirm this param name matches jianying.py
                )

                if jy_result['success']:
                    logger.info(f"模板素材直接替换成功: {target_export_path}")
                    result['success'] = True
                else:
                    error_msg = jy_result.get('error', '未知错误')
                    logger.error(f"模板素材直接替换失败: {error_msg}")
                    result['failure_type'] = 'jianying'
            except ValueError as ve:
                logger.error(f"素材处理验证失败: {str(ve)}")
                result['error'] = str(ve) # Pass specific error message back if needed
                result['failure_type'] = 'jianying' # Or maybe 'split_merge' if it's a pre-check? Assume jianying for now.
            except Exception as e:
                logger.exception(f"直接素材替换过程中发生未预期的错误: {e}")
                result['failure_type'] = 'jianying'

        # --- Unknown Mode ---
        else:
             logger.error(f"未知的处理模式: {process_mode}")
             result['failure_type'] = 'split_merge' # Assign a generic failure type

    except Exception as e:
         logger.exception(f"处理任务 {log_identifier_base} 时发生严重错误: {e}")
         result['success'] = False
         # Try to determine failure type based on stage? Hard here. Assign generic.
         result['failure_type'] = result.get('failure_type') or 'split_merge' # Keep existing type if set, else generic

    finally:
        # --- Cleanup: Delete source files if requested AND successful ---
        if delete_source and result['success']:
            _delete_source_files(files_to_delete_on_success, log_identifier_base)

        # --- Cleanup: Delete temporary split files (always on success or failure for split mode) ---
        if process_mode == "split" and created_split_files:
            logger.debug(f"清理临时分割文件...")
            deleted_splits = _delete_source_files(created_split_files, f"{log_identifier_base}-splits")
            logger.debug(f"清理完成，删除了 {deleted_splits} 个临时分割文件。")
            # Try removing the split directory if it exists and is empty
            split_dir = os.path.dirname(created_split_files[0]) if created_split_files else None
            if split_dir and os.path.exists(split_dir):
                 try:
                     if not os.listdir(split_dir): # Check if empty
                         os.rmdir(split_dir)
                         logger.debug(f"已删除空的临时分割目录: {split_dir}")
                 except Exception as e:
                     logger.warning(f"删除临时分割目录失败: {split_dir} - {e}")

    return result

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