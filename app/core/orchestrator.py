# app/core/orchestrator.py
# 负责协调整个视频处理流程：获取任务 -> 切割 -> 剪映处理 -> 删除

import os
import time
import logging
import traceback
import re

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

def run_individual_video_processing(input_folder, output_folder, draft_name, draft_folder_path, delete_source, num_segments, keep_bgm=True, bgm_volume=100, main_track_volume=100, process_mode="split", target_videos_count=1):
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
        num_segments (int): The number of segments to logically split or merge the video into.
        keep_bgm (bool): Whether to keep the background music from the draft template. Defaults to True.
        bgm_volume (int): BGM音量，取值范围0-100，默认为100（原始音量）。
        main_track_volume (int): 主轨道音量，取值范围0-100，默认为100（原始音量）。
        process_mode (str): 处理模式，可选值为"split"（分割）或"merge"（融合），默认为"split"。
        target_videos_count (int): 目标生成视频数量，用于排列组合，默认为1（不组合）。

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

    logger.info(f"========= 开始逐个视频{process_mode == 'split' and '分割' or '融合'}处理 =========")
    start_time = time.time()
    successful_tasks = 0
    failed_tasks = 0
    split_merge_failures = 0
    jianying_failures = 0
    
    # 跟踪全局成功处理的组合数量（在直接素材替换模式下使用）
    global_successful_combinations = 0
    
    try:
        # 1. Find all individual video tasks
        logger.info("\n--- 阶段 1: 扫描并准备素材 ---")
        
        # 获取所有视频任务
        try:
            video_tasks = find_video_tasks(input_folder)
            tasks_found = len(video_tasks)
            logger.info(f"找到 {tasks_found} 个素材文件夹")
            
            # 明确目标生成视频数量 - 移到这里，确保tasks_found已定义
            global_target_count = target_videos_count if process_mode == "merge" else tasks_found
            logger.info(f"[全局统计] 处理模式: {process_mode}，目标视频数量: {global_target_count}")
            
            if tasks_found == 0:
                logger.warning("未找到任何视频素材文件夹，任务完成")
                result_summary = {
                    'success': True,  # 虽然没有任务，但不算错误
                    'message': "未找到任何视频素材文件夹，请检查输入路径。",
                    'tasks_found': 0,
                    'tasks_processed': 0,
                    'tasks_failed': 0
                }
                return result_summary
                
        except Exception as e:
            # 捕获查找任务时的错误
            logger.exception(f"查找素材文件夹时出错: {e}")
            error_msg = f"视频素材查找阶段错误: {e}"
            result_summary = {
                'success': False,
                'message': error_msg,
                'tasks_found': 0,
                'tasks_processed': 0,
                'tasks_failed': 0
            }
            return result_summary

        # 2. Process each task individually
        logger.info("\n--- 阶段 2: 逐个处理视频素材 ---")
        logger.warning("请确保剪映专业版已打开并处于主界面，否则后续导出可能会失败！")

        # 设置目标生成视频数量（全局范围）
        global_combinations_to_process = target_videos_count if process_mode == "merge" else tasks_found
        logger.info(f"[全局统计] 目标总视频数量: {global_combinations_to_process}（{'按组合数' if process_mode == 'merge' else '按素材文件夹数'}）")

        for i, task in enumerate(video_tasks):
            # 检查是否已达到全局目标
            if process_mode == "merge" and global_successful_combinations >= global_combinations_to_process:
                logger.info(f"[全局统计] ⚠️ 已成功处理 {global_successful_combinations} 个组合，达到全局目标 {global_combinations_to_process}，停止后续任务处理")
                break

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
                logger.info(f"  步骤 2a(ii): {'分割' if process_mode == 'split' else '融合'}视频...")
                split_merge_start_time = time.time()
                
                if process_mode == "split":
                    # 分割模式
                    split_video_paths = split_video_ffmpeg(
                        original_video_path, 
                        split_output_dir, 
                        num_segments=num_segments,
                        volume_level=main_track_volume
                    )
                    split_merge_duration = time.time() - split_merge_start_time
                    logger.info(f"  视频分割完成，耗时: {split_merge_duration:.2f}秒")
                    
                    if not split_video_paths:
                        logger.error(f"  {task_identifier} 的视频分割失败，跳过此任务。")
                        split_merge_failures += 1
                        raise RuntimeError("视频分割失败") # 抛出异常以便外层捕获
                    
                    logger.info(f"  最终用于处理的片段 ({len(split_video_paths)}): {', '.join(os.path.basename(p) for p in split_video_paths)}")
                else:
                    # 直接素材替换模式 (更新后的实现)
                    # 在直接替换模式下，我们需要找到相关的视频文件来组成组合
                    # 然后直接将这些视频传递给剪映进行处理
                    
                    # 获取当前文件夹下的所有视频文件
                    video_dir = os.path.dirname(original_video_path)
                    base_name = os.path.splitext(os.path.basename(original_video_path))[0]
                    ext = os.path.splitext(original_video_path)[1]
                    
                    # 搜索所有视频文件
                    potential_videos = []
                    try:
                        for filename in os.listdir(video_dir):
                            file_path = os.path.join(video_dir, filename)
                            if os.path.isfile(file_path) and os.path.splitext(filename)[1].lower() in SUPPORTED_VIDEO_EXTENSIONS:
                                potential_videos.append(file_path)
                    except Exception as e:
                        logger.error(f"查找视频文件时出错: {e}")
                        split_merge_failures += 1
                        raise RuntimeError(f"查找视频文件失败: {e}")
                    
                    # 如果没有找到足够的视频文件，则报错
                    if len(potential_videos) < num_segments:
                        logger.error(f"未找到足够的视频文件用于组合，需要{num_segments}个，但只找到{len(potential_videos)}个")
                        split_merge_failures += 1
                        raise RuntimeError(f"未找到足够的视频文件用于组合，需要{num_segments}个，但只找到{len(potential_videos)}个")
                    
                    logger.info(f"  找到{len(potential_videos)}个视频文件可用于组合")
                    
                    # 提取视频文件的前缀映射，用于确保组合中不使用相同前缀的视频
                    def extract_video_prefix(filepath):
                        filename = os.path.basename(filepath)
                        # 尝试匹配常见的编号模式，如 name_1.mp4, name-1.mp4, name(1).mp4 等
                        match = re.search(r'^(.+?)(?:[_\-\s\.]\d+|\(\d+\))(?:\.[^.]+)?$', filename)
                        if match:
                            return match.group(1)
                        # 如果没有匹配到编号模式，尝试提取第一个下划线或短横线前的内容
                        parts = re.split(r'[_\-\s]', filename, 1)
                        if len(parts) > 1:
                            return parts[0]
                        # 如果没有分隔符，返回文件名（不含扩展名）
                        return os.path.splitext(filename)[0]
                    
                    # 按前缀分组视频文件
                    prefix_to_videos = {}
                    for video_path in potential_videos:
                        prefix = extract_video_prefix(video_path)
                        if prefix not in prefix_to_videos:
                            prefix_to_videos[prefix] = []
                        prefix_to_videos[prefix].append(video_path)
                    
                    # 日志输出前缀分组情况
                    logger.info(f"  视频文件按前缀分组:")
                    for prefix, videos in prefix_to_videos.items():
                        logger.info(f"    前缀 '{prefix}': {len(videos)} 个文件")
                    
                    # 检查是否有足够不同前缀的视频组
                    if len(prefix_to_videos) < num_segments:
                        logger.warning(f"  警告: 只有 {len(prefix_to_videos)} 个不同前缀的视频组，但需要 {num_segments} 个不同前缀")
                    
                    # 初始化数据库
                    from app.util.merge_database import MergeDatabase
                    db_dir = "db"
                    db_file = "merge_history.db"
                    db_path = os.path.join(db_dir, db_file)
                    
                    # 确保db目录存在
                    if not os.path.exists(db_dir):
                        os.makedirs(db_dir)
                        logger.info(f"创建数据库目录: {db_dir}")
                    
                    # 跟踪成功处理的组合数量
                    successful_combinations = 0
                    failed_combinations = 0
                    
                    # 用于跟踪本次处理中使用过的所有文件
                    used_video_files = set()
                    
                    # 根据目标生成视频数量计算当前任务需要处理的组合数
                    # 考虑全局已完成的组合数，确保不会超过全局目标
                    remaining_combinations = global_combinations_to_process - global_successful_combinations
                    combinations_to_process = min(max(1, target_videos_count), remaining_combinations)
                    logger.info(f"  任务 {i+1} 目标处理 {combinations_to_process} 个视频组合（全局已完成: {global_successful_combinations}, 全局目标: {global_combinations_to_process}）")
                    
                    # 如果没有剩余组合需要处理，跳过当前任务
                    if combinations_to_process <= 0:
                        logger.info(f"[全局统计] 当前素材文件夹 {i+1} 中没有剩余组合需要处理（全局已完成: {global_successful_combinations}/{global_combinations_to_process}）")
                        processing_success_flag = True  # 标记为成功，不计入失败
                        continue
                    
                    # 初始化组合索引
                    combo_index = 0
                    
                    # 修改循环条件，当成功处理的组合数达到目标时，停止处理
                    while successful_combinations < combinations_to_process:
                        try:
                            # 为每个组合生成唯一的输出文件名
                            combo_suffix = f"_{combo_index+1}" if combinations_to_process > 1 else ""
                            combo_output_filename = f"{output_base_name}{combo_suffix}.mp4"
                            combo_export_path = os.path.join(final_export_dir, combo_output_filename)
                            
                            logger.info(f"  处理组合 {combo_index+1}，目前已成功 {successful_combinations}/{combinations_to_process}")
                            
                            # 选择视频组合
                            selected_combo = None
                            
                            # 自定义生成不包含相同前缀视频的组合
                            def create_diverse_combo():
                                # 收集每个前缀组的使用次数
                                prefix_usage = {}
                                with MergeDatabase(db_path) as db:
                                    for prefix, videos in prefix_to_videos.items():
                                        # 计算该前缀组中文件的平均使用次数
                                        usage_stats = db.get_file_usage_stats()
                                        total_usage = sum(usage_stats.get(os.path.basename(v), 0) for v in videos)
                                        avg_usage = total_usage / len(videos) if videos else 0
                                        prefix_usage[prefix] = avg_usage
                                
                                # 按使用次数排序前缀，优先选择使用次数少的
                                sorted_prefixes = sorted(prefix_usage.keys(), key=lambda p: prefix_usage[p])
                                
                                # 如果排序后的前缀数量少于需要的段数，无法创建多样化组合
                                if len(sorted_prefixes) < num_segments:
                                    logger.warning(f"  没有足够的不同前缀 ({len(sorted_prefixes)}/{num_segments})，无法创建完全多样化的组合")
                                    return None
                                
                                # 选择使用频率最低的每个前缀组中的一个视频
                                combo = []
                                used_prefixes = []
                                
                                for i in range(min(num_segments, len(sorted_prefixes))):
                                    prefix = sorted_prefixes[i]
                                    used_prefixes.append(prefix)
                                    
                                    # 从该前缀组中选择使用频率最低的视频
                                    videos_in_prefix = prefix_to_videos[prefix]
                                    with MergeDatabase(db_path) as db:
                                        least_used = db.get_least_used_files(videos_in_prefix, limit=len(videos_in_prefix))
                                        if least_used:
                                            combo.append(least_used[0])
                                        else:
                                            # 如果数据库查询失败，随机选择一个
                                            import random
                                            combo.append(random.choice(videos_in_prefix))
                                
                                logger.info(f"  已创建多样化组合，使用了以下前缀: {', '.join(used_prefixes)}")
                                return combo
                            
                            with MergeDatabase(db_path) as db:
                                # 查找使用不同前缀的未使用组合
                                logger.info(f"  正在为组合 {combo_index+1}/{combinations_to_process} 查找使用不同前缀的视频组合...")
                                
                                # 尝试自定义生成多样化组合
                                selected_combo = create_diverse_combo()
                                
                                if selected_combo:
                                    logger.info(f"  组合 {combo_index+1}: 成功创建使用不同前缀的组合")
                                else:
                                    # 如果无法创建多样化组合，则回退到旧方法
                                    logger.warning(f"  组合 {combo_index+1}: 无法创建完全多样化的组合，将尝试使用旧方法")
                                    
                                    # 尝试从所有可能文件中找出未使用的组合
                                    unused_combinations = db.find_unused_combinations(potential_videos, num_segments)
                                    
                                    if unused_combinations:
                                        # 过滤出不包含相同前缀的组合
                                        diverse_combinations = []
                                        for combo in unused_combinations:
                                            prefixes = [extract_video_prefix(v) for v in combo]
                                            if len(prefixes) == len(set(prefixes)):  # 检查前缀是否都不同
                                                diverse_combinations.append(combo)
                                        
                                        if diverse_combinations:
                                            idx = min(combo_index, len(diverse_combinations) - 1)
                                            selected_combo = diverse_combinations[idx]
                                            logger.info(f"  组合 {combo_index+1}: 找到使用不同前缀的未使用组合")
                                        else:
                                            logger.warning(f"  组合 {combo_index+1}: 未找到使用不同前缀的未使用组合")
                                            # 回退到随机选择，但确保前缀不同
                                            import random
                                            if len(prefix_to_videos) >= num_segments:
                                                selected_prefixes = random.sample(list(prefix_to_videos.keys()), num_segments)
                                                selected_combo = [random.choice(prefix_to_videos[p]) for p in selected_prefixes]
                                                logger.info(f"  组合 {combo_index+1}: 随机选择了不同前缀的文件")
                                            else:
                                                logger.warning(f"  组合 {combo_index+1}: 没有足够的不同前缀可供选择")
                                                selected_combo = random.sample(potential_videos, num_segments)
                                                logger.warning(f"  组合 {combo_index+1}: 随机选择文件组合（可能包含相同前缀）")
                                    else:
                                        # 如果没有未使用的组合，尝试创建前缀多样化的组合
                                        logger.warning(f"  组合 {combo_index+1}: 未找到未使用的组合，将尝试创建多样化组合")
                                        
                                        if len(prefix_to_videos) >= num_segments:
                                            import random
                                            selected_prefixes = random.sample(list(prefix_to_videos.keys()), num_segments)
                                            selected_combo = [random.choice(prefix_to_videos[p]) for p in selected_prefixes]
                                            logger.info(f"  组合 {combo_index+1}: 创建了使用不同前缀的组合")
                                        else:
                                            logger.warning(f"  组合 {combo_index+1}: 没有足够的不同前缀 ({len(prefix_to_videos)}/{num_segments})")
                                            # 回退到使用最少使用的文件
                                            least_used_files = db.get_least_used_files(potential_videos, limit=len(potential_videos))
                                            if len(least_used_files) >= num_segments:
                                                selected_combo = least_used_files[:num_segments]
                                                logger.warning(f"  组合 {combo_index+1}: 使用了频率最低的文件（可能包含相同前缀）")
                            
                            if selected_combo:
                                # 检查所选组合中的前缀是否都不同
                                combo_prefixes = [extract_video_prefix(v) for v in selected_combo]
                                has_unique_prefixes = len(combo_prefixes) == len(set(combo_prefixes))
                                
                                if has_unique_prefixes:
                                    logger.info(f"  组合 {combo_index+1}: 所选组合使用了不同的前缀")
                                else:
                                    logger.warning(f"  组合 {combo_index+1}: 所选组合包含相同前缀: {', '.join(combo_prefixes)}")
                                
                                logger.info(f"  组合 {combo_index+1} 选择的文件: {', '.join(os.path.basename(f) for f in selected_combo)}")
                                
                                # 直接将选中的文件传递给剪映处理
                                logger.info(f"  组合 {combo_index+1}: 直接将选中文件传递给剪映处理")
                                
                                # 调用剪映处理
                                jy_result = process_videos(
                                    video_paths=selected_combo,  # 直接传递原始文件列表
                                    draft_name=draft_name,
                                    draft_folder_path=draft_folder_path,
                                    export_video=True,
                                    export_path=final_export_dir,
                                    export_filename=combo_output_filename,
                                    original_duration_seconds=original_duration_sec,
                                    keep_bgm=keep_bgm,
                                    bgm_volume=bgm_volume,
                                    main_track_volume=main_track_volume
                                )
                                
                                if jy_result["success"]:
                                    logger.info(f"  组合 {combo_index+1}: 剪映处理成功")
                                    
                                    # 记录到数据库
                                    try:
                                        with MergeDatabase(db_path) as db:
                                            # 重要：每个组合使用不同的输出文件路径，确保生成不同的task_id
                                            db.add_merge_task(selected_combo, combo_export_path)
                                            logger.info(f"  组合 {combo_index+1}: 已记录到数据库")
                                    except Exception as e:
                                        logger.error(f"  组合 {combo_index+1}: 记录到数据库失败: {e}")
                                    
                                    # 将成功处理的文件添加到使用过的文件集合中
                                    for video_file in selected_combo:
                                        used_video_files.add(video_file)
                                    
                                    successful_combinations += 1
                                    global_successful_combinations += 1
                                    logger.info(f"[全局统计] 组合处理成功 - 当前任务进度: {successful_combinations}/{combinations_to_process} (全局进度: {global_successful_combinations}/{global_combinations_to_process})")
                                    
                                    # 如果已达到目标数量，提前退出循环
                                    if successful_combinations >= combinations_to_process:
                                        logger.info(f"[全局统计] 当前任务已完成 - 已成功处理 {successful_combinations} 个组合，达到当前任务目标 {combinations_to_process}")
                                        break
                                    
                                    # 如果已达到全局目标数量，也提前退出循环
                                    if global_successful_combinations >= global_combinations_to_process:
                                        logger.info(f"[全局统计] ⚠️ 全局目标已达成 - 已处理 {global_successful_combinations} 个组合，达到目标 {global_combinations_to_process}")
                                        break
                                else:
                                    logger.error(f"  组合 {combo_index+1}: 剪映处理失败: {jy_result.get('error', '未知错误')}")
                                    failed_combinations += 1
                            else:
                                logger.error(f"  组合 {combo_index+1}: 未能选择有效的文件组合")
                                failed_combinations += 1
                        
                        except Exception as e:
                            logger.error(f"  组合 {combo_index+1} 处理时发生错误: {e}", exc_info=True)
                            failed_combinations += 1
                        
                        # 增加组合索引，准备处理下一个组合
                        combo_index += 1
                        
                        # 防止无限循环，设置最大尝试次数为目标数量的5倍
                        if combo_index >= combinations_to_process * 5:
                            logger.warning(f"  已尝试处理 {combo_index} 个组合，超过最大尝试次数 {combinations_to_process * 5}，强制停止处理")
                            break
                    
                    # 检查处理结果
                    if successful_combinations == 0:
                        logger.error(f"  {task_identifier} 的所有组合处理均失败")
                        split_merge_failures += 1
                        raise RuntimeError("所有组合处理均失败")
                    
                    # 更新任务处理结果
                    logger.info(f"  成功处理 {successful_combinations}/{combinations_to_process} 个组合")
                    
                    # 如果启用了删除源文件选项，并且处理成功，则删除原始视频文件
                    if delete_source and successful_combinations > 0:
                        logger.info("  步骤 2c: 选项已启用，准备删除已使用的原始视频文件...")
                        try:
                            # 删除已使用的文件
                            source_files_deleted = 0
                            for video_file in used_video_files:
                                if os.path.exists(video_file):
                                    os.remove(video_file)
                                    logger.info(f"    已删除已使用的视频文件: {video_file}")
                                    source_files_deleted += 1
                                else:
                                    logger.warning(f"    已使用的视频文件已不存在，跳过删除: {video_file}")
                            
                            logger.info(f"    已删除 {source_files_deleted} 个已使用的视频文件（共使用了 {len(used_video_files)} 个文件）")
                        except Exception as e:
                            logger.error(f"    删除已使用的视频文件失败: {e}", exc_info=True)
                    elif not delete_source:
                        logger.info("  步骤 2c: 选项未启用，跳过删除原始视频文件。")
                    else:
                        logger.info("  步骤 2c: 处理未成功，跳过删除原始视频文件。")
                    
                    # 设置用于后续处理的video_paths
                    # 这里我们不再需要split_video_paths，因为已经直接处理了所有组合
                    # 为了保持代码兼容性，设置为空列表
                    split_video_paths = []
                    
                    # 任务成功标记
                    if successful_combinations > 0:
                        processing_success_flag = True
                        # 增加成功任务计数
                        successful_tasks += successful_combinations - 1  # 减1是因为外层循环会再加1
                    
                    # 跳过后续的剪映处理步骤，因为已经在每个组合中单独处理了
                    continue

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
                    logger.info("  步骤 2c(i): 准备删除处理后的临时文件...")
                    if split_video_paths:
                        deleted_split_count = 0
                        logger.info(f"    准备删除 {len(split_video_paths)} 个临时文件...")
                        for split_file in split_video_paths:
                            if split_file != original_video_path:
                                try:
                                    if os.path.exists(split_file):
                                        os.remove(split_file)
                                        logger.info(f"      已删除临时文件: {split_file}")
                                        deleted_split_count += 1
                                    else:
                                         logger.warning(f"      临时文件已不存在，跳过删除: {split_file}")
                                except OSError as remove_split_error:
                                    logger.error(f"      删除临时文件失败: {split_file} - {remove_split_error}", exc_info=True)
                        logger.info(f"    临时文件删除完成: 成功删除 {deleted_split_count} 个。")
                        try:
                            if os.path.exists(split_output_dir) and os.path.isdir(split_output_dir) and not os.listdir(split_output_dir):
                                os.rmdir(split_output_dir)
                                logger.info(f"    已删除空的临时文件目录: {split_output_dir}")
                            elif not os.path.exists(split_output_dir):
                                logger.warning(f"    临时文件目录已不存在，无需删除: {split_output_dir}")
                        except OSError as rmdir_error:
                            logger.warning(f"    删除临时文件目录失败（可能非空或权限问题）: {split_output_dir} - {rmdir_error}")
                    else:
                        logger.info("    未找到临时文件信息，跳过删除临时文件。")

                    if delete_source:
                        logger.info("  步骤 2c(ii): 选项已启用，准备删除原始视频文件...")
                        # 如果是融合模式，并且删除源文件选项启用，需要删除所有用于融合的源文件
                        if process_mode == "merge":
                            try:
                                source_files_deleted = 0
                                for video_file in potential_videos:
                                    if os.path.exists(video_file):
                                        os.remove(video_file)
                                        logger.info(f"    已删除原始视频文件: {video_file}")
                                        source_files_deleted += 1
                                    else:
                                        logger.warning(f"    原始视频文件已不存在，跳过删除: {video_file}")
                                logger.info(f"    已删除 {source_files_deleted} 个原始视频文件。")
                            except Exception as e:
                                logger.error(f"    删除原始视频文件失败: {e}", exc_info=True)
                        else:
                            # 分割模式，仅删除单个源文件
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
                # 错误类型判断已在上面处理 (split_merge_failures, jianying_failures)

            task_duration = time.time() - task_start_time
            status_str = "成功" if processing_success_flag else "失败"
            logger.info(f"--- {task_identifier} 处理结束 [{status_str}] | 耗时: {task_duration:.2f}秒 ---")
            # 循环继续处理下一个任务

        # --- 循环结束后 --- 
        result_summary['tasks_processed'] = successful_tasks
        result_summary['tasks_failed'] = failed_tasks
        result_summary['success'] = (failed_tasks == 0) # 只有所有任务都成功才算整体成功
        
        final_message = f"处理完成: 共找到 {tasks_found} 个素材文件夹, 成功处理 {successful_tasks} 个, 失败 {failed_tasks} 个 (融合失败: {split_merge_failures}, 剪映失败: {jianying_failures})。共生成 {global_successful_combinations} 个视频组合。"
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
    logger.info(f"\n========= 逐个视频{'分割' if process_mode == 'split' else '融合'}处理完成 =========")
    logger.info(f"总素材文件夹数 (扫描到): {tasks_found}")
    logger.info(f"成功处理素材文件夹数: {successful_tasks}")
    logger.info(f"失败处理素材文件夹数: {failed_tasks}")
    if process_mode == "split":
        logger.info(f"  - 因分割失败: {split_merge_failures}")
    else:
        logger.info(f"  - 因融合失败: {split_merge_failures}")
        logger.info(f"[全局统计] 最终总共处理组合数: {global_successful_combinations}/{global_combinations_to_process}")
    logger.info(f"  - 因剪映处理失败: {jianying_failures}")
    logger.info(f"总耗时: {total_time:.2f} 秒")
    if tasks_found > 0:
        avg_time = total_time / tasks_found
        logger.info(f"平均素材文件夹处理耗时: {avg_time:.2f} 秒/文件夹")
    logger.info("====================================")

    # 添加最终统计信息到结果字典
    if process_mode == "merge":
        result_summary['combinations_processed'] = global_successful_combinations
        result_summary['combinations_target'] = global_combinations_to_process
    
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