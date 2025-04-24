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
import traceback
import inspect
import re
from functools import wraps

# 导入独立的导出逻辑模块
from app.util.jianying_export import Fast_Jianying_Controller
# 导入BGM处理模块
from app.util.bgm_handler import process_bgm, validate_bgm_volume

# 获取该模块的 logger 实例
logger = logging.getLogger(__name__)

# 定义一个专用的异常类处理素材替换错误
class MaterialReplacementError(ValueError):
    """素材替换过程中的错误"""
    pass

# 重写发生在素材替换过程中可能出现的错误映射函数
def handle_material_error(func):
    """装饰器：处理素材替换过程中可能出现的错误，将关键错误转为警告"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # 如果错误消息包含与素材数量相关的内容，将其转换为警告并返回默认值
            error_msg = str(e).lower()
            if any(term in error_msg for term in ['素材数量', '无法替换', '无法进行替换']):
                # 获取调用者信息以便于日志记录
                frame = inspect.currentframe().f_back
                caller_info = f"{os.path.basename(frame.f_code.co_filename)}:{frame.f_lineno}"
                logging.getLogger(__name__).warning(
                    f"[{caller_info}] 素材数量警告 (已处理): {str(e)}，将继续使用循环模式。"
                )
                # 根据函数返回类型返回适当的默认值
                return args[0]  # 通常是self或修改后的对象
            else:
                # 对于其他类型的错误，重新抛出
                raise
    return wrapper

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

def process_videos(
    jianying_controller, 
    draft_name, 
    video_list, 
    output_folder,
    output_base_name=None,
    segment_info=None,
    process_mode="merge",
    segment_count=0,
    keep_bgm=True,
    bgm_volume=50,
    main_track_volume=100,
    selected_templates=None
):
    """
    处理视频列表，可以是合并或替换模式
    """
    try:
        jianying_controller.open_draft_by_name(draft_name)
        time.sleep(1)  # 等待草稿加载
        
        # 检查模板中的片段数量
        track_segments = jianying_controller.get_all_track_segments()
        logger.info(f"模板轨道现有 {len(track_segments)} 个片段")
        
        # 获取视频素材列表
        video_materials = []
        
        # 确保视频列表非空
        if not video_list:
            logger.error("没有提供视频素材")
            return False
        
        # --- 修复Bug 1: 素材替换逻辑 ---
        # 处理直接素材替换模式
        if process_mode == "direct_material_replace":
            # 获取实际需要替换的片段数量
            num_segments_to_replace = segment_count if segment_count > 0 else len(track_segments)
            logger.info(f"将替换 {num_segments_to_replace} 个片段")
            
            # 准备替换素材
            for video_path in video_list:
                if os.path.exists(video_path):
                    video_materials.append({
                        'path': video_path,
                        'filename': os.path.basename(video_path)
                    })
            
            # 打印实际加载的视频素材数量
            logger.info(f"加载了 {len(video_materials)} 个视频素材")
            
            # 检查素材数量与需要替换的片段数量
            if len(video_materials) < num_segments_to_replace:
                logger.warning(f"素材数量({len(video_materials)})小于需要替换的段数({num_segments_to_replace})，将循环使用素材")
            
            # 开始替换片段
            for i in range(min(num_segments_to_replace, len(track_segments))):
                # 使用模运算循环使用素材
                material_index = i % len(video_materials)
                material = video_materials[material_index]
                
                logger.info(f"替换 模板片段索引 {i} 使用素材: {material['filename']}")
                jianying_controller.replace_segment_with_material(i, material['path'])
                time.sleep(0.5)  # 等待替换完成
        # --- 素材替换逻辑修复结束 ---
        
        elif process_mode == "merge":
            # 处理合并模式（原有代码保持不变）
            for video_path in video_list:
                if os.path.exists(video_path):
                    jianying_controller.add_material_to_track(video_path)
                    time.sleep(0.5)  # 等待添加完成
        else:
            logger.error(f"不支持的处理模式: {process_mode}")
            return False
        
        # 调整音量（如果需要）
        if main_track_volume != 100:
            logger.info(f"设置主轨道音量: {main_track_volume}")
            jianying_controller.set_main_track_volume(main_track_volume)
        
        # 处理背景音乐
        if not keep_bgm:
            logger.info("删除背景音乐")
            jianying_controller.delete_bgm()
        elif bgm_volume != 50:
            logger.info(f"设置背景音乐音量: {bgm_volume}")
            jianying_controller.set_bgm_volume(bgm_volume)
        
        # 准备导出文件名
        if output_base_name:
            # 使用提供的基础名称
            filename_base = output_base_name
        else:
            # 使用时间戳命名
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename_base = f"processed_{timestamp}"
        
        # 确保输出文件夹存在
        os.makedirs(output_folder, exist_ok=True)
        
        # 构建完整输出路径
        output_path = os.path.join(output_folder, f"{filename_base}.mp4")
        
        # 导出视频
        export_result = jianying_controller.export_draft(output_path)
        
        if export_result:
            logger.info(f"成功导出到: {output_path}")
            return True
        else:
            logger.error("导出失败")
            return False
    
    except Exception as e:
        logger.error(f"处理视频时出错: {str(e)}")
        traceback.print_exc()
        return False

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
                   main_track_volume=100,  # 新增参数：主轨道音量(0-100)
                   segments_to_replace=None):  # 新增参数：素材替换段数
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
        segments_to_replace (int, optional): 需要替换的素材段数，默认为None表示使用模板中的所有段数。

    Returns:
        dict: 包含处理结果的字典，格式为 {"success": bool, "error": str|None}
    """
    logger.info(f"--- 开始处理剪映模板: {draft_name} ---")
    logger.info(f"  使用视频片段 ({len(video_paths)}): {', '.join(os.path.basename(p) for p in video_paths)}")
    logger.info(f"  草稿库路径: {draft_folder_path}")
    logger.info(f"  保留BGM: {keep_bgm}, BGM循环: {bgm_loop}, BGM音量: {bgm_volume}%, 主轨道音量: {main_track_volume}%")
    if segments_to_replace is not None:
        logger.info(f"  素材替换段数: {segments_to_replace}")
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
        
        # 修复Bug 1：确保有足够的素材用于替换所有片段
        try:
            # 记录原始检查逻辑
            has_errors = False
            for video_path in video_paths:
                if not os.path.exists(video_path):
                    logger.error(f"用于替换的视频文件不存在: {video_path}")
                    has_errors = True
                    continue
                logger.debug(f"  创建素材对象: {os.path.basename(video_path)}")
                try:
                    material = draft.Video_material(video_path)
                    # 添加name属性，使用文件名
                    material.name = os.path.basename(video_path)
                    # 手动重写一些常用的访问器
                    if not hasattr(material, 'filename'):
                        material.filename = os.path.basename(video_path)
                    video_materials.append(material)
                except Exception as mat_err:
                    logger.error(f"创建视频素材对象时出错 ({video_path}): {mat_err}")
                    has_errors = True
            
            if has_errors and not video_materials:
                raise FileNotFoundError(f"预期存在的视频片段未找到")
                
            # 如果至少成功创建了一个素材，我们就可以继续
            logger.info(f"成功为 {len(video_materials)} 个视频片段创建素材对象，耗时: {time.time() - mat_start:.2f}秒")
        except Exception as e:
            logger.error(f"创建视频素材对象时发生错误: {e}")
            raise

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
                 # 尝试继续处理，假设模板有片段
                 actual_segments_in_template = 1
                 logger.info("将假设模板至少有1个片段并尝试继续。")

            # 确定需要替换的片段数
            # 如果指定了segments_to_replace参数，则使用它，否则使用模板中的片段数
            required_segments = segments_to_replace if segments_to_replace is not None else actual_segments_in_template
            
            logger.info(f"模板轨道现有 {actual_segments_in_template} 个片段，需要替换 {required_segments} 个片段，提供了 {len(video_materials)} 个素材。")
            
            # 修复Bug 1: 处理素材数量小于需要替换的段数的情况
            # 无论素材数量如何，都继续进行处理，使用循环模式
            if len(video_materials) < required_segments:
                logger.warning(f"素材数量({len(video_materials)})小于需要替换的段数({required_segments})，将循环使用现有素材。")
                # 不再抛出异常，而是继续处理
            
            # 确定要替换的片段数量
            segments_to_iterate = min(actual_segments_in_template, required_segments)
            
            # 如果模板中的片段数量不够，发出警告
            if actual_segments_in_template < required_segments:
                logger.warning(f"警告：模板轨道片段数 ({actual_segments_in_template}) 少于需要替换的片段数 ({required_segments})。将只替换 {segments_to_iterate} 个片段。")
            
        except Exception as e:
            # 捕获所有异常并尝试继续
            logger.warning(f"确定替换片段数时出错: {e}，将使用可用的素材数量: {len(video_materials)}")
            segments_to_iterate = min(actual_segments_in_template or 4, num_segments_to_replace)
            logger.info(f"将尝试替换 {segments_to_iterate} 个片段")

        logger.info(f"准备替换模板中的 {segments_to_iterate} 个视频片段...")
        replace_start_time = time.time()
        
        # 计算主轨道音量
        normalized_main_volume = max(0, min(100, main_track_volume)) / 100.0
        logger.info(f"主轨道音量设置为: {main_track_volume}% (归一化值: {normalized_main_volume:.2f})")
        
        # 替换视频段
        logger.info(f"开始替换模板中的片段")
        replaced_segments = []
        error_list = []
        for i in range(segments_to_iterate):
            try:
                segment_index = i
                # 修复Bug 1: 使用模运算来循环重用素材
                material_index = i % len(video_materials)
                material = video_materials[material_index]
                material_name = getattr(material, 'name', os.path.basename(getattr(material, 'original_path', f"material_{material_index}")))
                logger.info(f"替换 模板片段索引 {segment_index} 使用素材: {material_name}")
                
                # 使用视频替换指定索引的片段
                script.replace_material_by_seg(
                    video_track,
                    segment_index,
                    material,
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
                
                # 记录替换结果
                replaced_segments.append({
                    "index": segment_index,
                    "material_path": getattr(material, 'original_path', "unknown"),
                    "material_name": material_name
                })
                logger.info(f"成功替换片段 {segment_index}")
            except Exception as e:
                logger.error(f"替换片段 {i} 时出错: {str(e)}")
                error_list.append(f"片段{i}替换失败: {str(e)}")
                continue

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
            max_retries = 3  # 从10次减少到3次重试
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