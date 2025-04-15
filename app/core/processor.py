# app/core/processor.py
# 负责扫描视频文件、生成处理任务以及执行视频切割

import os
import subprocess
import json
import logging
import time # Added for potential future use or detailed logging
import hashlib # 添加用于计算哈希值

# 添加导入刚才创建的数据库模块
try:
    from app.util.merge_database import MergeDatabase
except ImportError:
    # 确保在直接运行此脚本时能正确导入
    import sys
    from pathlib import Path
    root_dir = Path(__file__).resolve().parent.parent.parent
    sys.path.append(str(root_dir))
    from app.util.merge_database import MergeDatabase

logger = logging.getLogger(__name__)

# --- Configuration Constants (Consider making these configurable later) ---
SUPPORTED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv'}
EXPECTED_SEGMENTS = 3 # How many segments to split each video into
# Make GPU options more configurable or disable by default if causing issues
USE_GPU_ACCEL = True # 默认开启GPU加速以提高处理速度
GPU_TYPE = 'nvidia' # 'nvidia', 'intel', 'amd' (Only relevant if USE_GPU_ACCEL is True)

# 添加数据库路径常量
DB_DIR = "db"  # 数据库文件存放目录
DB_FILE = "merge_history.db"  # 数据库文件名

def find_video_tasks(input_folder):
    """
    Scans the input folder for subdirectories and creates a task for each video file found.

    Args:
        input_folder (str): The root input directory containing subfolders.

    Returns:
        list: A list of dictionaries, where each dictionary represents a video task.
              Each task dict contains:
              - 'original_path': Absolute path to the source video file.
              - 'subfolder_name': Name of the subfolder the video was found in.
              - 'output_base_name': Base name of the video file (without extension).
    """
    tasks = []
    logger.info(f"开始扫描输入文件夹以查找独立的视频任务: {input_folder}")
    if not input_folder or not os.path.isdir(input_folder):
        logger.error(f"输入文件夹路径无效或不存在: '{input_folder}'")
        return tasks

    try:
        # Iterate through items in the input folder (expecting subdirectories)
        for subfolder_name in os.listdir(input_folder):
            subfolder_path = os.path.join(input_folder, subfolder_name)

            if os.path.isdir(subfolder_path):
                logger.info(f"扫描子文件夹: {subfolder_name}")
                try:
                    # Iterate through files within the subdirectory
                    for filename in os.listdir(subfolder_path):
                        file_path = os.path.join(subfolder_path, filename)
                        if os.path.isfile(file_path):
                            _, ext = os.path.splitext(filename)
                            if ext.lower() in SUPPORTED_VIDEO_EXTENSIONS:
                                base_name = os.path.splitext(filename)[0]
                                task = {
                                    'original_path': file_path,
                                    'subfolder_name': subfolder_name,
                                    'output_base_name': base_name
                                }
                                tasks.append(task)
                                logger.info(f"  找到任务: {filename} (属于子文件夹: {subfolder_name})")
                except PermissionError:
                     logger.warning(f"没有权限访问子文件夹 '{subfolder_name}' 的内容，跳过此文件夹。")
                     continue
                except Exception as list_subdir_error:
                     logger.warning(f"访问子文件夹 '{subfolder_name}' 内容时出错: {list_subdir_error}，跳过此文件夹。")
                     continue
            else:
                 logger.debug(f"跳过非目录项目 '{subfolder_name}'")

    except PermissionError:
         logger.error(f"没有权限访问输入文件夹: {input_folder}")
    except Exception as e:
        logger.exception(f"扫描文件夹以查找任务时发生意外错误")

    if not tasks:
        logger.info("扫描完成，未在任何子文件夹中找到支持格式的视频文件任务。")
    else:
        logger.info(f"扫描完成，共找到 {len(tasks)} 个独立的视频处理任务。")

    return tasks

# --- FFmpeg Helper Functions ---

def get_video_duration(video_path):
    """使用 ffprobe 获取视频时长 (秒)"""
    # Ensure video_path exists before calling ffprobe
    if not os.path.exists(video_path):
        logger.error(f"get_video_duration: 视频文件不存在: {video_path}")
        return None # Return None instead of raising an error here

    command = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', video_path
    ]
    try:
        # Ensure shell=False for security and proper argument handling
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore', shell=False)
        data = json.loads(result.stdout)
        duration = float(data['format']['duration'])
        logger.debug(f"获取 '{os.path.basename(video_path)}' 时长: {duration:.2f} 秒")
        return duration
    except FileNotFoundError:
        logger.error("ffprobe 命令未找到。请确保 FFmpeg 已安装并添加到系统 PATH。")
        return None # Return None to indicate failure
    except subprocess.CalledProcessError as e:
        logger.error(f"ffprobe 执行失败: {e}")
        stderr_output = e.stderr.strip() if e.stderr else "No stderr output"
        logger.error(f"ffprobe 输出: {stderr_output}")
        return None # Return None to indicate failure
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        logger.error(f"解析 ffprobe 输出失败: {e}")
        logger.error(f"ffprobe stdout received: {result.stdout if 'result' in locals() else 'N/A'}")
        return None # Return None to indicate failure
    except Exception as e:
        logger.exception(f"获取视频时长时发生未知错误: {video_path}")
        return None # Return None on unknown error

def split_video_ffmpeg(input_path, output_folder, num_segments=EXPECTED_SEGMENTS, volume_level=100):
    """
    使用 ffmpeg 将单个视频平均切割成指定数量的片段。

    Args:
        input_path (str): Path to the source video file.
        output_folder (str): Directory to save the split segments.
        num_segments (int): The desired number of segments.
        volume_level (int): 音量级别，范围0-100，默认100表示保持原始音量。

    Returns:
        list: A list of absolute paths to the generated segment files, or None if splitting fails.
    """
    # Skip splitting if only 1 segment is requested
    if num_segments <= 1:
        logger.info(f"请求切割成 {num_segments} 段，无需执行切割，将直接使用原始文件。")
        if not os.path.exists(input_path):
            logger.error(f"请求使用的原始文件不存在: {input_path}")
            return None
        return [input_path] # Return the original path in a list

    output_paths = []
    base_name, ext = os.path.splitext(os.path.basename(input_path))
    # Ensure output folder exists
    if not os.path.exists(output_folder):
        try:
            os.makedirs(output_folder)
            logger.info(f"为切割文件创建输出文件夹: {output_folder}")
        except OSError as e:
            logger.error(f"无法创建切割输出文件夹 '{output_folder}': {e}")
            return None
    elif not os.path.isdir(output_folder):
         logger.error(f"指定的切割输出路径不是文件夹: '{output_folder}'")
         return None

    try:
        duration = get_video_duration(input_path)
        if duration is None:
            logger.error(f"无法获取视频 '{os.path.basename(input_path)}' 的时长，无法进行切割。")
            return None
    except Exception as e:
        # This shouldn't happen if get_video_duration handles its exceptions
        logger.error(f"获取视频时长时发生意外错误，跳过切割 '{os.path.basename(input_path)}': {e}")
        return None

    if duration <= 0:
        logger.error(f"视频 '{os.path.basename(input_path)}' 时长为 0 或无效 ({duration})，无法切割。")
        return None

    segment_duration = duration / num_segments
    logger.info(f"准备将 '{base_name}{ext}' ({duration:.2f}s) 切割成 {num_segments} 段，每段约 {segment_duration:.2f}s")

    # 处理音量设置
    normalized_volume = max(0, min(100, volume_level)) / 100.0
    volume_filter = []
    if volume_level != 100:
        volume_filter = ['-af', f'volume={normalized_volume}']
        logger.info(f"  应用音量调整: {volume_level}% (归一化值: {normalized_volume:.2f})")

    if segment_duration < 0.1:
        logger.warning(f"计算出的切割片段时长 ({segment_duration:.3f}s) 非常短，可能导致 ffmpeg 出错或产生无效片段。")

    all_segments_successful = True
    for i in range(num_segments):
        start_time = i * segment_duration
        current_segment_duration = segment_duration

        output_filename = f"{base_name}_part{i+1}{ext}"
        output_path = os.path.join(output_folder, output_filename)

        command = ['ffmpeg', '-y']

        hwaccel_used = False
        if USE_GPU_ACCEL:
            hwaccel_options = []
            if GPU_TYPE == 'nvidia': hwaccel_options = ['-hwaccel', 'cuda']
            elif GPU_TYPE == 'intel': hwaccel_options = ['-hwaccel', 'qsv', '-qsv_device', '/dev/dri/renderD128']
            elif GPU_TYPE == 'amd': hwaccel_options = ['-hwaccel', 'dxva2']

            if hwaccel_options:
                command = ['ffmpeg', '-y'] + hwaccel_options
                logger.info(f"  尝试使用 GPU 加速解码: {' '.join(hwaccel_options)}")
                hwaccel_used = True
            else:
                logger.warning(f"  配置了 USE_GPU_ACCEL=True 但 GPU_TYPE '{GPU_TYPE}' 不支持或未配置正确的 hwaccel 选项。")

        command.extend(['-i', input_path])
        command.extend(['-ss', str(start_time)])
        command.extend(['-t', str(current_segment_duration)])

        # 添加音量滤镜
        if volume_filter:
            command.extend(volume_filter)

        codec_params = []
        encoder_used = "libx264 (软件编码)"
        if hwaccel_used and GPU_TYPE == 'nvidia':
            encoder_used = "h264_nvenc (硬件编码)"
            codec_params = ['-c:v', 'h264_nvenc', '-preset', 'p2', '-tune', 'hq', '-rc', 'vbr', '-cq', '23', '-b:v', '6M', '-maxrate', '10M', '-bufsize', '10M', '-spatial-aq', '1', '-temporal-aq', '1', '-profile:v', 'high']
        elif hwaccel_used and GPU_TYPE == 'intel':
            encoder_used = "h264_qsv (硬件编码)"
            codec_params = ['-c:v', 'h264_qsv', '-preset', 'medium', '-b:v', '6M', '-maxrate', '10M']
        else:
            if USE_GPU_ACCEL and not hwaccel_used:
                 logger.warning(f"回退到 libx264 软件编码。") # Warning already logged above
            elif USE_GPU_ACCEL and hwaccel_used:
                 logger.warning(f"使用了 '{GPU_TYPE}' 加速解码，但编码器不支持或未配置硬件编码，回退到 libx264 软件编码。")

            codec_params = ['-c:v', 'libx264', '-preset', 'medium', '-crf', '23', '-b:v', '6M', '-maxrate', '10M', '-bufsize', '10M', '-profile:v', 'high']

        command.extend(codec_params)
        command.extend(['-c:a', 'aac', '-b:a', '128k'])
        command.extend(['-movflags', '+faststart'])
        command.append(output_path)

        # 在日志中显示音量信息
        volume_info = f"音量: {volume_level}%" if volume_level != 100 else ""
        volume_display = f", {volume_info}" if volume_info else ""
        logger.info(f"  执行切割命令 (第 {i+1}/{num_segments} 段, 编码器: {encoder_used}{volume_display}): {' '.join(command)}")
        
        try:
            process_result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore', shell=False)
            if process_result.stdout:
                 logger.debug(f"    ffmpeg stdout:\n{process_result.stdout.strip()}")
            if process_result.stderr:
                 logger.debug(f"    ffmpeg stderr:\n{process_result.stderr.strip()}")

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                output_paths.append(output_path)
                logger.info(f"    成功生成切割片段: {output_filename}")
            else:
                logger.error(f"    ffmpeg 命令执行成功但未找到有效输出文件: {output_filename} (可能文件为空或未生成)")
                all_segments_successful = False
                break
        except FileNotFoundError:
            logger.error("ffmpeg 命令未找到。请确保 FFmpeg 已安装并添加到系统 PATH。")
            all_segments_successful = False # Mark as failure
            break # Cannot continue without ffmpeg
        except subprocess.CalledProcessError as e:
            logger.error(f"ffmpeg 切割第 {i+1} 段失败: {e}")
            stderr_output = e.stderr.strip() if e.stderr else "No stderr output"
            logger.error(f"ffmpeg 输出: {stderr_output}")
            all_segments_successful = False
            break
        except Exception as e:
            logger.exception(f"切割第 {i+1} 段时发生未知错误")
            all_segments_successful = False
            break

    if all_segments_successful and len(output_paths) == num_segments:
        logger.info(f"成功切割 '{os.path.basename(input_path)}' 为 {num_segments} 段。")
        return output_paths
    else:
        logger.error(f"未能成功切割 '{os.path.basename(input_path)}' 的所有片段 (成功 {len(output_paths)}/{num_segments})。请检查日志。")
        # Clean up any partially created segments if splitting failed midway
        logger.info("尝试清理可能已生成的切割片段...")
        cleaned_count = 0
        for temp_path in output_paths: # Clean up successfully created ones before failure
             if os.path.exists(temp_path):
                  try:
                       os.remove(temp_path)
                       cleaned_count += 1
                  except OSError as e:
                       logger.warning(f"清理部分片段失败: {temp_path} - {e}")
        # Also try cleaning the last failed one if path exists
        if 'output_path' in locals() and os.path.exists(output_path) and output_path not in output_paths:
             try:
                  os.remove(output_path)
                  cleaned_count += 1
             except OSError as e:
                  logger.warning(f"清理失败片段失败: {output_path} - {e}")
        logger.info(f"部分片段清理完成: {cleaned_count} 个。")
        return None # Indicate failure 

def merge_videos_ffmpeg(input_paths, output_file, volume_level=100, use_cache=True):
    """
    使用 ffmpeg 将多个视频文件按顺序融合成一个视频文件。
    
    增加缓存支持，避免重复合并相同的视频文件组合。

    Args:
        input_paths (list): 要融合的视频文件路径列表
        output_file (str): 融合后的输出文件路径
        volume_level (int): 音量级别，范围0-100，默认100表示保持原始音量。
        use_cache (bool): 是否使用缓存，默认为True

    Returns:
        str: 成功时返回输出文件路径，失败时返回None
    """
    if not input_paths or len(input_paths) == 0:
        logger.error("未提供要融合的视频文件路径")
        return None
    
    # 检查每个输入文件是否存在
    for video_path in input_paths:
        if not os.path.exists(video_path):
            logger.error(f"要融合的视频文件不存在: {video_path}")
            return None
    
    # 确保输出目录存在
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            logger.info(f"为融合文件创建输出文件夹: {output_dir}")
        except OSError as e:
            logger.error(f"无法创建融合输出文件夹 '{output_dir}': {e}")
            return None
    
    # 初始化数据库
    db_path = os.path.join(DB_DIR, DB_FILE)
    try:
        # 确保数据库目录存在
        if not os.path.exists(DB_DIR):
            os.makedirs(DB_DIR)
            logger.info(f"创建数据库目录: {DB_DIR}")
        
        # 从缓存中检查是否已有相同的合并任务
        if use_cache:
            with MergeDatabase(db_path) as db:
                if db.is_exact_combination_used(input_paths):
                    # 查找之前的输出文件
                    cursor = db.conn.cursor()
                    task_hash = db.generate_task_hash(input_paths)
                    cursor.execute('SELECT output_file FROM merge_tasks WHERE task_hash = ?', (task_hash,))
                    result = cursor.fetchone()
                    
                    if result and os.path.exists(result[0]):
                        cached_output = result[0]
                        logger.info(f"发现缓存的融合结果: {os.path.basename(cached_output)}")
                        
                        # 如果输出文件路径不同，但希望使用缓存，需要复制文件
                        if cached_output != output_file:
                            import shutil
                            try:
                                shutil.copy2(cached_output, output_file)
                                logger.info(f"复制缓存文件到请求的输出路径: {os.path.basename(output_file)}")
                                return output_file
                            except Exception as e:
                                logger.error(f"复制缓存文件失败: {e}")
                                # 继续执行合并操作，不使用缓存
                        else:
                            return cached_output
                    else:
                        logger.warning("缓存记录存在但文件已丢失，将重新执行合并")
    except Exception as e:
        logger.error(f"初始化或检查合并缓存失败: {e}")
        # 继续执行，不使用缓存
    
    # 创建临时文件列表
    temp_list_file = os.path.join(output_dir, "temp_file_list.txt")
    try:
        with open(temp_list_file, 'w', encoding='utf-8') as f:
            for video_path in input_paths:
                # 修复f-string中反斜杠问题
                path_fixed = video_path.replace('\\', '/')
                f.write(f"file '{path_fixed}'\n")
        logger.info(f"已创建临时文件列表: {temp_list_file}，包含 {len(input_paths)} 个视频文件")
    except Exception as e:
        logger.error(f"创建临时文件列表失败: {e}")
        return None
    
    # 处理音量设置
    normalized_volume = max(0, min(100, volume_level)) / 100.0
    volume_filter = []
    if volume_level != 100:
        volume_filter = ['-af', f'volume={normalized_volume}']
        logger.info(f"应用音量调整: {volume_level}% (归一化值: {normalized_volume:.2f})")
    
    # 构建融合命令
    command = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', temp_list_file]
    
    hwaccel_used = False
    if USE_GPU_ACCEL:
        hwaccel_options = []
        if GPU_TYPE == 'nvidia': hwaccel_options = ['-hwaccel', 'cuda']
        elif GPU_TYPE == 'intel': hwaccel_options = ['-hwaccel', 'qsv', '-qsv_device', '/dev/dri/renderD128']
        elif GPU_TYPE == 'amd': hwaccel_options = ['-hwaccel', 'dxva2']

        if hwaccel_options:
            command = ['ffmpeg', '-y'] + hwaccel_options + ['-f', 'concat', '-safe', '0', '-i', temp_list_file]
            logger.info(f"尝试使用 GPU 加速解码: {' '.join(hwaccel_options)}")
            hwaccel_used = True
        else:
            logger.warning(f"配置了 USE_GPU_ACCEL=True 但 GPU_TYPE '{GPU_TYPE}' 不支持或未配置正确的 hwaccel 选项。")
    
    # 添加音量滤镜
    if volume_filter:
        command.extend(volume_filter)
    
    # 设置视频编码参数
    codec_params = []
    encoder_used = "libx264 (软件编码)"
    if hwaccel_used and GPU_TYPE == 'nvidia':
        encoder_used = "h264_nvenc (硬件编码)"
        codec_params = ['-c:v', 'h264_nvenc', '-preset', 'p2', '-tune', 'hq', '-rc', 'vbr', '-cq', '23', '-b:v', '6M', '-maxrate', '10M', '-bufsize', '10M', '-spatial-aq', '1', '-temporal-aq', '1', '-profile:v', 'high']
    elif hwaccel_used and GPU_TYPE == 'intel':
        encoder_used = "h264_qsv (硬件编码)"
        codec_params = ['-c:v', 'h264_qsv', '-preset', 'medium', '-b:v', '6M', '-maxrate', '10M']
    else:
        if USE_GPU_ACCEL and not hwaccel_used:
            logger.warning(f"回退到 libx264 软件编码。")
        elif USE_GPU_ACCEL and hwaccel_used:
            logger.warning(f"使用了 '{GPU_TYPE}' 加速解码，但编码器不支持或未配置硬件编码，回退到 libx264 软件编码。")

        codec_params = ['-c:v', 'libx264', '-preset', 'medium', '-crf', '23', '-b:v', '6M', '-maxrate', '10M', '-bufsize', '10M', '-profile:v', 'high']
    
    command.extend(codec_params)
    command.extend(['-c:a', 'aac', '-b:a', '128k'])
    command.extend(['-movflags', '+faststart'])
    command.append(output_file)
    
    # 在日志中显示音量信息
    volume_info = f"音量: {volume_level}%" if volume_level != 100 else ""
    volume_display = f", {volume_info}" if volume_info else ""
    logger.info(f"执行融合命令 (融合 {len(input_paths)} 个视频文件, 编码器: {encoder_used}{volume_display}): {' '.join(command)}")
    
    merge_success = False
    try:
        process_result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore', shell=False)
        if process_result.stdout:
            logger.debug(f"ffmpeg stdout:\n{process_result.stdout.strip()}")
        if process_result.stderr:
            logger.debug(f"ffmpeg stderr:\n{process_result.stderr.strip()}")
        
        # 清理临时文件
        try:
            if os.path.exists(temp_list_file):
                os.remove(temp_list_file)
                logger.debug(f"已删除临时文件列表: {temp_list_file}")
        except OSError as e:
            logger.warning(f"删除临时文件列表失败: {e}")
        
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            logger.info(f"成功融合 {len(input_paths)} 个视频文件到: {os.path.basename(output_file)}")
            merge_success = True
        else:
            logger.error(f"ffmpeg 命令执行成功但未找到有效输出文件: {os.path.basename(output_file)} (可能文件为空或未生成)")
            return None
    except FileNotFoundError:
        logger.error("ffmpeg 命令未找到。请确保 FFmpeg 已安装并添加到系统 PATH。")
        return None
    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg 融合视频失败: {e}")
        stderr_output = e.stderr.strip() if e.stderr else "No stderr output"
        logger.error(f"ffmpeg 输出: {stderr_output}")
        return None
    except Exception as e:
        logger.exception(f"融合视频时发生未知错误")
        return None
    finally:
        # 确保临时文件被清理
        if os.path.exists(temp_list_file):
            try:
                os.remove(temp_list_file)
                logger.debug(f"已删除临时文件列表: {temp_list_file}")
            except OSError:
                pass
    
    # 如果合并成功，将记录添加到数据库
    if merge_success:
        try:
            with MergeDatabase(db_path) as db:
                db.add_merge_task(input_paths, output_file)
                logger.info(f"已将融合任务记录到数据库")
        except Exception as e:
            logger.error(f"记录融合任务到数据库失败: {e}")
    
    return output_file if merge_success else None

def find_available_combination(videos_dir, required_count=3, base_prefix=None):
    """
    在给定目录中查找尚未使用过的视频组合
    
    Args:
        videos_dir (str): 视频文件目录
        required_count (int): 需要的视频数量
        base_prefix (str, optional): 基础前缀，如果提供，将仅选择该前缀开头的文件
        
    Returns:
        list: 未使用过的视频文件路径列表，如果未找到则返回空列表
    """
    if not os.path.exists(videos_dir) or not os.path.isdir(videos_dir):
        logger.error(f"视频目录不存在或无效: {videos_dir}")
        return []
    
    # 获取目录中所有视频文件
    video_files = []
    for filename in os.listdir(videos_dir):
        file_path = os.path.join(videos_dir, filename)
        if os.path.isfile(file_path):
            _, ext = os.path.splitext(filename)
            if ext.lower() in SUPPORTED_VIDEO_EXTENSIONS:
                # 如果指定了前缀，则只选择匹配前缀的文件
                if base_prefix is None or filename.startswith(base_prefix):
                    video_files.append(file_path)
    
    if len(video_files) < required_count:
        logger.warning(f"可用视频文件数量 ({len(video_files)}) 少于所需数量 ({required_count})")
        return []
    
    # 初始化数据库
    db_path = os.path.join(DB_DIR, DB_FILE)
    try:
        with MergeDatabase(db_path) as db:
            # 获取使用频率最低的文件
            least_used_files = db.get_least_used_files(video_files, limit=required_count * 2)
            
            # 尝试从使用频率最低的文件中找出未使用过的组合
            unused_combinations = db.find_unused_combinations(least_used_files, required_count)
            
            if unused_combinations:
                selected_combo = unused_combinations[0]  # 选择第一个未使用过的组合
                logger.info(f"找到未使用过的视频组合: {[os.path.basename(f) for f in selected_combo]}")
                return selected_combo
            else:
                # 如果没有找到未使用过的组合，尝试从所有文件中查找
                unused_combinations = db.find_unused_combinations(video_files, required_count)
                if unused_combinations:
                    selected_combo = unused_combinations[0]
                    logger.info(f"从所有文件中找到未使用过的视频组合: {[os.path.basename(f) for f in selected_combo]}")
                    return selected_combo
                else:
                    logger.warning(f"未找到未使用过的视频组合")
                    # 如果没有未使用过的组合，则返回使用频率最低的文件
                    least_used = db.get_least_used_files(video_files, limit=required_count)
                    if len(least_used) == required_count:
                        logger.info(f"返回使用频率最低的文件组合: {[os.path.basename(f) for f in least_used]}")
                        return least_used
                    else:
                        logger.warning(f"无法获取足够的视频文件")
                        return []
    except Exception as e:
        logger.error(f"查找可用组合时出错: {e}")
        # 如果数据库操作失败，随机选择文件
        import random
        if len(video_files) >= required_count:
            selected_files = random.sample(video_files, required_count)
            logger.info(f"随机选择视频组合: {[os.path.basename(f) for f in selected_files]}")
            return selected_files
        return [] 