# 导入模块
import os
import time
import pyJianYingDraft as draft
from pyJianYingDraft import Intro_type, Transition_type, trange, tim
from pyJianYingDraft import Export_resolution, Export_framerate
import uiautomation as uia
from collections import defaultdict
import datetime
import shutil

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
CUSTOMIZE_EXPORT = False  # 是否自定义导出参数（分辨率、帧率）

# UI控制优化设置
UI_SPEED_UP = True  # 是否加速UI操作

# 详细的UI等待时间配置（单位：秒）
# 小的值会使操作更快，但可能导致操作失败
UI_WAIT_TIMES = {
    "draft_click": 0.5,     # 点击草稿后等待时间（原值：10秒）
    "export_click": 0.5,    # 点击导出按钮后等待时间（原值：10秒）
    "resolution_click": 0.2, # 分辨率设置点击后等待时间（原值：0.5秒）
    "framerate_click": 0.2,  # 帧率设置点击后等待时间（原值：0.5秒）
    "export_button": 0.5,    # 点击最终导出按钮后等待时间（原值：5秒）
    "export_check": 0.1,     # 导出进度循环检查间隔（原值：1秒）
    "complete_wait": 0.2,    # 导出完成后等待时间（原值：2秒）
    "return_home": 0.2,      # 返回主页等待时间（原值：2秒）
    "window_search": 0.1,    # 窗口搜索等待时间
}

# 创建自定义的Jianying_controller类
class Fast_Jianying_Controller(draft.Jianying_controller):
    """速度优化的剪映控制器，完全重写导出功能"""
    
    def __init__(self, wait_times=None):
        """初始化速度优化的剪映控制器
        
        Args:
            wait_times: UI等待时间配置字典
        """
        self.wait_times = wait_times or {}
        # 操作耗时统计
        self.operation_times = defaultdict(float)
        self.total_sleep_time = 0
        self.operation_counts = defaultdict(int)
        self.start_time = time.time()
        
        # 调用父类初始化
        super().__init__()
    
    def timed_sleep(self, seconds, operation_name="未命名操作"):
        """计时的sleep函数"""
        # 根据操作类型获取配置的等待时间
        custom_seconds = self.wait_times.get(operation_name.lower().replace(" ", "_"), seconds)
        
        # 确保等待时间不会太小，以免操作失败
        custom_seconds = max(0.1, custom_seconds)
        
        # 记录操作时间
        sleep_start = time.time()
        print(f"  > {operation_name} 等待 {custom_seconds:.2f}秒...")
        
        # 实际sleep
        time.sleep(custom_seconds)
        
        # 计算实际耗时
        actual_sleep_time = time.time() - sleep_start
        self.operation_times[operation_name] += actual_sleep_time
        self.total_sleep_time += actual_sleep_time
        self.operation_counts[operation_name] += 1
    
    def export_draft(self, draft_name, output_path=None, *,
                     resolution=None, framerate=None, timeout=1200):
        """完全重写的导出草稿方法，减少不必要的等待时间"""
        print(f"开始导出 {draft_name} 至 {output_path}")
        export_start = time.time()
        
        try:
            # === 第1步：获取窗口并切换到主页 ===
            step_start = time.time()
            print("步骤1: 获取剪映窗口并切换到主页...")
            self.get_window_fast()
            self.switch_to_home_fast()
            print(f"  完成，耗时: {time.time() - step_start:.2f}秒")
            
            # === 第2步：点击对应草稿 ===
            step_start = time.time()
            print("步骤2: 点击目标草稿...")
            from pyJianYingDraft.jianying_controller import ControlFinder
            
            draft_name_text = self.app.TextControl(
                searchDepth=2,
                Compare=ControlFinder.desc_matcher(f"HomePageDraftTitle:{draft_name}", exact=True)
            )
            if not draft_name_text.Exists(0):
                raise draft.exceptions.DraftNotFound(f"未找到名为{draft_name}的剪映草稿")
            
            draft_btn = draft_name_text.GetParentControl()
            assert draft_btn is not None
            draft_btn.Click(simulateMove=False)
            self.timed_sleep(self.wait_times.get("draft_click", 1.0), "点击草稿等待")
            self.get_window_fast()
            print(f"  完成，耗时: {time.time() - step_start:.2f}秒")
            
            # === 第3步：点击导出按钮 ===
            step_start = time.time()
            print("步骤3: 点击导出按钮...")
            export_btn = self.app.TextControl(searchDepth=2, 
                                             Compare=ControlFinder.desc_matcher("MainWindowTitleBarExportBtn"))
            if not export_btn.Exists(0):
                raise draft.exceptions.AutomationError("未在编辑窗口中找到导出按钮")
            export_btn.Click(simulateMove=False)
            self.timed_sleep(self.wait_times.get("export_click", 1.0), "点击导出按钮等待")
            self.get_window_fast()
            print(f"  完成，耗时: {time.time() - step_start:.2f}秒")
            
            # === 第4步：获取原始导出路径 ===
            step_start = time.time()
            print("步骤4: 获取原始导出路径...")
            export_path_sib = self.app.TextControl(searchDepth=2, 
                                                  Compare=ControlFinder.desc_matcher("ExportPath"))
            if not export_path_sib.Exists(0):
                raise draft.exceptions.AutomationError("未找到导出路径框")
            export_path_text = export_path_sib.GetSiblingControl(lambda ctrl: True)
            assert export_path_text is not None
            export_path = export_path_text.GetPropertyValue(30159)
            print(f"  导出路径: {export_path}")
            print(f"  完成，耗时: {time.time() - step_start:.2f}秒")
            
            # === 第5步：设置分辨率（可选）===
            if resolution is not None:
                step_start = time.time()
                print(f"步骤5: 设置分辨率为 {resolution.value}...")
                setting_group = self.app.GroupControl(
                    searchDepth=1,
                    Compare=ControlFinder.class_name_matcher("PanelSettingsGroup_QMLTYPE")
                )
                if not setting_group.Exists(0):
                    raise draft.exceptions.AutomationError("未找到导出设置组")
                
                resolution_btn = setting_group.TextControl(
                    searchDepth=2, 
                    Compare=ControlFinder.desc_matcher("ExportSharpnessInput")
                )
                if not resolution_btn.Exists(0.2):
                    raise draft.exceptions.AutomationError("未找到导出分辨率下拉框")
                
                resolution_btn.Click(simulateMove=False)
                self.timed_sleep(self.wait_times.get("resolution_click", 0.2), "分辨率下拉框点击等待")
                
                resolution_item = self.app.TextControl(
                    searchDepth=2, 
                    Compare=ControlFinder.desc_matcher(resolution.value)
                )
                if not resolution_item.Exists(0.2):
                    raise draft.exceptions.AutomationError(f"未找到{resolution.value}分辨率选项")
                
                resolution_item.Click(simulateMove=False)
                self.timed_sleep(self.wait_times.get("resolution_click", 0.2), "分辨率选项点击等待")
                print(f"  完成，耗时: {time.time() - step_start:.2f}秒")
            
            # === 第6步：设置帧率（可选）===
            if framerate is not None:
                step_start = time.time()
                print(f"步骤6: 设置帧率为 {framerate.value}...")
                setting_group = self.app.GroupControl(
                    searchDepth=1,
                    Compare=ControlFinder.class_name_matcher("PanelSettingsGroup_QMLTYPE")
                )
                if not setting_group.Exists(0):
                    raise draft.exceptions.AutomationError("未找到导出设置组")
                
                framerate_btn = setting_group.TextControl(
                    searchDepth=2, 
                    Compare=ControlFinder.desc_matcher("FrameRateInput")
                )
                if not framerate_btn.Exists(0.2):
                    raise draft.exceptions.AutomationError("未找到导出帧率下拉框")
                
                framerate_btn.Click(simulateMove=False)
                self.timed_sleep(self.wait_times.get("framerate_click", 0.2), "帧率下拉框点击等待")
                
                framerate_item = self.app.TextControl(
                    searchDepth=2, 
                    Compare=ControlFinder.desc_matcher(framerate.value)
                )
                if not framerate_item.Exists(0.2):
                    raise draft.exceptions.AutomationError(f"未找到{framerate.value}帧率选项")
                
                framerate_item.Click(simulateMove=False)
                self.timed_sleep(self.wait_times.get("framerate_click", 0.2), "帧率选项点击等待")
                print(f"  完成，耗时: {time.time() - step_start:.2f}秒")
            
            # === 第7步：点击导出按钮，开始导出过程 ===
            step_start = time.time()
            print("步骤7: 点击最终导出按钮...")
            export_btn = self.app.TextControl(
                searchDepth=2, 
                Compare=ControlFinder.desc_matcher("ExportOkBtn", exact=True)
            )
            if not export_btn.Exists(0):
                raise draft.exceptions.AutomationError("未在导出窗口中找到导出按钮")
            
            export_btn.Click(simulateMove=False)
            self.timed_sleep(self.wait_times.get("export_button", 0.5), "最终导出按钮点击等待")
            print(f"  完成，耗时: {time.time() - step_start:.2f}秒")
            
            # === 第8步：等待导出完成 ===
            step_start = time.time()
            print("步骤8: 等待导出完成...")
            st = time.time()
            progress_checks = 0
            
            while True:
                progress_checks += 1
                self.get_window_fast()
                
                if self.app_status != "pre_export": 
                    print("  警告: 应用状态不是导出中，重新获取窗口...")
                    self.get_window_fast()
                    continue
                
                succeed_close_btn = self.app.TextControl(
                    searchDepth=2, 
                    Compare=ControlFinder.desc_matcher("ExportSucceedCloseBtn")
                )
                
                if succeed_close_btn.Exists(0):
                    print(f"  导出成功! 共检查进度 {progress_checks} 次")
                    succeed_close_btn.Click(simulateMove=False)
                    break
                
                if time.time() - st > timeout:
                    raise draft.exceptions.AutomationError(f"导出超时, 时限为{timeout}秒")
                
                # 更高效的等待
                self.timed_sleep(self.wait_times.get("export_check", 0.1), "导出进度检查")
                
                if progress_checks % 10 == 0:
                    remaining_time = timeout - (time.time() - st)
                    print(f"  进度检查 #{progress_checks}, 已等待 {time.time() - st:.1f}秒, 超时剩余 {remaining_time:.1f}秒")
            
            # 导出完成后的等待
            self.timed_sleep(self.wait_times.get("complete_wait", 0.2), "导出完成后等待")
            print(f"  完成，耗时: {time.time() - step_start:.2f}秒")
            
            # === 第9步：回到主页 ===
            step_start = time.time()
            print("步骤9: 返回剪映主页...")
            self.get_window_fast()
            self.switch_to_home_fast()
            self.timed_sleep(self.wait_times.get("return_home", 0.2), "返回主页等待")
            print(f"  完成，耗时: {time.time() - step_start:.2f}秒")
            
            # === 第10步：复制到指定路径（如果需要）===
            if output_path is not None:
                step_start = time.time()
                print(f"步骤10: 移动文件到目标路径 {output_path}...")
                try:
                    shutil.move(export_path, output_path)
                    print(f"  完成，耗时: {time.time() - step_start:.2f}秒")
                except Exception as e:
                    print(f"  移动文件失败: {e}")
                    print(f"  尝试复制文件...")
                    try:
                        shutil.copy(export_path, output_path)
                        print(f"  复制成功，耗时: {time.time() - step_start:.2f}秒")
                    except Exception as e2:
                        print(f"  复制也失败了: {e2}")
                        print(f"  原始文件可能仍在: {export_path}")
            
            print(f"导出 {draft_name} 至 {output_path} 完成")
            return True
            
        except Exception as e:
            print(f"导出过程中出错: {str(e)}")
            print("错误发生时的操作状态:")
            for op_name, count in self.operation_counts.items():
                print(f"  - {op_name}: 执行了 {count} 次")
            return False
            
        finally:
            # 计算总耗时
            total_time = time.time() - self.start_time
            export_time = time.time() - export_start
            
            # 打印耗时统计
            print("\n------ 导出操作耗时统计 ------")
            print(f"总耗时: {total_time:.2f}秒")
            print(f"导出函数耗时: {export_time:.2f}秒")
            print(f"总等待时间: {self.total_sleep_time:.2f}秒 ({self.total_sleep_time/total_time*100:.1f}%)")
            
            print("\n各操作等待时间:")
            for op_name, op_time in sorted(self.operation_times.items(), key=lambda x: x[1], reverse=True):
                count = self.operation_counts[op_name]
                avg_time = op_time / count if count > 0 else 0
                print(f"  {op_name}: {op_time:.2f}秒 ({op_time/self.total_sleep_time*100:.1f}%) - 次数: {count}次, 平均: {avg_time:.2f}秒/次")
            
            print("\n------ 统计结束 ------")
    
    def get_window_fast(self):
        """优化版的获取窗口函数"""
        if hasattr(self, "app") and self.app.Exists(0):
            self.app.SetTopmost(False)

        self.app = uia.WindowControl(searchDepth=1, Compare=self._jianying_window_cmp)
        if not self.app.Exists(0):
            raise draft.exceptions.AutomationError("剪映窗口未找到")

        # 寻找可能存在的导出窗口
        export_window = self.app.WindowControl(searchDepth=1, Name="导出")
        if export_window.Exists(0):
            self.app = export_window
            self.app_status = "pre_export"

        self.app.SetActive()
        self.app.SetTopmost()
        
        # 极短等待以确保窗口激活
        self.timed_sleep(self.wait_times.get("window_search", 0.1), "窗口激活等待")
    
    def _jianying_window_cmp(self, control, depth):
        """自定义的剪映窗口匹配函数"""
        if control.Name != "剪映专业版":
            return False
        if "HomePage".lower() in control.ClassName.lower():
            self.app_status = "home"
            return True
        if "MainWindow".lower() in control.ClassName.lower():
            self.app_status = "edit"
            return True
        return False
    
    def switch_to_home_fast(self):
        """优化版的切换到主页函数"""
        if self.app_status == "home":
            return
        if self.app_status != "edit":
            raise draft.exceptions.AutomationError("仅支持从编辑模式切换到主页")
        
        close_btn = self.app.GroupControl(searchDepth=1, ClassName="TitleBarButton", foundIndex=3)
        close_btn.Click(simulateMove=False)
        self.timed_sleep(self.wait_times.get("return_home", 0.2), "返回主页按钮点击等待")
        self.get_window_fast()

# 创建草稿文件夹管理器
draft_folder = draft.Draft_folder(DRAFT_FOLDER_PATH)

# 检查草稿是否存在
print(f"可用的草稿列表: {draft_folder.list_drafts()}")

# 记录整体操作时间
start_time = time.time()
material_start_time = 0
export_start_time = 0

# 加载草稿
try:
    # 直接加载现有草稿
    script_start_time = time.time()
    script = draft_folder.load_template(DRAFT_NAME)
    script_load_time = time.time() - script_start_time
    print(f"加载草稿耗时: {script_load_time:.2f}秒")
    
    # 输出素材元数据，帮助您了解当前草稿中的素材
    print("当前草稿中的素材元数据:")
    script.inspect_material()
    
    # 创建新素材 - 三个视频素材
    material_start_time = time.time()
    new_video_material1 = draft.Video_material(NEW_VIDEO_PATH1)
    new_video_material2 = draft.Video_material(NEW_VIDEO_PATH2)
    new_video_material3 = draft.Video_material(NEW_VIDEO_PATH3)
    material_load_time = time.time() - material_start_time
    print(f"加载视频素材耗时: {material_load_time:.2f}秒")
    
    # 只有在需要替换音频时才创建音频素材
    if REPLACE_AUDIO and NEW_AUDIO_PATH:
        audio_start_time = time.time()
        new_audio_material = draft.Audio_material(NEW_AUDIO_PATH)
        audio_load_time = time.time() - audio_start_time
        print(f"加载音频素材耗时: {audio_load_time:.2f}秒")
    
    # 获取导入的轨道
    track_start_time = time.time()
    video_track = script.get_imported_track(draft.Track_type.video, index=0)  # 第一个视频轨道
    track_load_time = time.time() - track_start_time
    print(f"获取轨道耗时: {track_load_time:.2f}秒")
    
    # 替换视频轨道上的三个片段
    replace_start_time = time.time()
    
    print("替换第一个视频片段...")
    seg1_start = time.time()
    script.replace_material_by_seg(video_track, 0, new_video_material1)
    print(f"  - 耗时: {time.time() - seg1_start:.2f}秒")
    
    print("替换第二个视频片段...")
    seg2_start = time.time()
    script.replace_material_by_seg(video_track, 1, new_video_material2)
    print(f"  - 耗时: {time.time() - seg2_start:.2f}秒")
    
    print("替换第三个视频片段...")
    seg3_start = time.time()
    script.replace_material_by_seg(video_track, 2, new_video_material3)
    print(f"  - 耗时: {time.time() - seg3_start:.2f}秒")
    
    replace_time = time.time() - replace_start_time
    print(f"替换视频片段总耗时: {replace_time:.2f}秒")
    
    # 只有在需要替换音频时才替换音频
    if REPLACE_AUDIO and NEW_AUDIO_PATH:
        audio_replace_start = time.time()
        audio_track = script.get_imported_track(draft.Track_type.audio, index=0)  # 第一个音频轨道
        print("替换音频片段...")
        script.replace_material_by_seg(audio_track, 0, new_audio_material)
        audio_replace_time = time.time() - audio_replace_start
        print(f"替换音频耗时: {audio_replace_time:.2f}秒")
    
    # 直接保存回原草稿
    save_start_time = time.time()
    script.save()
    save_time = time.time() - save_start_time
    print(f"保存草稿耗时: {save_time:.2f}秒")
    
    print(f"草稿已成功修改: {DRAFT_NAME}")
    
    # 导出视频
    if EXPORT_VIDEO:
        try:
            # 确保导出目录存在
            os.makedirs(EXPORT_PATH, exist_ok=True)
            
            export_file_path = os.path.join(EXPORT_PATH, EXPORT_FILENAME)
            print(f"开始导出视频到: {export_file_path}")
            
            # 使用自定义的高速剪映控制器
            export_start_time = time.time()
            if UI_SPEED_UP:
                print("使用速度优化的剪映控制器...")
                ctrl = Fast_Jianying_Controller(UI_WAIT_TIMES)
            else:
                ctrl = draft.Jianying_controller()
            
            # 导出草稿为视频
            # 注意: 这会打开剪映并控制UI，需要确保剪映已经打开并在主页面
            if CUSTOMIZE_EXPORT:
                # 使用自定义分辨率和帧率
                ctrl.export_draft(
                    DRAFT_NAME,
                    export_file_path,
                    resolution=Export_resolution.RES_1080P,
                    framerate=Export_framerate.FR_30
                )
            else:
                # 使用剪映默认设置，不修改分辨率和帧率
                ctrl.export_draft(
                    DRAFT_NAME,
                    export_file_path
                )
            
            export_time = time.time() - export_start_time
            print(f"视频导出总耗时: {export_time:.2f}秒")
            print(f"视频导出完成: {export_file_path}")
        except Exception as ex:
            print(f"导出视频时出错: {ex}")
            print("提示: 请确保剪映已打开且位于主页面，且拥有导出权限")
    
    # 打印总体时间统计
    total_time = time.time() - start_time
    print(f"\n总耗时: {total_time:.2f}秒")
    
except Exception as e:
    print(f"出错: {e}")
