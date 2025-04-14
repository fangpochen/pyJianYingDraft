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

# 导入独立的导出逻辑模块
from app.util.jianying_export import Fast_Jianying_Controller

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
        
        # 4.1 若保留BGM，获取所有音频轨道
        audio_tracks = []
        bgm_tracks = [] # 专门存储BGM轨道
        bgm_segments = [] # 存储所有BGM片段信息
        
        if keep_bgm:
            try:
                # 尝试查找所有音频轨道
                i = 0
                while True:
                    try:
                        audio_track = script.get_imported_track(draft.Track_type.audio, index=i)
                        if audio_track:
                            audio_tracks.append(audio_track)
                            # 检查是否是BGM轨道（根据命名约定或其他特征）
                            if "bgm" in audio_track.name.lower() or "音乐" in audio_track.name or "music" in audio_track.name.lower():
                                bgm_tracks.append(audio_track)
                                # 收集BGM片段信息
                                if hasattr(audio_track, 'segments') and audio_track.segments:
                                    for seg in audio_track.segments:
                                        bgm_segments.append({
                                            "track": audio_track,
                                            "segment": seg,
                                            "index": len(bgm_segments),
                                            "start": seg.target_timerange.start,
                                            "duration": seg.target_timerange.duration,
                                            "material_id": seg.material_id,
                                            "material_instance": None  # 后续需要查找素材实例
                                        })
                            logger.info(f"找到音频轨道 #{i} ({audio_track.name}), 包含 {len(audio_track.segments) if hasattr(audio_track, 'segments') else '未知'} 个片段")
                        i += 1
                    except IndexError:
                        # 没有更多音频轨道，退出循环
                        break
                    except Exception as e:
                        logger.warning(f"获取音频轨道 #{i} 时出错: {e}")
                        break
                
                if audio_tracks:
                    logger.info(f"成功找到 {len(audio_tracks)} 个音频轨道，其中 {len(bgm_tracks)} 个被识别为BGM轨道。")
                    if bgm_segments:
                        logger.info(f"找到 {len(bgm_segments)} 个BGM片段。")
                    else:
                        logger.info("未在BGM轨道中找到音频片段。")
                else:
                    logger.info("模板中未找到音频轨道。")
            except Exception as e:
                logger.warning(f"尝试获取音频轨道时发生错误: {e}，将跳过BGM保留步骤。")

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

        # 6. 获取新视频轨道时长并调整BGM
        video_end_time = 0
        try:
            if video_track and hasattr(video_track, 'end_time'):
                video_end_time = video_track.end_time
                logger.info(f"计算得到的视频轨道实际结束时间: {video_end_time} 微秒 ({video_end_time / 1_000_000:.2f} 秒)")
                
                # 处理BGM（新实现）
                if keep_bgm and bgm_segments and len(bgm_segments) > 0:
                    logger.info("开始处理BGM...")
                    
                    # 获取第一个BGM片段的素材信息
                    bgm_material = None
                    for bgm_info in bgm_segments:
                        try:
                            if bgm_info["material_id"] in script.materials:
                                bgm_info["material_instance"] = script.materials[bgm_info["material_id"]]
                                if not bgm_material:
                                    bgm_material = bgm_info["material_instance"]
                                logger.debug(f"获取到BGM素材: {bgm_info['material_id']}")
                            else:
                                logger.warning(f"BGM素材ID {bgm_info['material_id']} 在素材库中未找到")
                        except Exception as e:
                            logger.warning(f"获取BGM素材时发生错误: {e}")

                    if not bgm_material:
                        logger.warning("未能获取有效的BGM素材信息，将跳过BGM处理")
                    else:
                        # 获取BGM总长度和首个BGM片段信息
                        first_bgm_segment = bgm_segments[0]
                        first_bgm_track = first_bgm_segment["track"]
                        first_bgm_duration = bgm_material.duration
                        
                        logger.info(f"BGM素材时长: {first_bgm_duration / 1_000_000:.2f} 秒")
                        
                        # 清空bgm轨道上的所有片段，我们将重新添加
                        for bgm_track in bgm_tracks:
                            if hasattr(bgm_track, 'segments'):
                                # 备份原始片段信息，以便重建
                                bgm_track.segments.clear()
                                logger.debug(f"清空BGM轨道 {bgm_track.name} 上的片段")
                        
                        # 确保bgm_volume在合法范围内
                        normalized_volume = max(0, min(100, bgm_volume)) / 100.0  # 转换为0.0-1.0的浮点数
                        
                        if video_end_time <= first_bgm_duration:
                            # 视频比BGM短，需要截断BGM
                            logger.info(f"视频长度小于BGM，截断BGM至 {video_end_time / 1_000_000:.2f} 秒")
                            
                            # 创建新的截断BGM片段
                            try:
                                # 使用原始素材，但设置新时长
                                target_timerange = Timerange(0, video_end_time)
                                source_timerange = Timerange(0, video_end_time)
                                
                                # 替换第一个轨道的素材，应用音量设置
                                first_bgm_track.segments.append(
                                    draft.Imported_media_segment({
                                        "material_id": bgm_material.material_id,
                                        "source_timerange": source_timerange.export_json(),
                                        "target_timerange": target_timerange.export_json(),
                                        "clip": None,
                                        "volume": normalized_volume,  # 应用用户设置的音量
                                        "extra_material_refs": [],
                                        "id": first_bgm_segment["segment"].segment_id if hasattr(first_bgm_segment["segment"], "segment_id") else None
                                    })
                                )
                                logger.info(f"成功添加截断的BGM片段，时长: {video_end_time / 1_000_000:.2f} 秒，音量: {bgm_volume}%")
                            except Exception as e:
                                logger.error(f"添加截断BGM片段时出错: {e}", exc_info=True)
                        
                        elif bgm_loop:
                            # 视频比BGM长，需要循环播放BGM
                            logger.info(f"视频长度大于BGM，将循环播放BGM {math.ceil(video_end_time / first_bgm_duration)} 次")
                            
                            # 计算需要多少个完整BGM循环
                            current_position = 0
                            loop_count = 0
                            
                            while current_position < video_end_time:
                                remaining_time = video_end_time - current_position
                                
                                # 计算当前循环应该使用的时长（可能需要截断最后一个循环）
                                loop_duration = min(first_bgm_duration, remaining_time)
                                
                                try:
                                    # 创建新的BGM片段
                                    target_timerange = Timerange(current_position, loop_duration)
                                    source_timerange = Timerange(0, loop_duration)
                                    
                                    # 添加到第一个BGM轨道，应用音量设置
                                    segment_id = first_bgm_segment["segment"].segment_id if hasattr(first_bgm_segment["segment"], "segment_id") and loop_count == 0 else None
                                    
                                    first_bgm_track.segments.append(
                                        draft.Imported_media_segment({
                                            "material_id": bgm_material.material_id,
                                            "source_timerange": source_timerange.export_json(),
                                            "target_timerange": target_timerange.export_json(),
                                            "clip": None,
                                            "volume": normalized_volume,  # 应用用户设置的音量
                                            "extra_material_refs": [],
                                            "id": segment_id
                                        })
                                    )
                                    logger.debug(f"添加第 {loop_count+1} 个BGM循环片段，起始位置: {current_position / 1_000_000:.2f} 秒，时长: {loop_duration / 1_000_000:.2f} 秒，音量: {bgm_volume}%")
                                except Exception as e:
                                    logger.error(f"添加第 {loop_count+1} 个BGM循环片段时出错: {e}")
                                    break
                                
                                # 更新位置和计数
                                current_position += loop_duration
                                loop_count += 1
                            
                            logger.info(f"成功添加 {loop_count} 个BGM循环片段，总时长: {current_position / 1_000_000:.2f} 秒，音量: {bgm_volume}%")
                        else:
                            # 不循环BGM，保持原有长度
                            logger.info("视频长度大于BGM，但不循环播放，保持原BGM长度")
                            
                            # 仅添加一次完整BGM，应用音量设置
                            try:
                                target_timerange = Timerange(0, first_bgm_duration)
                                source_timerange = Timerange(0, first_bgm_duration)
                                
                                first_bgm_track.segments.append(
                                    draft.Imported_media_segment({
                                        "material_id": bgm_material.material_id,
                                        "source_timerange": source_timerange.export_json(),
                                        "target_timerange": target_timerange.export_json(),
                                        "clip": None,
                                        "volume": normalized_volume,  # 应用用户设置的音量
                                        "extra_material_refs": [],
                                        "id": first_bgm_segment["segment"].segment_id if hasattr(first_bgm_segment["segment"], "segment_id") else None
                                    })
                                )
                                logger.info(f"成功添加单次播放的BGM片段，时长: {first_bgm_duration / 1_000_000:.2f} 秒，音量: {bgm_volume}%")
                            except Exception as e:
                                logger.error(f"添加单次播放BGM片段时出错: {e}", exc_info=True)
                
                # 更新草稿总时长
                if hasattr(script, 'content') and isinstance(script.content, dict):
                    current_draft_duration = script.content.get('duration')
                    logger.info(f"  当前草稿总时长: {current_draft_duration} 微秒")
                    
                    # 计算新的总时长（考虑所有轨道的最大结束时间）
                    max_track_end_time = video_end_time
                    
                    # 如果有BGM且不循环，检查BGM轨道是否超出视频长度
                    if keep_bgm and not bgm_loop and bgm_tracks:
                        for bgm_track in bgm_tracks:
                            if hasattr(bgm_track, 'end_time'):
                                track_end_time = bgm_track.end_time
                                if track_end_time > max_track_end_time:
                                    logger.info(f"BGM轨道 {bgm_track.name} 结束时间 ({track_end_time / 1_000_000:.2f}秒) 大于视频轨道")
                                    max_track_end_time = track_end_time
                    
                    # 可能还有其他轨道需要考虑
                    for track in audio_tracks:
                        if track not in bgm_tracks and hasattr(track, 'end_time'):
                            track_end_time = track.end_time
                            if track_end_time > max_track_end_time:
                                logger.info(f"音频轨道 {track.name} 结束时间 ({track_end_time / 1_000_000:.2f}秒) 大于当前最大时长")
                                max_track_end_time = track_end_time
                    
                    if max_track_end_time != current_draft_duration:
                        script.content['duration'] = max_track_end_time
                        logger.info(f"  草稿总时长已更新为: {script.content['duration']} 微秒 ({script.content['duration'] / 1_000_000:.2f}秒)")
                    else:
                        logger.info("  计算时长与当前草稿时长一致，无需更新。")
                else:
                    logger.warning("无法访问草稿内容字典 (script.content) 或其不是字典，无法调整总时长。")
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
        
        script.save()
        logger.info(f"草稿 '{draft_name}' 保存完成")

        # --- 8. Export video --- 
        # 使用独立的导出模块
        if export_video:
            logger.info(f"准备导出视频到: {export_file_path}")
            # Directory creation moved earlier

            # 使用新模块中的控制器
            ctrl = Fast_Jianying_Controller() # 使用优化的控制器
            logger.info("使用速度优化的剪映控制器进行导出...")

            export_start = time.time()
            export_success = ctrl.export_draft(
                draft_name=draft_name,
                output_path=export_file_path, # This is the final destination path
                resolution=Export_resolution.RES_1080P if CUSTOMIZE_EXPORT else None,
                framerate=Export_framerate.FR_30 if CUSTOMIZE_EXPORT else None
            )
            export_dur = time.time() - export_start
            logger.info(f"导出函数调用耗时: {export_dur:.2f}秒")

            if export_success:
                logger.info(f"视频导出成功: {export_file_path}")
                result["success"] = True
            else:
                error_msg = f"视频导出失败 (模板: {draft_name})。请检查剪映状态和详细日志。"
                logger.error(error_msg)
                result["error"] = error_msg # Set error message
                # No longer raising error here, return success=False
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