# app/core/processor.py
# 负责扫描视频文件、生成处理任务以及执行视频切割

import os
import subprocess
import json
import logging
import time # Added for potential future use or detailed logging

logger = logging.getLogger(__name__)

# --- Configuration Constants (Consider making these configurable later) ---
SUPPORTED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv'}
EXPECTED_SEGMENTS = 3 # How many segments to split each video into
# Make GPU options more configurable or disable by default if causing issues
USE_GPU_ACCEL = False # Default to False for broader compatibility
GPU_TYPE = 'nvidia' # 'nvidia', 'intel', 'amd' (Only relevant if USE_GPU_ACCEL is True)

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

def split_video_ffmpeg(input_path, output_folder, num_segments=EXPECTED_SEGMENTS):
    """
    使用 ffmpeg 将单个视频平均切割成指定数量的片段。

    Args:
        input_path (str): Path to the source video file.
        output_folder (str): Directory to save the split segments.
        num_segments (int): The desired number of segments.

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
            return None # Indicate splitting failure
    except Exception as e:
        # This shouldn't happen if get_video_duration handles its exceptions
        logger.error(f"获取视频时长时发生意外错误，跳过切割 '{os.path.basename(input_path)}': {e}")
        return None

    if duration <= 0:
        logger.error(f"视频 '{os.path.basename(input_path)}' 时长为 0 或无效 ({duration})，无法切割。")
        return None

    segment_duration = duration / num_segments
    logger.info(f"准备将 '{base_name}{ext}' ({duration:.2f}s) 切割成 {num_segments} 段，每段约 {segment_duration:.2f}s")

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

        logger.info(f"  执行切割命令 (第 {i+1}/{num_segments} 段, 编码器: {encoder_used}): {' '.join(command)}")
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