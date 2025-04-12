# 导入模块
import os
import pyJianYingDraft as draft
from pyJianYingDraft import Intro_type, Transition_type, trange, tim
from pyJianYingDraft import Export_resolution, Export_framerate

# 剪映草稿文件夹路径
DRAFT_FOLDER_PATH = r"D:\DJianYingDrafts\JianyingPro Drafts"  # 例如: "C:/Users/Username/JianyingPro Drafts"
DRAFT_NAME = "简单测试_4940"  # 例如: "我的草稿"

# 新素材路径 - 三段视频的路径
NEW_VIDEO_PATH1 = r"D:/123/椿沈以诚 炙热计划 无声卡清唱 吉他弹唱_split_part1.mp4"
NEW_VIDEO_PATH2 = r"D:/123/椿沈以诚 炙热计划 无声卡清唱 吉他弹唱_split_part2.mp4"  # 替换为第二个视频路径
NEW_VIDEO_PATH3 = r"D:/123/椿沈以诚 炙热计划 无声卡清唱 吉他弹唱_split_part3.mp4"  # 替换为第三个视频路径

# 音频替换设置
REPLACE_AUDIO = False  # 设置为True时才会替换音频
NEW_AUDIO_PATH = r""  # 如果需要替换音频，请在这里填写正确的音频文件路径

# 导出设置
EXPORT_VIDEO = True  # 是否导出视频
EXPORT_PATH = r"D:/123/导出视频"  # 导出视频的路径
EXPORT_FILENAME = "椿沈以诚_炙热计划.mp4"  # 导出视频的文件名

# 创建草稿文件夹管理器
draft_folder = draft.Draft_folder(DRAFT_FOLDER_PATH)

# 检查草稿是否存在
print(f"可用的草稿列表: {draft_folder.list_drafts()}")

# 加载草稿
try:
    # 直接加载现有草稿
    script = draft_folder.load_template(DRAFT_NAME)
    
    # 输出素材元数据，帮助您了解当前草稿中的素材
    print("当前草稿中的素材元数据:")
    script.inspect_material()
    
    # 创建新素材 - 三个视频素材
    new_video_material1 = draft.Video_material(NEW_VIDEO_PATH1)
    new_video_material2 = draft.Video_material(NEW_VIDEO_PATH2)
    new_video_material3 = draft.Video_material(NEW_VIDEO_PATH3)
    
    # 只有在需要替换音频时才创建音频素材
    if REPLACE_AUDIO and NEW_AUDIO_PATH:
        new_audio_material = draft.Audio_material(NEW_AUDIO_PATH)
    
    # 获取导入的轨道
    video_track = script.get_imported_track(draft.Track_type.video, index=0)  # 第一个视频轨道
    
    # 替换视频轨道上的三个片段
    print("替换第一个视频片段...")
    script.replace_material_by_seg(video_track, 0, new_video_material1)
    
    print("替换第二个视频片段...")
    script.replace_material_by_seg(video_track, 1, new_video_material2)
    
    print("替换第三个视频片段...")
    script.replace_material_by_seg(video_track, 2, new_video_material3)
    
    # 只有在需要替换音频时才替换音频
    if REPLACE_AUDIO and NEW_AUDIO_PATH:
        audio_track = script.get_imported_track(draft.Track_type.audio, index=0)  # 第一个音频轨道
        print("替换音频片段...")
        script.replace_material_by_seg(audio_track, 0, new_audio_material)
    
    # 直接保存回原草稿
    script.save()
    print(f"草稿已成功修改: {DRAFT_NAME}")
    
    # 导出视频
    if EXPORT_VIDEO:
        try:
            # 确保导出目录存在
            os.makedirs(EXPORT_PATH, exist_ok=True)
            
            export_file_path = os.path.join(EXPORT_PATH, EXPORT_FILENAME)
            print(f"开始导出视频到: {export_file_path}")
            
            # 创建剪映控制器
            ctrl = draft.Jianying_controller()
            
            # 导出草稿为视频
            # 注意: 这会打开剪映并控制UI，需要确保剪映已经打开并在主页面
            ctrl.export_draft(
                DRAFT_NAME,
                export_file_path,
                resolution=Export_resolution.RES_1080P,  # 1080P分辨率
                framerate=Export_framerate.FR_30        # 30fps帧率
            )
            
            print(f"视频导出完成: {export_file_path}")
        except Exception as ex:
            print(f"导出视频时出错: {ex}")
            print("提示: 请确保剪映已打开且位于主页面，且拥有导出权限")
    
except Exception as e:
    print(f"出错: {e}")
