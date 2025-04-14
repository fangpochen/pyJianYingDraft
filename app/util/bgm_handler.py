"""
剪映BGM处理模块

处理剪映草稿中的BGM，包括音量控制、长度调整和循环播放逻辑
"""

import logging
import copy
import pyJianYingDraft as draft
from pyJianYingDraft.time_util import Timerange

# 获取模块的logger实例
logger = logging.getLogger(__name__)

def process_bgm(script, video_end_time, keep_bgm=True, bgm_loop=True, bgm_volume=100):
    """
    处理BGM的核心逻辑，包括裁剪、循环和音量控制
    
    Args:
        script: 草稿对象 
        video_end_time: 视频轨道结束时间（微秒）
        keep_bgm: 是否保留BGM
        bgm_loop: 视频长于BGM时是否循环播放BGM
        bgm_volume: BGM音量百分比(0-100)
        
    Returns:
        dict: 包含处理结果的字典，格式为{"audio_tracks": [...], "max_track_end_time": int}
    """
    logger.info(f"script:{script}")
    logger.info(f"video_end_time:{video_end_time}")
    logger.info(f"keep_bgm:{keep_bgm}")
    logger.info(f"bgm_loop:{bgm_loop}")
    logger.info(f"bgm_volume:{bgm_volume}")
    result = {
        "audio_tracks": [],
        "max_track_end_time": video_end_time,
        "success": True
    }
    
    # 如果用户选择不保留BGM，则直接返回
    if not keep_bgm:
        logger.info("用户选择不保留BGM，将跳过BGM处理")
        return result
    
    # 获取所有音频轨道
    audio_tracks = []
    bgm_tracks = []  # 专门存储BGM轨道
    bgm_segments = []  # 存储所有BGM片段信息
    
    try:
        # 尝试查找所有音频轨道
        i = 0
        while True:
            try:
                audio_track = script.get_imported_track(draft.Track_type.audio, index=i)
                if audio_track:
                    audio_tracks.append(audio_track)
                    # 将所有音频轨道都视为BGM轨道
                    bgm_tracks.append(audio_track)
                    logger.info(f"将音频轨道 #{i} ({audio_track.name}) 识别为BGM轨道")
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
        
        # 更新返回结果中的音频轨道
        result["audio_tracks"] = audio_tracks
        
        if audio_tracks:
            logger.info(f"成功找到 {len(audio_tracks)} 个音频轨道，其中 {len(bgm_tracks)} 个被识别为BGM轨道。")
            if bgm_segments:
                logger.info(f"找到 {len(bgm_segments)} 个BGM片段。")
            else:
                logger.info("未在BGM轨道中找到音频片段。")
                return result
        else:
            logger.info("模板中未找到音频轨道。")
            return result
        
        # 处理BGM（剪映内置BGM适配版 - 修改现有片段）
        if bgm_segments and len(bgm_segments) > 0:
            logger.info("开始处理BGM...")
            
            # 获取第一个BGM片段信息
            first_bgm_segment = bgm_segments[0]
            first_bgm_track = first_bgm_segment["track"]
            first_segment_obj = first_bgm_segment["segment"]  # 原始BGM片段对象
            
            # 获取原始BGM属性
            material_id = first_bgm_segment["material_id"]
            bgm_duration = first_bgm_segment["duration"]
            logger.info(f"原始BGM片段时长: {bgm_duration/1_000_000:.2f}秒")
            
            # 确保音量设置在合法范围内并归一化为0.0-1.0
            normalized_volume = max(0, min(100, bgm_volume)) / 100.0
            if normalized_volume < 0.01 and bgm_volume > 0:
                normalized_volume = 0.01  # 确保即使是低音量设置也至少有1%的音量
            logger.info(f"设置BGM音量为: {bgm_volume}% (归一化值: {normalized_volume:.4f})")
            
            # 保存原始片段以便复制
            original_segments = []
            for segment in first_bgm_track.segments:
                # 记录BGM片段的起始位置
                if hasattr(segment, 'target_timerange'):
                    bgm_start = segment.target_timerange.start
                    logger.info(f"BGM片段原始起始位置: {bgm_start/1_000_000:.2f}秒")
                    
                    # 如果BGM不是从0开始，记录下来
                    if bgm_start > 0:
                        logger.info(f"注意：BGM不是从0开始，而是从 {bgm_start/1_000_000:.2f}秒开始")
                
                # 设置所有片段的音量
                if hasattr(segment, 'volume'):
                    segment.volume = normalized_volume
                    logger.info(f"设置BGM片段音量属性: volume={segment.volume}")
                elif hasattr(segment, '_json') and '_json' in segment.__dict__:
                    # 尝试通过_json属性设置音量
                    segment._json['volume'] = normalized_volume
                    logger.info(f"通过_json设置BGM片段音量: _json['volume']={segment._json['volume']}")
                else:
                    # 尝试直接设置字典属性
                    try:
                        segment.__dict__['volume'] = normalized_volume
                        logger.info(f"通过__dict__设置BGM片段音量: {normalized_volume}")
                    except Exception as e:
                        logger.warning(f"无法设置BGM片段音量: {e}")
                original_segments.append(segment)
            
            # 根据情况处理BGM
            if video_end_time <= bgm_duration:
                # 情况1: 视频短于BGM，需要截断BGM
                logger.info(f"视频长度小于BGM长度，截断BGM至 {video_end_time/1_000_000:.2f}秒")
                
                # 仅保留第一个片段并截断时长
                if len(original_segments) > 0:
                    first_segment = original_segments[0]
                    
                    # 截断片段
                    if hasattr(first_segment, 'target_timerange'):
                        original_start = first_segment.target_timerange.start
                        first_segment.target_timerange = Timerange(original_start, video_end_time)
                        
                        # 将轨道段修改为只有第一个片段
                        first_bgm_track.segments = [first_segment]
                        logger.info(f"成功截断BGM片段至视频长度: {video_end_time/1_000_000:.2f}秒")
            
            elif bgm_loop and len(original_segments) > 0:
                # 情况2: 视频长于BGM且需循环播放
                logger.info(f"视频长度大于BGM长度且需循环BGM: {bgm_duration/1_000_000:.2f}秒 < {video_end_time/1_000_000:.2f}秒")
                
                # 清空现有片段
                first_bgm_track.segments.clear()
                
                # 添加循环片段直到覆盖整个视频长度
                template_segment = original_segments[0]  # 使用第一个片段作为模板
                
                # 获取原始BGM的起始位置
                original_start = 0  # 默认从0开始
                if hasattr(template_segment, 'target_timerange'):
                    # 是否要保持原始位置还是移到0开始
                    keep_original_start = False  # 是否保持原始起始位置
                    
                    if keep_original_start:
                        original_start = template_segment.target_timerange.start
                        logger.info(f"保留原始BGM起始位置: {original_start/1_000_000:.2f}秒")
                    else:
                        original_start = 0
                        logger.info(f"将BGM起始位置设置为0")
                
                # 从设定位置开始添加循环片段
                current_position = original_start
                loop_count = 0
                
                while current_position < video_end_time:
                    remaining_time = video_end_time - current_position
                    loop_duration = min(bgm_duration, remaining_time)
                    
                    # 复制片段并调整属性
                    new_segment = copy.deepcopy(template_segment)
                    
                    # 设置新片段的时间范围，保留原始起始位置
                    if hasattr(new_segment, 'target_timerange'):
                        new_segment.target_timerange = Timerange(current_position, loop_duration)
                    
                    # 设置新片段的源时间范围
                    if hasattr(new_segment, 'source_timerange'):
                        new_segment.source_timerange = Timerange(0, loop_duration)
                    
                    # 设置音量
                    if hasattr(new_segment, 'volume'):
                        new_segment.volume = normalized_volume
                    
                    # 添加到轨道
                    first_bgm_track.segments.append(new_segment)
                    
                    current_position += loop_duration
                    loop_count += 1
                    logger.info(f"添加第 {loop_count} 个BGM循环片段, 位置: {(current_position-loop_duration)/1_000_000:.2f}s - {current_position/1_000_000:.2f}s")
                
                logger.info(f"成功添加 {loop_count} 个BGM循环片段，总计覆盖时长: {current_position/1_000_000:.2f}秒")
            else:
                # 情况3: 视频长于BGM但不循环，保留原始片段
                logger.info(f"视频长度大于BGM长度但不循环: {bgm_duration/1_000_000:.2f}秒 < {video_end_time/1_000_000:.2f}秒")
                logger.info("保留原始BGM片段，仅设置音量")
                
                # 仅设置音量
                for i, segment in enumerate(first_bgm_track.segments):
                    if hasattr(segment, 'volume'):
                        segment.volume = normalized_volume
                        logger.info(f"设置BGM片段 {i} 的音量为 {bgm_volume}%")
            
            # 验证BGM轨道片段状态
            if hasattr(first_bgm_track, 'segments'):
                bgm_segments_count = len(first_bgm_track.segments)
                logger.info(f"BGM处理完成，轨道包含 {bgm_segments_count} 个片段")
        else:
            logger.warning(f"BGM轨道 {first_bgm_track.name} 不包含segments属性，无法处理")
        
        # 计算新的总时长（考虑所有轨道的最大结束时间）
        max_track_end_time = video_end_time
        
        # 如果有BGM且不循环，检查BGM轨道是否超出视频长度
        if not bgm_loop and bgm_tracks:
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
        
        # 更新返回结果中的最大轨道时长
        result["max_track_end_time"] = max_track_end_time
        
    except Exception as e:
        logger.warning(f"处理BGM时发生错误: {e}", exc_info=True)
        result["success"] = False
    
    return result


def validate_bgm_volume(bgm_tracks, context="保存前"):
    """
    验证BGM轨道片段的音量设置
    
    Args:
        bgm_tracks: BGM轨道列表
        context: 上下文描述，用于日志
        
    Returns:
        bool: 验证是否成功
    """
    if not bgm_tracks:
        logger.warning(f"{context}没有可验证的BGM轨道")
        return True
    
    logger.info(f"====== {context}BGM音量状态 ======")
    try:
        for track_idx, track in enumerate(bgm_tracks):
            if hasattr(track, 'segments') and track.segments:
                logger.info(f"BGM轨道 #{track_idx} ({track.name if hasattr(track, 'name') else '无名称'}) {context}音量:")
                for seg_idx, segment in enumerate(track.segments):
                    # 尝试多种方式获取音量
                    volume_attrs = []
                    
                    # 1. 直接属性
                    if hasattr(segment, 'volume'):
                        volume_attrs.append(f"volume={segment.volume}")
                    else:
                        volume_attrs.append("volume=未设置(属性不存在)")
                    
                    # 2. _json字典
                    if hasattr(segment, '_json') and isinstance(segment._json, dict):
                        if 'volume' in segment._json:
                            volume_attrs.append(f"_json['volume']={segment._json['volume']}")
                        else:
                            volume_attrs.append("_json['volume']=不存在")
                    else:
                        volume_attrs.append("_json=不存在或不是字典")
                    
                    # 3. __dict__
                    if hasattr(segment, '__dict__'):
                        if 'volume' in segment.__dict__:
                            volume_attrs.append(f"__dict__['volume']={segment.__dict__['volume']}")
                        else:
                            volume_attrs.append("__dict__['volume']=不存在")
                    
                    # 输出所有获取到的音量值
                    logger.info(f"  片段 #{seg_idx}: {', '.join(volume_attrs)}")
                    
                    # 尝试输出片段的JSON表示
                    try:
                        import json
                        if hasattr(segment, '_json'):
                            logger.debug(f"  片段 #{seg_idx} JSON: {json.dumps(segment._json, indent=2)}")
                    except Exception as e:
                        logger.debug(f"  无法序列化片段 #{seg_idx} 的JSON: {e}")
            else:
                logger.warning(f"BGM轨道 #{track_idx} ({track.name if hasattr(track, 'name') else '无名称'}) 没有segments属性或segments为空")
    except Exception as e:
        logger.error(f"验证{context}BGM音量时出错: {e}")
        return False
    
    logger.info("============================")
    return True 