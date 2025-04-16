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
    
    # 根据是否保留BGM调用不同的处理函数
    if not keep_bgm:
        # 不保留BGM，调用静音处理函数
        return process_bgm_mute(script, video_end_time)
    else:
        # 保留BGM，调用正常处理函数
        return process_bgm_keep(script, video_end_time, bgm_loop, bgm_volume)


def process_bgm_mute(script, video_end_time):
    """
    处理不保留BGM的情况，将所有音频轨道静音
    
    Args:
        script: 草稿对象
        video_end_time: 视频轨道结束时间（微秒）
        
    Returns:
        dict: 包含处理结果的字典
    """
    logger.info("用户选择不保留BGM，将BGM音量设置为0（静音）")
    result = {
        "audio_tracks": [],
        "max_track_end_time": video_end_time,
        "success": True
    }
    
    # 获取所有音频轨道
    try:
        audio_tracks = []
        i = 0
        while True:
            try:
                audio_track = script.get_imported_track(draft.Track_type.audio, index=i)
                if audio_track:
                    audio_tracks.append(audio_track)
                    if hasattr(audio_track, 'segments'):
                        muted_count = 0
                        for segment in audio_track.segments:
                            if hasattr(segment, 'volume'):
                                segment.volume = 0.0
                                muted_count += 1
                            elif hasattr(segment, '_json') and '_json' in segment.__dict__:
                                segment._json['volume'] = 0.0
                                muted_count += 1
                            else:
                                try:
                                    segment.__dict__['volume'] = 0.0
                                    muted_count += 1
                                except Exception as e:
                                    logger.warning(f"无法设置BGM片段音量为0: {e}")
                        logger.info(f"已将音频轨道 #{i} ({audio_track.name if hasattr(audio_track, 'name') else '无名称'}) 的 {muted_count}/{len(audio_track.segments)} 个片段音量设置为0")
                    else:
                        logger.warning(f"音频轨道 #{i} 没有segments属性，无法静音")
                i += 1
            except IndexError:
                # 没有更多音频轨道，退出循环
                break
            except Exception as e:
                logger.warning(f"获取音频轨道 #{i} 时出错: {e}")
                break
                
        result["audio_tracks"] = audio_tracks
        logger.info(f"已静音 {len(audio_tracks)} 个音频轨道")
    except Exception as e:
        logger.warning(f"静音BGM时发生错误: {e}", exc_info=True)
        result["success"] = False
    
    return result


def process_bgm_keep(script, video_end_time, bgm_loop=True, bgm_volume=100):
    """
    处理保留BGM的情况，包括设置音量、控制长度和循环播放
    
    Args:
        script: 草稿对象
        video_end_time: 视频轨道结束时间（微秒）
        bgm_loop: 视频长于BGM时是否循环播放BGM
        bgm_volume: BGM音量百分比(0-100)
        
    Returns:
        dict: 包含处理结果的字典
    """
    result = {
        "audio_tracks": [],
        "max_track_end_time": video_end_time,
        "success": True
    }
    
    # 获取所有音频轨道
    audio_tracks = []
    bgm_tracks = []  # 专门存储BGM轨道
    bgm_segments = []  # 存储所有BGM片段信息
    
    try:
        # 计算视频轨道的实际长度
        # 获取脚本中的所有视频轨道
        video_tracks = []
        total_video_length = 0
        track_idx = 0
        
        # 尝试获取视频轨道
        while True:
            try:
                video_track = script.get_imported_track(draft.Track_type.video, index=track_idx)
                if video_track:
                    video_tracks.append(video_track)
                    
                    # 计算视频轨道的实际结束时间
                    if hasattr(video_track, 'segments') and video_track.segments:
                        for segment in video_track.segments:
                            if hasattr(segment, 'target_timerange'):
                                segment_end = segment.target_timerange.start + segment.target_timerange.duration
                                if segment_end > total_video_length:
                                    total_video_length = segment_end
                track_idx += 1
            except IndexError:
                break
            except Exception as e:
                logger.warning(f"获取视频轨道 #{track_idx} 时出错: {e}")
                break
        
        # 如果找到了视频轨道，使用它的实际长度作为BGM长度
        if total_video_length > 0:
            logger.info(f"计算出视频轨道的实际长度: {total_video_length/1_000_000:.2f}秒，使用此长度作为BGM长度")
            video_end_time = total_video_length
        else:
            logger.info(f"未能计算出视频轨道实际长度，使用传入的视频结束时间: {video_end_time/1_000_000:.2f}秒")
        
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
                                "start": seg.target_timerange.start if hasattr(seg, 'target_timerange') else 0,
                                "duration": seg.target_timerange.duration if hasattr(seg, 'target_timerange') else 0,
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
            
            # === 统一处理逻辑：无论视频与BGM长度关系如何，都确保start为0，duration与视频长度一致 ===
            
            logger.info(f"按照要求设置BGM时长等于视频时长: {video_end_time/1_000_000:.2f}秒，且起始位置为0")
            
            # 无论BGM长度如何，只处理第一个片段
            if len(original_segments) > 0:
                # 保留第一个片段，设置正确的timerange
                first_segment = original_segments[0]
                
                # 设置target_timerange，起始位置为0，时长为视频时长
                if hasattr(first_segment, 'target_timerange') or True:  # 确保创建target_timerange
                    first_segment.target_timerange = Timerange(0, video_end_time)
                    logger.info(f"设置BGM target_timerange: start=0秒, duration={video_end_time/1_000_000:.2f}秒")
                
                # 必须设置source_timerange，start为0，duration与target_timerange.duration一致
                if hasattr(first_segment, 'source_timerange') or True:  # 确保创建source_timerange
                    first_segment.source_timerange = Timerange(0, video_end_time)
                    logger.info(f"设置BGM source_timerange: start=0秒, duration={video_end_time/1_000_000:.2f}秒")
                
                # 设置音量
                if hasattr(first_segment, 'volume'):
                    first_segment.volume = normalized_volume
                    logger.info(f"设置BGM片段音量为: {normalized_volume:.2f}")
                
                # 将轨道段修改为只有第一个片段
                first_bgm_track.segments = [first_segment]
                logger.info(f"成功设置BGM片段: 起始位置=0秒, 时长={video_end_time/1_000_000:.2f}秒")
            
            # 验证BGM轨道片段状态
            if hasattr(first_bgm_track, 'segments'):
                bgm_segments_count = len(first_bgm_track.segments)
                logger.info(f"BGM处理完成，轨道包含 {bgm_segments_count} 个片段")
            
            # 修改轨道级别的timerange属性
            for track in bgm_tracks:
                # 确保轨道上的segment的timerange正确
                if hasattr(track, 'segments') and track.segments:
                    for seg in track.segments:
                        # 设置segment的target_timerange
                        if hasattr(seg, 'target_timerange'):
                            seg.target_timerange = Timerange(0, video_end_time)
                            logger.info(f"设置BGM segment的target_timerange: start=0秒, duration={video_end_time/1_000_000:.2f}秒")
                        
                        # 设置segment的source_timerange
                        if hasattr(seg, 'source_timerange'):
                            seg.source_timerange = Timerange(0, video_end_time)
                            logger.info(f"设置BGM segment的source_timerange: start=0秒, duration={video_end_time/1_000_000:.2f}秒")
                
                # 设置轨道级别的source_timerange
                if hasattr(track, 'source_timerange'):
                    track.source_timerange = Timerange(0, video_end_time)
                    logger.info(f"设置BGM轨道source_timerange: start=0秒, duration={video_end_time/1_000_000:.2f}秒")
                
                # 设置轨道级别的target_timerange
                if hasattr(track, 'target_timerange'):
                    track.target_timerange = Timerange(0, video_end_time)
                    logger.info(f"设置BGM轨道target_timerange: start=0秒, duration={video_end_time/1_000_000:.2f}秒")
                
                # 设置轨道的end_time
                if hasattr(track, 'end_time'):
                    track.end_time = video_end_time
                    logger.info(f"设置BGM轨道end_time: {video_end_time/1_000_000:.2f}秒")
                
                # 尝试直接设置文件时长（如果存在这个属性）
                if hasattr(track, 'duration'):
                    track.duration = video_end_time
                    logger.info(f"设置BGM轨道duration: {video_end_time/1_000_000:.2f}秒")
                
                # 检查轨道的_json属性
                if hasattr(track, '_json') and track._json and isinstance(track._json, dict):
                    # 尝试设置_json中的timerange相关字段
                    if 'source_timerange' in track._json:
                        track._json['source_timerange'] = {'start': 0, 'duration': video_end_time}
                    if 'target_timerange' in track._json:
                        track._json['target_timerange'] = {'start': 0, 'duration': video_end_time}
                    if 'duration' in track._json:
                        track._json['duration'] = video_end_time
                    logger.info(f"设置BGM轨道_json字段中的时间属性为视频总时长: {video_end_time/1_000_000:.2f}秒")
            
            # 如果有单独的音频素材对象，也修改其时长（但不要修改草稿对象的总时长）
            for segment in bgm_segments:
                if 'material_instance' in segment and segment['material_instance'] is not None:
                    material = segment['material_instance']
                    if hasattr(material, 'duration'):
                        # 修改素材的原始时长，使其与视频时长一致
                        material.duration = video_end_time
                        logger.info(f"设置BGM素材duration为视频时长: {video_end_time/1_000_000:.2f}秒")
                        
                        # 如果素材有_json属性，也修改其中的duration值
                        if hasattr(material, '_json') and material._json and isinstance(material._json, dict):
                            if 'duration' in material._json:
                                material._json['duration'] = video_end_time
                                logger.info(f"设置BGM素材_json['duration']为视频时长: {video_end_time/1_000_000:.2f}秒")
            
            # 修改所有音频素材的duration
            if hasattr(script, 'materials') and hasattr(script.materials, 'audios'):
                for audio_material in script.materials.audios:
                    if hasattr(audio_material, 'duration'):
                        # 记录原始duration以便日志
                        original_duration = audio_material.duration
                        audio_material.duration = video_end_time
                        logger.info(f"修改音频素材duration从 {original_duration/1_000_000:.2f}秒 到 {video_end_time/1_000_000:.2f}秒")
                    
                    # 如果素材有_json属性，也修改其中的duration值
                    if hasattr(audio_material, '_json') and audio_material._json and isinstance(audio_material._json, dict):
                        if 'duration' in audio_material._json:
                            audio_material._json['duration'] = video_end_time
                            logger.info(f"设置音频素材_json['duration']为视频时长: {video_end_time/1_000_000:.2f}秒")
                            
            # 修改content中的总时长
            if hasattr(script, 'content') and isinstance(script.content, dict):
                if 'duration' in script.content:
                    script.content['duration'] = video_end_time
                    logger.info(f"设置草稿content['duration']为视频时长: {video_end_time/1_000_000:.2f}秒")
        else:
            logger.warning(f"BGM轨道不包含segments属性或没有片段，无法处理")
        
        # 更新返回结果中的最大轨道时长
        result["max_track_end_time"] = video_end_time
        
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
                    
                    # 输出timerange信息
                    if hasattr(segment, 'target_timerange'):
                        logger.info(f"  片段 #{seg_idx} target_timerange: start={segment.target_timerange.start/1_000_000:.2f}秒, duration={segment.target_timerange.duration/1_000_000:.2f}秒")
                    if hasattr(segment, 'source_timerange'):
                        logger.info(f"  片段 #{seg_idx} source_timerange: start={segment.source_timerange.start/1_000_000:.2f}秒, duration={segment.source_timerange.duration/1_000_000:.2f}秒")
                    
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