# app/util/jianying.py
# 包含与剪映交互的核心逻辑

import os
import time
import pyJianYingDraft as draft
from pyJianYingDraft import Export_resolution, Export_framerate, Extend_mode, Shrink_mode
from pyJianYingDraft.time_util import Timerange, SEC
import uiautomation as uia
from collections import defaultdict
import datetime
import shutil
import logging # 导入日志模块
import math
import uuid

# 导入独立的导出逻辑模块
from app.util.jianying_export import Fast_Jianying_Controller
# 导入BGM处理模块
from app.util.bgm_handler import process_bgm, validate_bgm_volume

# 获取该模块的 logger 实例
logger = logging.getLogger(__name__)

# 辅助函数：设置片段音量
def set_segment_volume(segment, volume, segment_idx=None, context=""):
    """
    安全地设置片段音量并处理相关关键帧

    Args:
        segment: 需要设置音量的片段对象
        volume (float): 目标音量值，范围0.0-1.0
        segment_idx (int, optional): 片段索引，用于日志
        context (str, optional): 上下文描述，用于日志
    
    Returns:
        bool: 设置是否成功
    """
    prefix = f"[{context}]" if context else ""
    segment_desc = f"片段 {segment_idx}" if segment_idx is not None else "片段"
    
    try:
        # 获取当前音量
        old_volume = segment.volume if hasattr(segment, 'volume') else 1.0
        
        # 设置新音量
        segment.volume = volume
        
        # 验证设置是否成功
        if segment.volume == volume:
            logger.info(f"{prefix} 成功设置{segment_desc}音量从 {old_volume:.2f} 到 {volume:.2f}")
            
            # 处理可能存在的音量关键帧
            if hasattr(segment, 'common_keyframes'):
                volume_keyframes = [kf for kf in segment.common_keyframes 
                                  if hasattr(kf, 'keyframe_property') and 
                                     getattr(kf, 'keyframe_property', None) == draft.Keyframe_property.volume]
                
                if volume_keyframes:
                    logger.warning(f"{prefix} 检测到{segment_desc}存在 {len(volume_keyframes)} 个音量关键帧，尝试清除...")
                    # 移除音量关键帧
                    segment.common_keyframes = [kf for kf in segment.common_keyframes 
                                             if not (hasattr(kf, 'keyframe_property') and 
                                                    getattr(kf, 'keyframe_property', None) == draft.Keyframe_property.volume)]
                    logger.info(f"{prefix} 已清除{segment_desc}的音量关键帧")
            
            return True
        else:
            logger.warning(f"{prefix} {segment_desc}音量设置可能未生效: 期望 {volume:.2f}，实际为 {segment.volume:.2f}")
            return False
    except Exception as e:
        logger.error(f"{prefix} 设置{segment_desc}音量时出错: {e}")
        return False

# 全局配置，未来可以考虑放入配置文件或通过参数传递
CUSTOMIZE_EXPORT = False # 是否自定义导出（可以考虑做成参数）

# --- Core Processing Function ---

def process_videos(video_paths,
                   draft_name,
                   draft_folder_path,
                   export_video=False,
                   export_path=None,
                   export_filename=None,
                   original_duration_seconds=None,
                   keep_bgm=True,
                   bgm_loop=True,
                   bgm_volume=100,  # 新增参数：BGM音量(0-100)
                   main_track_volume=100):  # 新增参数：主轨道音量(0-100)
    """
    处理单个视频批次（假设视频路径已准备好）：加载模板，替换片段，保存，导出。
    Now expects video_paths to be the final list (likely split segments).
    The draft duration adjustment based on original_duration_seconds is disabled.

    Args:
        video_paths (list): 最终用于替换的视频文件绝对路径列表 (通常是切割后的片段)。
        draft_name (str): 要使用的模板草稿的名称。
        draft_folder_path (str): 剪映草稿库的路径。
        export_video (bool): 是否导出视频。
        export_path (str, optional): 导出视频的目标文件夹路径。
        export_filename (str, optional): 导出视频的文件名。
        original_duration_seconds (float, optional): 原始视频的时长（秒）。(当前未使用)
        keep_bgm (bool, optional): 是否保留模板中的BGM音频轨道，默认为True。
        bgm_loop (bool, optional): 当视频长度大于BGM时，是否循环播放BGM，默认为True。
        bgm_volume (int, optional): BGM音量，取值范围0-100，默认为100（原始音量）。
        main_track_volume (int, optional): 主轨道（视频片段）音量，取值范围0-100，默认为100（原始音量）。

    Returns:
        dict: 包含处理结果的字典，格式为 {"success": bool, "error": str|None}
    """
    logger.info(f"--- 开始处理剪映模板: {draft_name} ---")
    logger.info(f"  使用视频片段 ({len(video_paths)}): {', '.join(os.path.basename(p) for p in video_paths)}")
    logger.info(f"  草稿库路径: {draft_folder_path}")
    logger.info(f"  保留BGM: {keep_bgm}, BGM循环: {bgm_loop}, BGM音量: {bgm_volume}%, 主轨道音量: {main_track_volume}%")
    export_file_path = None
    if export_video:
        logger.info(f"  导出设置: 启用")
        if not export_path or not export_filename:
            logger.error("需要导出视频，但未提供 export_path 或 export_filename。")
            return {"success": False, "error": "导出路径或文件名缺失"}
        export_file_path = os.path.join(export_path, export_filename)
        logger.info(f"    导出目标: {export_file_path}")
        # Ensure target dir for export exists before Jianying tries to write there
        try:
            os.makedirs(export_path, exist_ok=True)
            logger.debug(f"确认导出目录存在或已创建: {export_path}")
        except OSError as e:
            logger.error(f"无法创建导出目录 '{export_path}': {e}", exc_info=True)
            return {"success": False, "error": f"创建导出目录失败: {export_path}"}
    else:
        logger.info(f"  导出设置: 禁用")

    result = {"success": False, "error": None}
    script = None

    try:
        # 1. 初始化 Draft_folder
        logger.debug("初始化草稿文件夹管理器...")
        draft_folder = draft.Draft_folder(draft_folder_path)
        available_drafts = draft_folder.list_drafts()
        if draft_name not in available_drafts:
             logger.error(f"指定的模板草稿 '{draft_name}' 在草稿库 '{draft_folder_path}' 中未找到。可用草稿: {available_drafts}")
             raise draft.exceptions.DraftNotFound(f"模板草稿 '{draft_name}' 不存在")
        logger.debug(f"可用草稿: {available_drafts}")

        # 2. 加载模板草稿
        logger.info(f"加载模板草稿: {draft_name}")
        load_start = time.time()
        script = draft_folder.load_template(draft_name)
        logger.info(f"模板加载成功，耗时: {time.time() - load_start:.2f}秒")

        # 3. 创建视频素材对象 (使用传入的 video_paths)
        logger.info("创建视频素材对象...")
        mat_start = time.time()
        video_materials = []
        for video_path in video_paths:
            if not os.path.exists(video_path):
                 logger.error(f"用于替换的视频文件不存在: {video_path}")
                 raise FileNotFoundError(f"预期存在的视频片段未找到: {video_path}")
            logger.debug(f"  创建素材对象: {os.path.basename(video_path)}")
            video_materials.append(draft.Video_material(video_path))
        logger.info(f"成功为 {len(video_materials)} 个视频片段创建素材对象，耗时: {time.time() - mat_start:.2f}秒")

        # 4. 获取视频轨道
        logger.info("获取第一个视频轨道...")
        track_start = time.time()
        try:
            video_track = script.get_imported_track(draft.Track_type.video, index=0)
            if not video_track:
                 # This case might happen if get_imported_track returns None on failure
                 logger.error(f"无法获取模板草稿 '{draft_name}' 中索引为 0 的视频轨道 (返回 None)。")
                 raise IndexError(f"模板草稿 '{draft_name}' 中没有视频轨道或获取失败。")
        except IndexError:
             logger.error(f"模板草稿 '{draft_name}' 中找不到索引为 0 的视频轨道 (IndexError)。")
             raise # Re-raise the original IndexError
        except Exception as e:
             # Catch other potential errors from get_imported_track
             logger.error(f"获取模板 '{draft_name}' 视频轨道时发生错误: {e}", exc_info=True)
             raise
        logger.info(f"视频轨道获取成功，耗时: {time.time() - track_start:.2f}秒")

        # 5. 替换视频片段
        num_segments_to_replace = len(video_materials)
        actual_segments_in_template = 0 # Default value
        try:
            # Ensure video_track and video_track.segments are valid before accessing length
            if video_track and hasattr(video_track, 'segments') and video_track.segments is not None:
                 actual_segments_in_template = len(video_track.segments)
            else:
                 logger.warning("无法访问模板视频轨道的片段列表 (video_track.segments)。")
                 # Decide how to handle this - raise error or try to proceed assuming 0?
                 # Let's raise for now, as replacing into a non-existent list is problematic
                 raise ValueError("模板视频轨道的片段列表无效或无法访问。")

            logger.info(f"模板轨道现有 {actual_segments_in_template} 个片段，需要用 {num_segments_to_replace} 个新片段替换。")
            segments_to_iterate = min(actual_segments_in_template, num_segments_to_replace)
            if actual_segments_in_template < num_segments_to_replace:
                 logger.warning(f"警告：模板轨道片段数 ({actual_segments_in_template}) 少于提供的视频片段数 ({num_segments_to_replace})！将只替换前 {segments_to_iterate} 个片段。")
            elif actual_segments_in_template > num_segments_to_replace:
                 logger.warning(f"警告：模板轨道片段数 ({actual_segments_in_template}) 多于提供的视频片段数 ({num_segments_to_replace})。将只替换前 {segments_to_iterate} 个片段，后续片段将保留原样。")
        except Exception as e:
             logger.warning(f"无法准确获取模板轨道片段数 ({e})，将尝试替换前 {num_segments_to_replace} 个片段。")
             segments_to_iterate = num_segments_to_replace

        logger.info(f"准备替换模板中的 {segments_to_iterate} 个视频片段...")
        replace_start_time = time.time()
        
        # 计算主轨道音量
        normalized_main_volume = max(0, min(100, main_track_volume)) / 100.0
        logger.info(f"主轨道音量设置为: {main_track_volume}% (归一化值: {normalized_main_volume:.2f})")
        
        for i in range(segments_to_iterate):
            segment_log_name = f"模板片段索引 {i}"
            video_file_basename = os.path.basename(video_paths[i])
            logger.info(f"  替换 {segment_log_name} -> {video_file_basename}")
            try:
                replace_seg_start = time.time()
                
                # 替换视频片段
                script.replace_material_by_seg(
                    video_track,
                    i,
                    video_materials[i],
                    handle_shrink=Shrink_mode.cut_tail_align, # 片段缩短时，切尾并前移后续片段
                    handle_extend=Extend_mode.push_tail # 片段延长时，推后结束点及后续片段
                )
                
                # 设置片段音量
                if normalized_main_volume != 1.0 and i < len(video_track.segments):
                    set_segment_volume(
                        video_track.segments[i], 
                        normalized_main_volume, 
                        segment_idx=i, 
                        context="替换后立即设置"
                    )
                
                logger.debug(f"    替换耗时: {time.time() - replace_seg_start:.2f}秒")
            except IndexError:
                 error_msg = f"尝试替换索引为 {i} 的片段时出错。模板草稿 '{draft_name}' 的视频轨道可能没有足够的片段 ({actual_segments_in_template})。"
                 logger.error(error_msg)
                 raise IndexError(error_msg) # Re-raise specific error
            except Exception as replace_err:
                 logger.error(f"替换 {segment_log_name} ({video_file_basename}) 时发生错误: {replace_err}", exc_info=True)
                 raise # Re-raise general error

        replace_time = time.time() - replace_start_time
        logger.info(f"视频片段替换完成，耗时: {replace_time:.2f}秒.")
        
        # 所有片段替换完成后，再次设置所有片段的音量（确保音量设置生效）
        if normalized_main_volume != 1.0:
            logger.info(f"所有片段替换完成，开始应用主轨道音量设置: {main_track_volume}%")
            try:
                segments_updated = 0
                segments_total = len(video_track.segments)
                
                for i in range(segments_total):
                    if set_segment_volume(
                        video_track.segments[i], 
                        normalized_main_volume, 
                        segment_idx=i, 
                        context="替换完成后批量设置"
                    ):
                        segments_updated += 1
                
                # 添加确认日志
                logger.info(f"已更新 {segments_updated}/{segments_total} 个视频片段的音量为 {main_track_volume}%")
            except Exception as e:
                logger.error(f"应用主轨道音量设置时发生错误: {e}", exc_info=True)

        # 6. 获取新视频轨道时长并处理BGM
        video_end_time = 0
        try:
            if video_track and hasattr(video_track, 'end_time'):
                video_end_time = video_track.end_time
                logger.info(f"计算得到的视频轨道实际结束时间: {video_end_time} 微秒 ({video_end_time / 1_000_000:.2f} 秒)")
                
                # 使用专门的BGM处理模块处理BGM
                bgm_result = process_bgm(
                    script=script,
                    video_end_time=video_end_time,
                    keep_bgm=keep_bgm,
                    bgm_loop=bgm_loop,
                    bgm_volume=bgm_volume
                )
                
                # 获取处理后的音频轨道和最大轨道时长
                audio_tracks = bgm_result.get("audio_tracks", [])
                max_track_end_time = bgm_result.get("max_track_end_time", video_end_time)
                
                # 更新草稿总时长
                if hasattr(script, 'content') and isinstance(script.content, dict):
                    current_draft_duration = script.content.get('duration')
                    logger.info(f"  当前草稿总时长: {current_draft_duration} 微秒")
                    
                    if max_track_end_time != current_draft_duration:
                        script.content['duration'] = max_track_end_time
                        logger.info(f"  草稿总时长已更新为: {script.content['duration']} 微秒 ({script.content['duration'] / 1_000_000:.2f}秒)")
                    else:
                        logger.info("  计算时长与当前草稿时长一致，无需更新。")
                else:
                    logger.warning("无法访问草稿内容字典 (script.content) 或其不是字典，无法调整总时长。")
                
                # 确保所有素材的duration都设置为视频实际时长
                try:
                    # 设置音频素材的duration
                    if hasattr(script, 'materials') and hasattr(script.materials, 'audios'):
                        audio_materials_count = len(script.materials.audios)
                        audio_materials_updated = 0
                        for audio_material in script.materials.audios:
                            if hasattr(audio_material, 'duration') and audio_material.duration != max_track_end_time:
                                original_duration = audio_material.duration
                                audio_material.duration = max_track_end_time
                                audio_materials_updated += 1
                                logger.info(f"  更新音频素材duration从 {original_duration/1_000_000:.2f}秒 到 {max_track_end_time/1_000_000:.2f}秒")
                        logger.info(f"  更新了 {audio_materials_updated}/{audio_materials_count} 个音频素材的duration")
                    
                    # 设置Script_file的duration属性
                    if hasattr(script, 'duration'):
                        if script.duration != max_track_end_time:
                            logger.info(f"  更新script.duration从 {script.duration/1_000_000:.2f}秒 到 {max_track_end_time/1_000_000:.2f}秒")
                            script.duration = max_track_end_time
                        else:
                            logger.info(f"  script.duration已经是正确的值: {script.duration/1_000_000:.2f}秒")
                
                except Exception as e:
                    logger.warning(f"  在设置素材duration时发生错误: {e}", exc_info=True)
            else:
                logger.warning("无法获取 video_track 或其 end_time 属性，跳过总时长调整。")
        except Exception as e:
            logger.warning(f"处理BGM或调整草稿总时长时发生错误: {e}", exc_info=True)
            # Continue even if BGM adjustment fails

        # --- 7. Save draft changes ---
        logger.warning(f"注意：即将保存修改，这将覆盖原始模板草稿 \'{draft_name}\'！")
        logger.info(f"保存修改到草稿: {draft_name}")
        save_start_time = time.time()
        
        # 保存前检查片段音量设置
        if main_track_volume != 100:
            try:
                logger.info(f"保存前验证主轨道音量设置状态：")
                check_count = min(5, len(video_track.segments))  # 最多检查前5个片段
                for i in range(check_count):
                    current_volume = video_track.segments[i].volume if hasattr(video_track.segments[i], 'volume') else "未设置"
                    logger.info(f"  保存前片段 {i} 音量为: {current_volume}")
            except Exception as e:
                logger.error(f"保存前检查音量设置时出错: {e}")
        
        # 强制提交一次所有视频片段的音量设置
        if normalized_main_volume != 1.0:
            try:
                logger.info("保存前强制应用最终音量设置...")
                segments_updated = 0
                segments_total = len(video_track.segments)
                
                for i in range(segments_total):
                    if set_segment_volume(
                        video_track.segments[i], 
                        normalized_main_volume, 
                        segment_idx=i, 
                        context="保存前最终设置"
                    ):
                        segments_updated += 1
                
                # 添加确认日志
                logger.info(f"保存前已更新 {segments_updated}/{segments_total} 个视频片段的音量为 {main_track_volume}%")
            except Exception as e:
                logger.error(f"最终应用音量设置时出错: {e}")
        
        # 保存前验证BGM音量
        if keep_bgm and len(audio_tracks) > 0:
            validate_bgm_volume(audio_tracks, context="保存前")
        
        logger.info(f"准备保存草稿: {draft_name}...")
        script.save()
        logger.info(f"草稿 '{draft_name}' 保存完成")
        
        # 保存后重新加载草稿验证BGM音量
        if keep_bgm and len(audio_tracks) > 0:
            try:
                logger.info(f"重新加载草稿 '{draft_name}' 以验证保存后的BGM音量...")
                reload_script = draft_folder.load_template(draft_name)
                
                # 查找音频轨道
                reload_bgm_tracks = []
                i = 0
                try:
                    while True:
                        try:
                            audio_track = reload_script.get_imported_track(draft.Track_type.audio, index=i)
                            if audio_track:
                                reload_bgm_tracks.append(audio_track)
                            i += 1
                        except IndexError:
                            break
                except Exception as e:
                    logger.error(f"获取重新加载后的音频轨道时出错: {e}")
                
                # 验证保存后的BGM音量
                validate_bgm_volume(reload_bgm_tracks, context="保存后")
            except Exception as e:
                logger.error(f"验证保存后BGM音量时出错: {e}")

        # --- 8. Export video ---
        # 使用独立的导出模块
        if export_video:
            logger.info(f"准备导出视频到: {export_file_path}")
            # Directory creation moved earlier

            # 使用新模块中的控制器
            ctrl = Fast_Jianying_Controller() # 使用优化的控制器
            logger.info("使用速度优化的剪映控制器进行导出...")

            export_success = False # 初始化导出状态
            max_retries = 10  # 增加到10次重试
            initial_wait = 3  # 初始等待时间3秒
            
            for attempt in range(1, max_retries + 1):
                # 计算等待时间：初始值 + (尝试次数 - 1)
                wait_time = initial_wait + (attempt - 1) if attempt > 1 else 0
                
                if attempt > 1:
                    logger.info(f"等待 {wait_time} 秒后进行第 {attempt} 次导出尝试...")
                    time.sleep(wait_time)
                    
                logger.info(f"开始导出尝试 #{attempt}/{max_retries}...")
                export_start = time.time()
                try:
                    current_export_success = ctrl.export_draft(
                        draft_name=draft_name,
                        output_path=export_file_path, # This is the final destination path
                        resolution=Export_resolution.RES_1080P if CUSTOMIZE_EXPORT else None,
                        framerate=Export_framerate.FR_30 if CUSTOMIZE_EXPORT else None
                    )
                    export_dur = time.time() - export_start
                    logger.info(f"导出函数调用 (尝试 #{attempt}) 耗时: {export_dur:.2f}秒")

                    if current_export_success:
                        export_success = True # 标记最终成功状态
                        logger.info(f"导出尝试 #{attempt} 成功。")
                        break # 成功则跳出重试循环
                    else:
                        logger.warning(f"导出尝试 #{attempt} 失败。")
                        if attempt >= max_retries:
                            logger.error(f"所有 {max_retries} 次导出尝试均失败。")
                except Exception as export_err:
                    export_dur = time.time() - export_start
                    logger.error(f"导出尝试 #{attempt} 期间发生异常: {export_err}", exc_info=True)
                    logger.info(f"导出函数调用 (尝试 #{attempt} - 异常) 耗时: {export_dur:.2f}秒")
                    if attempt >= max_retries:
                        logger.error(f"所有 {max_retries} 次导出尝试均因异常失败。")

            # --- 根据最终的 export_success 状态进行后续处理 ---
            if export_success:
                logger.info(f"视频导出成功: {export_file_path}")
                result["success"] = True
            else:
                # 如果所有尝试都失败了
                error_msg = f"视频导出失败 (模板: {draft_name})，已尝试 {max_retries} 次。请检查剪映状态和详细日志。"
                logger.error(error_msg)
                result["error"] = error_msg # Set error message based on final failure
                result["success"] = False # Ensure result reflects the failure
        else:
             logger.info("跳过视频导出步骤。")
             result["success"] = True # Mark as success if export is skipped

    except draft.exceptions.DraftNotFound as e:
        error_msg = f"剪映处理失败：找不到模板草稿 '{draft_name}'。错误: {e}"
        logger.error(error_msg)
        result["error"] = error_msg
    except FileNotFoundError as e:
         error_msg = f"剪映处理失败：找不到预期的视频片段文件。错误: {e}"
         logger.error(error_msg)
         result["error"] = str(e)
    except IndexError as e:
        error_msg = f"剪映处理失败：模板轨道和输入片段数量不匹配或索引错误。错误: {e}"
        logger.error(error_msg)
        result["error"] = error_msg
    except ValueError as e:
         error_msg = f"剪映处理失败：处理模板轨道时出错。错误: {e}"
         logger.error(error_msg)
         result["error"] = error_msg
    except draft.exceptions.AutomationError as e:
        error_msg = f"剪映处理失败：剪映 UI 自动化错误。错误: {e}"
        logger.error(error_msg, exc_info=True)
        result["error"] = f"剪映 UI 自动化错误: {e}"
    except IOError as e:
         error_msg = f"剪映处理失败：文件系统错误（如创建导出目录失败）。错误: {e}"
         logger.error(error_msg)
         result["error"] = error_msg
    # Removed RuntimeError handling as we now set success=False for export fail
    except Exception as e:
        error_msg = f"剪映处理过程中发生未知错误"
        logger.exception(error_msg) # Log full traceback for unknown errors
        result["error"] = f"未知错误: {str(e)}"
    finally:
        status_msg = "成功" if result["success"] else f"失败 ({result['error']})"
        logger.info(f"--- 剪映模板处理结束: {draft_name} | 结果: {status_msg} ---")

    return result 