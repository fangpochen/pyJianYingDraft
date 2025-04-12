# jianying_utils.py
# 包含与剪映交互的核心逻辑

import os
import time
import pyJianYingDraft as draft
from pyJianYingDraft import Export_resolution, Export_framerate
import uiautomation as uia
from collections import defaultdict
import datetime
import shutil
import logging # 导入日志模块
import subprocess # 用于调用 ffmpeg
import json # 用于解析 ffprobe 输出

# 获取该模块的 logger 实例
logger = logging.getLogger(__name__)

# 从 sample.py 迁移过来的全局配置，未来可以考虑放入配置文件或通过参数传递
UI_WAIT_TIMES = {
    "draft_click": 0.5,
    "export_click": 0.5,
    "resolution_click": 0.2,
    "framerate_click": 0.2,
    "export_button": 0.5,
    "export_check": 0.1,
    "complete_wait": 0.2,
    "return_home": 0.2,
    "window_search": 0.1,
}
CUSTOMIZE_EXPORT = False # 是否自定义导出（可以考虑做成参数）
EXPECTED_SEGMENTS = 3 # 期望的视频片段数量
USE_GPU_ACCEL = True # 是否尝试启用 GPU 加速 (解码和编码)
GPU_TYPE = 'nvidia' # GPU 厂商: 'nvidia', 'intel', 'amd' (用于选择 hwaccel 和编码器)

class Fast_Jianying_Controller(draft.Jianying_controller):
    """速度优化的剪映控制器，完全重写导出功能，增加日志回调"""
    
    def __init__(self, wait_times=None):
        """初始化速度优化的剪映控制器
        
        Args:
            wait_times: UI等待时间配置字典
        """
        self.wait_times = wait_times or UI_WAIT_TIMES # 使用传入的或默认的
        
        # 操作耗时统计
        self.operation_times = defaultdict(float)
        self.total_sleep_time = 0
        self.operation_counts = defaultdict(int)
        self.start_time = time.time()
        
        # 获取独立的 logger 实例，避免与其他实例混淆
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # 调用父类初始化（这里需要确保父类初始化不依赖特定的日志方式）
        super().__init__()

    def timed_sleep(self, seconds, operation_name="未命名操作"):
        """计时的sleep函数，使用标准 logging"""
        custom_seconds = self.wait_times.get(operation_name.lower().replace(" ", "_"), seconds)
        custom_seconds = max(0.1, custom_seconds)
        
        sleep_start = time.time()
        # 使用 DEBUG 级别记录等待信息，避免过多 INFO 日志
        self.logger.debug(f"  > {operation_name} 等待 {custom_seconds:.2f}秒...") 
        time.sleep(custom_seconds)
        
        actual_sleep_time = time.time() - sleep_start
        self.operation_times[operation_name] += actual_sleep_time
        self.total_sleep_time += actual_sleep_time
        self.operation_counts[operation_name] += 1
    
    def export_draft(self, draft_name, output_path=None, *,
                     resolution=None, framerate=None, timeout=1200):
        """完全重写的导出草稿方法，使用标准 logging"""
        self.logger.info(f"开始导出 {draft_name} 至 {output_path}")
        export_start = time.time()
        
        try:
            # === 第1步：获取窗口并切换到主页 ===
            step_start = time.time()
            self.logger.info("步骤1: 获取剪映窗口并切换到主页...")
            self.get_window_fast()
            self.switch_to_home_fast()
            self.logger.info(f"  完成，耗时: {time.time() - step_start:.2f}秒")
            
            # === 第2步：点击对应草稿 ===
            step_start = time.time()
            self.logger.info("步骤2: 点击目标草稿...")
            from pyJianYingDraft.jianying_controller import ControlFinder # 确保能访问
            
            draft_name_text = self.app.TextControl(
                searchDepth=2,
                Compare=ControlFinder.desc_matcher(f"HomePageDraftTitle:{draft_name}", exact=True)
            )
            if not draft_name_text.Exists(0):
                self.logger.error(f"未找到名为 '{draft_name}' 的剪映草稿") 
                raise draft.exceptions.DraftNotFound(f"未找到名为{draft_name}的剪映草稿")
            
            draft_btn = draft_name_text.GetParentControl()
            assert draft_btn is not None
            draft_btn.Click(simulateMove=False)
            self.timed_sleep(self.wait_times.get("draft_click", 1.0), "点击草稿等待")
            self.get_window_fast()
            self.logger.info(f"  完成，耗时: {time.time() - step_start:.2f}秒")
            
            # === 第3步：点击导出按钮 ===
            step_start = time.time()
            self.logger.info("步骤3: 点击导出按钮...")
            export_btn = self.app.TextControl(searchDepth=2, 
                                             Compare=ControlFinder.desc_matcher("MainWindowTitleBarExportBtn"))
            if not export_btn.Exists(0):
                self.logger.error("未在编辑窗口中找到导出按钮")
                raise draft.exceptions.AutomationError("未在编辑窗口中找到导出按钮")
            export_btn.Click(simulateMove=False)
            self.timed_sleep(self.wait_times.get("export_click", 1.0), "点击导出按钮等待")
            self.get_window_fast()
            self.logger.info(f"  完成，耗时: {time.time() - step_start:.2f}秒")
            
            # === 第4步：获取原始导出路径 ===
            step_start = time.time()
            self.logger.info("步骤4: 获取原始导出路径...")
            export_path_sib = self.app.TextControl(searchDepth=2, 
                                                  Compare=ControlFinder.desc_matcher("ExportPath"))
            if not export_path_sib.Exists(0):
                self.logger.error("未找到导出路径框")
                raise draft.exceptions.AutomationError("未找到导出路径框")
            export_path_text = export_path_sib.GetSiblingControl(lambda ctrl: True)
            assert export_path_text is not None
            export_path = export_path_text.GetPropertyValue(30159)
            self.logger.info(f"  导出路径: {export_path}")
            self.logger.info(f"  完成，耗时: {time.time() - step_start:.2f}秒")
            
            # === 第5步：设置分辨率（可选）===
            if resolution is not None:
                step_start = time.time()
                self.logger.info(f"步骤5: 设置分辨率为 {resolution.value}...")
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
                    self.logger.error("未找到导出分辨率下拉框")
                    raise draft.exceptions.AutomationError("未找到导出分辨率下拉框")
                
                resolution_btn.Click(simulateMove=False)
                self.timed_sleep(self.wait_times.get("resolution_click", 0.2), "分辨率下拉框点击等待")
                
                resolution_item = self.app.TextControl(
                    searchDepth=2, 
                    Compare=ControlFinder.desc_matcher(resolution.value)
                )
                if not resolution_item.Exists(0.2):
                    self.logger.error(f"未找到{resolution.value}分辨率选项")
                    raise draft.exceptions.AutomationError(f"未找到{resolution.value}分辨率选项")
                
                resolution_item.Click(simulateMove=False)
                self.timed_sleep(self.wait_times.get("resolution_click", 0.2), "分辨率选项点击等待")
                self.logger.info(f"  完成，耗时: {time.time() - step_start:.2f}秒")
            
            # === 第6步：设置帧率（可选）===
            if framerate is not None:
                step_start = time.time()
                self.logger.info(f"步骤6: 设置帧率为 {framerate.value}...")
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
                    self.logger.error("未找到导出帧率下拉框")
                    raise draft.exceptions.AutomationError("未找到导出帧率下拉框")
                
                framerate_btn.Click(simulateMove=False)
                self.timed_sleep(self.wait_times.get("framerate_click", 0.2), "帧率下拉框点击等待")
                
                framerate_item = self.app.TextControl(
                    searchDepth=2, 
                    Compare=ControlFinder.desc_matcher(framerate.value)
                )
                if not framerate_item.Exists(0.2):
                    self.logger.error(f"未找到{framerate.value}帧率选项")
                    raise draft.exceptions.AutomationError(f"未找到{framerate.value}帧率选项")
                
                framerate_item.Click(simulateMove=False)
                self.timed_sleep(self.wait_times.get("framerate_click", 0.2), "帧率选项点击等待")
                self.logger.info(f"  完成，耗时: {time.time() - step_start:.2f}秒")
            
            # === 第7步：点击导出按钮，开始导出过程 ===
            step_start = time.time()
            self.logger.info("步骤7: 点击最终导出按钮...")
            export_btn = self.app.TextControl(
                searchDepth=2, 
                Compare=ControlFinder.desc_matcher("ExportOkBtn", exact=True)
            )
            if not export_btn.Exists(0):
                self.logger.error("未在导出窗口中找到导出按钮")
                raise draft.exceptions.AutomationError("未在导出窗口中找到导出按钮")
            
            export_btn.Click(simulateMove=False)
            self.timed_sleep(self.wait_times.get("export_button", 0.5), "最终导出按钮点击等待")
            self.logger.info(f"  完成，耗时: {time.time() - step_start:.2f}秒")
            
            # === 第8步：等待导出完成 ===
            step_start = time.time()
            self.logger.info("步骤8: 等待导出完成...")
            st = time.time()
            progress_checks = 0
            
            while True:
                progress_checks += 1
                self.get_window_fast()
                
                if self.app_status != "pre_export": 
                    self.logger.warning("  警告: 应用状态不是导出中，重新获取窗口...")
                    self.get_window_fast()
                    continue
                
                succeed_close_btn = self.app.TextControl(
                    searchDepth=2, 
                    Compare=ControlFinder.desc_matcher("ExportSucceedCloseBtn")
                )
                
                if succeed_close_btn.Exists(0):
                    self.logger.info(f"  导出成功! 共检查进度 {progress_checks} 次")
                    succeed_close_btn.Click(simulateMove=False)
                    break
                
                if time.time() - st > timeout:
                    self.logger.error(f"导出超时, 时限为{timeout}秒")
                    raise draft.exceptions.AutomationError(f"导出超时, 时限为{timeout}秒")
                
                self.timed_sleep(self.wait_times.get("export_check", 0.1), "导出进度检查")
                
                if progress_checks % 10 == 0:
                    remaining_time = timeout - (time.time() - st)
                    self.logger.info(f"  进度检查 #{progress_checks}, 已等待 {time.time() - st:.1f}秒, 超时剩余 {remaining_time:.1f}秒")
            
            self.timed_sleep(self.wait_times.get("complete_wait", 0.2), "导出完成后等待")
            self.logger.info(f"  完成，耗时: {time.time() - step_start:.2f}秒")
            
            # === 第9步：回到主页 ===
            step_start = time.time()
            self.logger.info("步骤9: 返回剪映主页...")
            self.get_window_fast()
            self.switch_to_home_fast()
            self.timed_sleep(self.wait_times.get("return_home", 0.2), "返回主页等待")
            self.logger.info(f"  完成，耗时: {time.time() - step_start:.2f}秒")
            
            # === 第10步：移动/复制到指定路径（如果需要）===
            if output_path is not None:
                step_start = time.time()
                self.logger.info(f"步骤10: 移动文件到目标路径 {output_path}...")
                try:
                    shutil.move(export_path, output_path)
                    self.logger.info(f"  完成，耗时: {time.time() - step_start:.2f}秒")
                except Exception as e:
                    self.logger.warning(f"  移动文件失败: {e}")
                    self.logger.warning(f"  尝试复制文件...")
                    try:
                        shutil.copy(export_path, output_path)
                        self.logger.info(f"  复制成功，耗时: {time.time() - step_start:.2f}秒")
                    except Exception as e2:
                        self.logger.error(f"  复制也失败了: {e2}")
                        self.logger.warning(f"  警告: 导出文件可能仍在原始路径: {export_path}")
                        # 虽然复制失败，但导出本身是成功的，所以仍然返回True，但需要提醒用户
            
            self.logger.info(f"导出 {draft_name} 至 {output_path} 完成")
            return True # 表示导出操作成功（即使移动/复制可能失败）
            
        except Exception as e:
            self.logger.error(f"导出过程中出错: {str(e)}", exc_info=True)
            self.logger.info("错误发生时的操作状态:")
            for op_name, count in self.operation_counts.items():
                self.logger.info(f"  - {op_name}: 执行了 {count} 次")
            return False # 表示导出操作失败
            
        finally:
            # 计算总耗时
            total_time = time.time() - self.start_time
            export_time = time.time() - export_start
            
            # 打印耗时统计 (这些统计信息也通过日志回调输出)
            self.logger.debug("\n------ 导出操作耗时统计 ------")
            self.logger.debug(f"总耗时: {total_time:.2f}秒")
            self.logger.debug(f"导出函数耗时: {export_time:.2f}秒")
            # 避免除零错误
            total_time_safe = total_time if total_time > 0 else 1 
            self.logger.debug(f"总等待时间: {self.total_sleep_time:.2f}秒 ({self.total_sleep_time/total_time_safe*100:.1f}%)")
            
            self.logger.debug("\n各操作等待时间:")
            total_sleep_time_safe = self.total_sleep_time if self.total_sleep_time > 0 else 1
            for op_name, op_time in sorted(self.operation_times.items(), key=lambda x: x[1], reverse=True):
                count = self.operation_counts[op_name]
                avg_time = op_time / count if count > 0 else 0
                self.logger.debug(f"  {op_name}: {op_time:.2f}秒 ({op_time/total_sleep_time_safe*100:.1f}%) - 次数: {count}次, 平均: {avg_time:.2f}秒/次")
            
            self.logger.debug("\n------ 统计结束 ------")
    
    def get_window_fast(self):
        """获取剪映窗口并判断状态 (home/edit/pre_export)，优化查找方式"""
        self.logger.info("获取剪映窗口并判断状态...")
        
        # 1. 首先按名称查找主窗口
        self.app = uia.WindowControl(searchDepth=1, Name='剪映专业版')
        if not self.app.Exists(1.0): # 稍微增加一点查找时间
            self.logger.error("按名称 '剪映专业版' 未找到主窗口。")
            raise draft.exceptions.AutomationError("剪映窗口未找到")
        
        # 2. 判断窗口状态 (Home vs Edit) 基于 ClassName
        window_name = self.app.Name
        window_class_name = self.app.ClassName
        self.logger.debug(f"找到窗口: Name='{window_name}', ClassName='{window_class_name}'")
        
        class_name_lower = window_class_name.lower()
        if "homepage" in class_name_lower or "homewindow" in class_name_lower:
            self.app_status = "home"
            self.logger.info("窗口状态判断为: 主界面 (home)")
        elif "maineditorwindow" in class_name_lower or "mainwindow" in class_name_lower or "lvcompositionwindow" in class_name_lower:
            self.app_status = "edit"
            self.logger.info("窗口状态判断为: 编辑界面 (edit)")
        else:
            self.logger.error(f"无法根据 ClassName '{window_class_name}' 判断窗口状态 (home/edit)。")
            # 可以在这里尝试查找特定子控件作为后备判断，或者直接报错
            # raise draft.exceptions.AutomationError(f"无法识别的剪映窗口状态: {window_class_name}")
            # 为了继续尝试，暂时标记为 edit，但后续操作可能失败
            self.logger.warning("无法识别窗口状态，暂时假设为编辑界面 (edit)，后续操作可能失败。")
            self.app_status = "edit" 
            
        # 3. 检查是否存在导出窗口 (覆盖之前的状态)
        export_window = self.app.WindowControl(searchDepth=1, Name="导出")
        if export_window.Exists(0): # 导出窗口通常立即出现，不需要长等待
            self.logger.info("检测到 '导出' 子窗口，更新状态为 pre_export")
            self.app = export_window # 操作目标切换到导出窗口
            self.app_status = "pre_export"
        
        # 4. 尝试激活和置顶 (保持不变)
        try:
            self.app.SetActive()
            self.app.SetTopmost()
        except Exception as activate_error:
            self.logger.warning(f"警告：激活或置顶窗口时出错: {activate_error}")

        self.timed_sleep(self.wait_times.get("window_search", 0.1), "窗口激活等待")

    def switch_to_home_fast(self):
        """优化版的切换到主页函数"""
        if self.app_status == "home":
            return
        if self.app_status != "edit":
            # 使用日志记录代替 print
            self.logger.warning("尝试从非编辑模式切换到主页，当前状态: %s", self.app_status)
            # 尝试强制获取窗口并检查状态
            self.get_window_fast()
            if self.app_status == "home":
                self.logger.info("重新获取窗口后发现已在主页。")
                return
            elif self.app_status != "edit":
                 self.logger.error("无法从当前状态 (%s) 切换到主页。", self.app_status)
                 raise draft.exceptions.AutomationError(f"仅支持从编辑模式切换到主页, 当前状态: {self.app_status}")
            else:
                 self.logger.info("重新获取窗口后确认在编辑模式，继续切换。")

        try:
            # 定位关闭按钮更精确，避免依赖索引
            title_bar = self.app.GroupControl(searchDepth=1, ClassName="QMainWindowTitleBar")
            if not title_bar.Exists(0.1):
                 self.logger.warning("未能快速找到 QMainWindowTitleBar, 尝试备用方法...")
                 # 备用方法：尝试按索引查找，兼容旧逻辑，但发出警告
                 close_btn = self.app.GroupControl(searchDepth=1, ClassName="TitleBarButton", foundIndex=3)
            else:
                 # 在 TitleBar 内查找关闭按钮，描述符可能更稳定
                 # 注意：desc_matcher 可能需要根据实际情况调整
                 close_btn = title_bar.ButtonControl(searchDepth=1, Compare=draft.jianying_controller.ControlFinder.desc_matcher("TitleBarButtonType:CLOSE"))
                 if not close_btn.Exists(0.1):
                      self.logger.warning("在 TitleBar 中未找到描述符匹配的关闭按钮，尝试按 ClassName...")
                      close_btn = title_bar.ButtonControl(searchDepth=1, ClassName="TitleBarButton", foundIndex=3) # 假设关闭仍在第3个

            if not close_btn or not close_btn.Exists(0):
                self.logger.error("无法定位到编辑窗口的关闭/返回主页按钮。")
                raise draft.exceptions.AutomationError("无法定位到编辑窗口的关闭/返回主页按钮。")

            self.logger.debug("尝试点击关闭/返回主页按钮...")
            close_btn.Click(simulateMove=False)
            self.timed_sleep(self.wait_times.get("return_home", 0.2), "返回主页按钮点击等待")
            self.get_window_fast() # 切换后重新获取窗口状态
            if self.app_status != "home":
                self.logger.warning("点击返回按钮后，应用状态仍不是 'home' (%s)，可能切换未完全成功或过快。", self.app_status)
            else:
                self.logger.info("成功切换到主页。")
        except Exception as e:
             self.logger.exception("切换到主页时发生错误")
             raise draft.exceptions.AutomationError(f"切换到主页失败: {e}")

# --- Video Preparation Helper (Splitting) ---

def prepare_video_paths_for_batch(original_video_paths, output_folder_for_splits):
    """
    准备用于批次处理的视频路径列表。
    如果原始列表只有一个视频，则尝试将其切割成 EXPECTED_SEGMENTS 段。
    切割后的文件将放在 output_folder_for_splits 目录下。

    Args:
        original_video_paths (list): 批次原始的视频文件绝对路径列表。
        output_folder_for_splits (str): 用于存放切割后视频片段的文件夹路径。

    Returns:
        list or None: 成功则返回最终使用的视频路径列表 (可能是原始列表或切割后的列表)，
                      如果需要切割但切割失败或缺少输出目录，则返回 None。
    """
    if len(original_video_paths) == 1:
        single_video_path = original_video_paths[0]
        logger.info(f"检测到批次中只有一个视频文件: {os.path.basename(single_video_path)}，将尝试切割成 {EXPECTED_SEGMENTS} 段。")

        if not output_folder_for_splits:
            logger.error("需要切割视频，但未提供有效的输出文件夹路径来存放切割片段。")
            return None # 错误：缺少输出目录
        if not os.path.exists(single_video_path):
             logger.error(f"要切割的源视频文件不存在: {single_video_path}")
             return None # 错误：源文件不存在

        try:
            # 调用核心切割函数
            split_paths = split_video_ffmpeg(
                single_video_path,
                output_folder_for_splits,
                EXPECTED_SEGMENTS,
                USE_GPU_ACCEL # 传递 GPU 加速设置
            )

            if split_paths:
                logger.info(f"视频成功切割成 {len(split_paths)} 段。")
                return split_paths # 返回切割后的路径列表
            else:
                logger.error("视频切割过程失败。")
                return None # 错误：切割函数返回失败
        except Exception as split_err:
            logger.error(f"执行视频切割时发生意外错误: {split_err}", exc_info=True)
            return None # 错误：切割过程中抛出异常
    else:
        logger.info(f"批次包含 {len(original_video_paths)} 个视频文件，无需切割。")
        # 验证所有原始文件是否存在
        for video_path in original_video_paths:
            if not os.path.exists(video_path):
                logger.error(f"批次中的原始视频文件不存在: {video_path}")
                return None # 错误：原始文件缺失
        return original_video_paths # 返回原始路径列表

# --- FFmpeg Helper Function ---

def get_video_duration(video_path):
    """使用 ffprobe 获取视频时长 (秒)"""
    command = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', video_path
    ]
    try:
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        data = json.loads(result.stdout)
        duration = float(data['format']['duration'])
        logger.debug(f"获取 '{os.path.basename(video_path)}' 时长: {duration:.2f} 秒")
        return duration
    except FileNotFoundError:
        logger.error("ffprobe 命令未找到。请确保 FFmpeg 已安装并添加到系统 PATH。")
        raise
    except subprocess.CalledProcessError as e:
        logger.error(f"ffprobe 执行失败: {e}")
        logger.error(f"ffprobe 输出: {e.stderr}")
        raise RuntimeError(f"无法获取视频时长: {e.stderr}")
    except (KeyError, ValueError) as e:
        logger.error(f"解析 ffprobe 输出失败: {e}")
        raise RuntimeError(f"解析视频时长失败")
    except Exception as e:
        logger.exception(f"获取视频时长时发生未知错误: {video_path}")
        raise

def split_video_ffmpeg(input_path, output_folder, num_segments, use_copy=True):
    """使用 ffmpeg 将视频平均切割成指定数量的片段"""
    output_paths = []
    base_name, ext = os.path.splitext(os.path.basename(input_path))
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        logger.info(f"为切割文件创建输出文件夹: {output_folder}")

    try:
        duration = get_video_duration(input_path)
    except Exception as e:
        logger.error(f"无法获取视频时长，跳过切割: {e}")
        return None # 返回 None 表示切割失败

    segment_duration = duration / num_segments
    logger.info(f"准备将 '{base_name}{ext}' ({duration:.2f}s) 切割成 {num_segments} 段，每段约 {segment_duration:.2f}s")

    for i in range(num_segments):
        start_time = i * segment_duration
        output_filename = f"{base_name}_part{i+1}{ext}"
        output_path = os.path.join(output_folder, output_filename)

        command = ['ffmpeg'] # 初始化命令列表

        # --- 添加 -y 覆盖选项 ---
        command.append('-y')

        # --- 添加硬件加速解码选项 --- (在 -i 之前)
        hwaccel_added = False
        if USE_GPU_ACCEL:
            hwaccel_option_list = []
            if GPU_TYPE == 'nvidia':
                hwaccel_option_list = ['-hwaccel', 'cuda']
            elif GPU_TYPE == 'intel':
                hwaccel_option_list = ['-hwaccel', 'qsv']
            elif GPU_TYPE == 'amd':
                hwaccel_option_list = ['-hwaccel', 'dxva2']

            if hwaccel_option_list:
                command.extend(hwaccel_option_list)
                logger.info(f"  尝试使用 GPU 加速解码: {' '.join(hwaccel_option_list)}")
                hwaccel_added = True
            else:
                logger.warning(f"  配置了 USE_GPU_ACCEL=True 但 GPU_TYPE '{GPU_TYPE}' 不支持或未配置正确的 hwaccel 选项。")

        # --- 添加输入和时间参数 ---
        command.extend(['-i', input_path])
        command.extend(['-ss', str(start_time)])
        command.extend(['-t', str(segment_duration)])

        # --- 添加视频和音频编码参数 (替换 -c copy) ---
        codec_params_list = []
        if USE_GPU_ACCEL and GPU_TYPE == 'nvidia':
            logger.debug(f"使用 NVIDIA NVENC 编码 (第 {i+1} 段)")
            codec_params_list = [
                '-c:v', 'h264_nvenc',
                '-preset', 'p2',       # 用户指定的预设
                '-tune', 'hq',         # 用户指定的调整
                '-rc', 'vbr',          # 可变比特率
                '-cq', '23',           # 恒定质量级别
                '-b:v', '6M',           # 平均比特率
                '-maxrate', '10M',      # 最大比特率
                '-bufsize', '10M',      # 缓冲区大小
                '-spatial-aq', '1',    # 空间 AQ
                '-temporal-aq', '1',   # 时间 AQ
                '-profile:v', 'high'    # H.264 Profile
            ]
        else:
            if USE_GPU_ACCEL and GPU_TYPE != 'nvidia':
                 logger.warning(f"配置了 USE_GPU_ACCEL=True 但 GPU 类型为 '{GPU_TYPE}'，不支持 h264_nvenc，将回退到 libx264 软件编码。")
            logger.debug(f"使用 libx264 软件编码 (第 {i+1} 段)")
            codec_params_list = [
                '-c:v', 'libx264',
                '-preset', 'medium',   # CPU 编码预设
                '-crf', '23',           # 恒定速率因子 (质量)
                '-b:v', '6M',           # 平均比特率
                '-maxrate', '10M',      # 最大比特率
                '-bufsize', '10M',      # 缓冲区大小
                '-profile:v', 'high'    # H.264 Profile
            ]

        command.extend(codec_params_list)

        # --- 添加音频编码参数 ---
        command.extend(['-c:a', 'aac', '-b:a', '128k'])

        # --- 添加线程和优化参数 ---
        command.extend(['-threads', '10'])
        command.extend(['-movflags', '+faststart'])

        # --- 添加输出路径 ---
        command.append(output_path)

        logger.info(f"  执行切割命令 (第 {i+1}/{num_segments} 段): {' '.join(command)}")
        try:
            # 运行 ffmpeg 命令并捕获输出
            process_result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
            # 记录 ffmpeg 的输出 (stdout 和 stderr)，使用 DEBUG 级别避免刷屏
            if process_result.stdout:
                logger.debug(f"    ffmpeg stdout (第 {i+1} 段):\n{process_result.stdout.strip()}")
            if process_result.stderr:
                logger.debug(f"    ffmpeg stderr (第 {i+1} 段):\n{process_result.stderr.strip()}")

            if os.path.exists(output_path):
                output_paths.append(output_path)
                logger.info(f"    成功生成切割片段: {output_filename}")
            else:
                logger.error(f"    ffmpeg 命令执行成功但未找到输出文件: {output_filename}")
                raise RuntimeError(f"切割后文件未生成: {output_filename}")
        except FileNotFoundError:
            logger.error("ffmpeg 命令未找到。请确保 FFmpeg 已安装并添加到系统 PATH。")
            raise
        except subprocess.CalledProcessError as e:
            logger.error(f"ffmpeg 切割第 {i+1} 段失败: {e}")
            logger.error(f"ffmpeg 输出: {e.stderr}")
            # 如果一段失败，可能后续也无意义，可以选择直接返回失败
            raise RuntimeError(f"ffmpeg 切割失败: {e.stderr}")
        except Exception as e:
            logger.exception(f"切割第 {i+1} 段时发生未知错误")
            raise

    if len(output_paths) == num_segments:
        logger.info(f"视频成功切割成 {num_segments} 段。")
        return output_paths
    else:
        logger.error(f"切割过程未生成所有期望的片段 ({len(output_paths)}/{num_segments})。")
        return None # 返回 None 表示切割不完整

# --- Core Processing Function ---

def process_videos(video_paths,
                   draft_name,
                   draft_folder_path,
                   export_video=False,
                   export_path=None,
                   export_filename=None):
    """
    处理单个视频批次（假设视频路径已准备好）：加载模板，替换片段，保存，导出。

    Args:
        video_paths (list): 最终用于替换的视频文件绝对路径列表 (可能已被切割)。
        draft_name (str): 要使用的模板草稿的名称。
        draft_folder_path (str): 剪映草稿库的路径。
        export_video (bool): 是否导出视频。
        export_path (str, optional): 导出视频的目标文件夹路径。
        export_filename (str, optional): 导出视频的文件名。

    Returns:
        dict: 包含处理结果的字典，格式为 {"success": bool, "error": str|None}
    """
    logger.info(f"--- 开始处理批次，使用模板: {draft_name} ---")
    logger.info(f"  最终使用的视频文件 ({len(video_paths)}): {', '.join(os.path.basename(p) for p in video_paths)}")
    logger.info(f"  草稿库路径: {draft_folder_path}")
    if export_video:
        logger.info(f"  导出设置: 启用")
        if not export_path or not export_filename:
            logger.error("需要导出视频，但未提供 export_path 或 export_filename。")
            # 这里需要小心，如果是因为切割而没有 export_path，上面已经返回错误了
            # 但如果是因为正常流程缺少，这里需要再次检查
            return {"success": False, "error": "导出路径或文件名缺失"}
        export_file_path = os.path.join(export_path, export_filename)
        logger.info(f"    导出目标: {export_file_path}")
    else:
        logger.info(f"  导出设置: 禁用")

    result = {"success": False, "error": None}
    script = None

    try:
        # 1. 初始化 Draft_folder
        logger.debug("初始化草稿文件夹管理器...")
        draft_folder = draft.Draft_folder(draft_folder_path)
        # 可选：检查模板是否存在于列表中，提前失败
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

        # 3. 创建视频素材对象 (使用可能已被切割替换的 video_paths)
        logger.info("创建视频素材对象...")
        mat_start = time.time()
        video_materials = []
        for video_path in video_paths:
            if not os.path.exists(video_path):
                # 如果是切割后的文件找不到，可能是切割或移动环节出问题
                if "_part" in os.path.basename(video_path):
                     logger.error(f"切割后的视频文件不存在: {video_path}")
                     raise FileNotFoundError(f"切割生成的视频文件未找到: {video_path}")
                else:
                     logger.error(f"输入视频文件不存在: {video_path}")
                     raise FileNotFoundError(f"视频文件不存在: {video_path}")
            logger.debug(f"  创建素材对象: {os.path.basename(video_path)}")
            video_materials.append(draft.Video_material(video_path))
        logger.info(f"成功为 {len(video_materials)} 个视频创建素材对象，耗时: {time.time() - mat_start:.2f}秒")

        # 4. 获取视频轨道 (假设是第一个视频轨道)
        logger.info("获取第一个视频轨道...")
        track_start = time.time()
        try:
            video_track = script.get_imported_track(draft.Track_type.video, index=0)
        except IndexError:
             logger.error(f"模板草稿 '{draft_name}' 中找不到索引为 0 的视频轨道。")
             raise IndexError(f"模板草稿 '{draft_name}' 中没有视频轨道。")
        logger.info(f"视频轨道获取成功，耗时: {time.time() - track_start:.2f}秒")

        # 5. 替换视频片段
        num_segments_to_replace = len(video_materials)
        try:
            actual_segments = len(video_track.segments)
            logger.info(f"模板轨道现有 {actual_segments} 个片段，需要替换 {num_segments_to_replace} 个。")
            if actual_segments < num_segments_to_replace:
                 logger.warning(f"警告：模板轨道片段数 ({actual_segments}) 少于处理后视频数 ({num_segments_to_replace})！将只替换前 {actual_segments} 个片段。")
                 num_segments_to_replace = actual_segments
            elif actual_segments > num_segments_to_replace:
                 logger.warning(f"警告：模板轨道片段数 ({actual_segments}) 多于处理后视频数 ({num_segments_to_replace})。将只替换前 {num_segments_to_replace} 个片段，后续片段将保留原样。")
        except Exception as e:
             logger.warning(f"无法准确获取轨道片段数 ({e})，将假设数量足够并尝试替换 {num_segments_to_replace} 个。")

        logger.info(f"准备替换模板中的 {num_segments_to_replace} 个视频片段...")
        replace_start_time = time.time()
        for i in range(num_segments_to_replace):
            segment_log_name = f"第 {i+1}/{num_segments_to_replace} 个片段"
            video_file_basename = os.path.basename(video_paths[i])
            logger.info(f"  替换 {segment_log_name} -> {video_file_basename}")
            try:
                replace_seg_start = time.time()
                script.replace_material_by_seg(video_track, i, video_materials[i])
                logger.debug(f"    替换耗时: {time.time() - replace_seg_start:.2f}秒")
            except IndexError:
                 # 使用更新后的 video_paths 列表长度
                 error_msg = f"尝试替换索引为 {i} 的片段时出错。模板草稿 '{draft_name}' 的视频轨道可能没有足够的片段来匹配处理后的视频数量 ({len(video_paths)})。"
                 logger.error(error_msg)
                 raise IndexError(error_msg)
            except Exception as replace_err:
                 logger.error(f"替换 {segment_log_name} ({video_file_basename}) 时发生错误: {replace_err}", exc_info=True)
                 raise

        replace_time = time.time() - replace_start_time
        logger.info(f"视频片段替换完成，耗时: {replace_time:.2f}秒.")

        # 6. 保存修改回原草稿 (覆盖)
        logger.warning(f"注意：即将保存修改，这将覆盖原始模板草稿 '{draft_name}'！")
        logger.info(f"保存修改到草稿: {draft_name}")
        save_start_time = time.time()
        script.save()
        save_time = time.time() - save_start_time
        logger.info(f"草稿保存成功，耗时: {save_time:.2f}秒.")

        # 7. 导出视频 (如果需要)
        if export_video:
            logger.info(f"准备导出视频到: {export_file_path}")
            # 确保导出目录存在
            try:
                os.makedirs(export_path, exist_ok=True)
                logger.debug(f"确认导出目录存在或已创建: {export_path}")
            except Exception as e:
                 logger.error(f"无法创建导出目录 '{export_path}': {e}", exc_info=True)
                 raise IOError(f"创建导出目录失败: {export_path}") from e

            ctrl = Fast_Jianying_Controller() # 使用本文件定义的优化控制器
            logger.info("使用速度优化的剪映控制器进行导出...")

            export_start = time.time()
            export_success = ctrl.export_draft(
                draft_name=draft_name,
                output_path=export_file_path,
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
                raise RuntimeError(error_msg)
        else:
             logger.info("跳过视频导出步骤。")
             result["success"] = True

    except draft.exceptions.DraftNotFound as e:
        error_msg = f"处理失败：找不到模板草稿 '{draft_name}' 或其在列表中不存在。错误: {e}"
        logger.error(error_msg)
        result["error"] = error_msg
    except FileNotFoundError as e:
         error_msg = f"处理失败：找不到视频文件。错误: {e}"
         logger.error(error_msg)
         result["error"] = str(e)
    except IndexError as e:
        error_msg = f"处理失败：{e}" # 错误信息已包含细节
        logger.error(error_msg)
        result["error"] = error_msg
    except draft.exceptions.AutomationError as e:
        error_msg = f"处理失败：剪映 UI 自动化错误。错误: {e}"
        logger.error(error_msg, exc_info=True)
        result["error"] = f"剪映 UI 自动化错误: {e}"
    except IOError as e:
         error_msg = f"处理失败：文件系统错误。错误: {e}"
         logger.error(error_msg)
         result["error"] = error_msg
    except RuntimeError as e:
         error_msg = f"处理失败：导出或切割步骤失败。错误: {e}" # 调整了RuntimeError的消息
         logger.error(error_msg)
         result["error"] = error_msg
    except Exception as e:
        error_msg = f"处理批次时发生未知错误"
        logger.exception(error_msg)
        result["error"] = f"未知错误: {str(e)}"
    finally:
        status_msg = "成功" if result["success"] else f"失败 ({result['error']})"
        logger.info(f"--- 批次处理结束: {draft_name} | 结果: {status_msg} ---")

    return result 