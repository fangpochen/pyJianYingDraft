def process_videos(video_paths, draft_name, draft_folder_path, export_video=True, export_path=None, 
                export_filename=None, original_duration_seconds=None, keep_bgm=True):
    """
    Process videos using the Jianying template.

    Args:
        video_paths (list): List of video file paths to process.
        draft_name (str): Name of the Jianying draft template to use.
        draft_folder_path (str): Path to the Jianying draft folder.
        export_video (bool): Whether to export the processed video.
        export_path (str): Path to export the processed video to.
        export_filename (str): Filename for the exported video.
        original_duration_seconds (float): Original duration of the video, for logging purposes.
        keep_bgm (bool): Whether to keep the template's background music. Defaults to True.

    Returns:
        dict: Result of the processing operation.
    """
    logger.info(f"使用剪映处理 {len(video_paths)} 个视频片段...")
    logger.info(f"使用模板: {draft_name}")
    logger.info(f"草稿库路径: {draft_folder_path}")
    logger.debug(f"导出设置: export_video={export_video}, export_path={export_path}, export_filename={export_filename}")
    logger.debug(f"保留模板BGM: {keep_bgm}")

    try:
        # 获取剪映草稿JSON文件路径
        draft_json_path = jianying_finder.find_draft_json(draft_name, draft_folder_path)
        if not draft_json_path:
            logger.error(f"找不到模板 '{draft_name}' 在路径 '{draft_folder_path}'")
            return {
                'success': False,
                'message': f"找不到模板 '{draft_name}' 在路径 '{draft_folder_path}'"
            }
        
        logger.debug(f"找到草稿JSON文件: {draft_json_path}")
        
        # 创建草稿处理器
        draft_handler = draft_manager.JianyingDraftHandler(draft_json_path)
        
        # 检查草稿中的素材是否已经存在
        logger.debug("检查草稿中的素材...")
        
        # 移除草稿中的现有视频素材
        draft_handler.remove_all_videos()
        
        # 根据keep_bgm设置决定是否移除BGM
        if not keep_bgm:
            draft_handler.remove_all_audio()
            logger.debug("已移除所有BGM")
        
        # 添加新的视频素材
        logger.debug("添加新视频...")
        
        # ... existing code ... 
    except Exception as e:
        logger.error(f"处理视频时发生错误: {e}")
        return {
            'success': False,
            'message': f"处理视频时发生错误: {e}"
        }

    return {
        'success': True,
        'message': "视频处理成功"
    } 