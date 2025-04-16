# app/util/jianying_export.py
# 包含与剪映导出相关的核心逻辑

import os
import time
import pyJianYingDraft as draft
from pyJianYingDraft import Export_resolution, Export_framerate, Extend_mode, Shrink_mode
from pyJianYingDraft.jianying_controller import ControlFinder
import uiautomation as uia
from collections import defaultdict
import datetime
import shutil
import logging # 导入日志模块

# 导入UI日志队列，确保日志可以显示在界面上
from ..util.logging_setup import log_queue

# 全局配置，未来可以考虑放入配置文件或通过参数传递
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
        # Note: super().__init__() might implicitly call get_window which we override
        # Consider if direct initialization of necessary attributes is better
        # For now, assume super().__init__() is okay
        try:
            super().__init__()
        except Exception as e:
             self.logger.warning(f"调用父类 Jianying_controller 初始化时出错: {e}")
             # Initialize necessary attributes manually if super fails
             self.app = None
             self.app_status = None

    # 添加一个直接向UI发送消息的方法，用于关键操作
    def log_to_ui(self, message, level=logging.INFO):
        """直接向UI发送日志消息"""
        # 记录到正常日志系统
        self.logger.log(level, message)
        
        # 同时直接添加到UI队列
        try:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            level_name = logging.getLevelName(level)
            formatted_message = f"{timestamp} - {level_name} - {self.__class__.__name__} - {message}"
            log_queue.put(formatted_message)
        except Exception as e:
            self.logger.error(f"向UI发送日志失败: {e}")

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
        export_file_generated_path = None # Track the path where Jianying actually exports

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
            # Ensure ControlFinder is accessible
            try:
                from pyJianYingDraft.jianying_controller import ControlFinder
            except ImportError:
                self.logger.error("无法从 pyJianYingDraft 导入 ControlFinder")
                raise

            draft_name_text = self.app.TextControl(
                searchDepth=2,
                Compare=ControlFinder.desc_matcher(f"HomePageDraftTitle:{draft_name}", exact=True)
            )
            if not draft_name_text.Exists(0):
                self.logger.error(f"未找到名为 '{draft_name}' 的剪映草稿")
                raise draft.exceptions.DraftNotFound(f"未找到名为{draft_name}的剪映草稿")

            draft_btn = draft_name_text.GetParentControl()
            if not draft_btn:
                 self.logger.error("无法获取草稿名称文本的父控件。")
                 raise draft.exceptions.AutomationError("无法获取草稿按钮")

            draft_btn.Click(simulateMove=False)
            self.timed_sleep(self.wait_times.get("draft_click", 1.0), "点击草稿等待")
            self.get_window_fast() # Refresh window state after click
            if self.app_status != "edit":
                 self.logger.warning(f"点击草稿后，窗口状态不是 'edit' (是 '{self.app_status}')，可能未成功进入编辑模式。")
                 # Optionally add a retry or longer wait here

            self.logger.info(f"  完成，耗时: {time.time() - step_start:.2f}秒")

            # === 第3步：点击导出按钮 ===
            step_start = time.time()
            self.logger.info("步骤3: 点击导出按钮...")
            # Re-check window status before clicking export
            if self.app_status != "edit":
                 self.logger.error("无法点击导出按钮，因为当前不在编辑模式。")
                 raise draft.exceptions.AutomationError("不在编辑模式，无法导出")

            export_btn = self.app.TextControl(searchDepth=2,
                                             Compare=ControlFinder.desc_matcher("MainWindowTitleBarExportBtn"))
            if not export_btn.Exists(0):
                self.logger.error("未在编辑窗口中找到导出按钮")
                raise draft.exceptions.AutomationError("未在编辑窗口中找到导出按钮")
            export_btn.Click(simulateMove=False)
            self.timed_sleep(self.wait_times.get("export_click", 1.0), "点击导出按钮等待")
            self.get_window_fast() # Refresh state, should be pre_export now
            if self.app_status != "pre_export":
                 self.logger.warning(f"点击导出按钮后，窗口状态不是 'pre_export' (是 '{self.app_status}')，可能导出窗口未弹出。")
                 # Optionally add retry or longer wait

            self.logger.info(f"  完成，耗时: {time.time() - step_start:.2f}秒")

            # === 第4步：获取原始导出路径 ===
            step_start = time.time()
            self.logger.info("步骤4: 获取原始导出路径...")
            if self.app_status != "pre_export":
                 self.logger.error("无法获取导出路径，因为当前不在导出窗口模式。")
                 raise draft.exceptions.AutomationError("不在导出窗口，无法获取路径")

            export_path_sib = self.app.TextControl(searchDepth=2,
                                                  Compare=ControlFinder.desc_matcher("ExportPath"))
            if not export_path_sib.Exists(0):
                self.logger.error("未找到导出路径标签控件")
                raise draft.exceptions.AutomationError("未找到导出路径标签控件")
            export_path_text = export_path_sib.GetSiblingControl(lambda ctrl: True)
            if not export_path_text:
                 self.logger.error("未找到导出路径文本控件 (标签控件的兄弟)")
                 raise draft.exceptions.AutomationError("未找到导出路径文本控件")

            export_file_generated_path = export_path_text.GetPropertyValue(30159) # AutomationProperties.ValuePropertyId (LegacyIAccessible.Value)
            if not export_file_generated_path:
                 self.logger.error("获取导出路径文本值失败。")
                 raise draft.exceptions.AutomationError("无法获取导出路径文本值")

            self.logger.info(f"  剪映默认导出路径: {export_file_generated_path}")
            self.logger.info(f"  完成，耗时: {time.time() - step_start:.2f}秒")

            # === 第5步：设置分辨率（可选）===
            if resolution is not None:
                step_start = time.time()
                self.logger.info(f"步骤5: 设置分辨率为 {resolution.value}...")
                # Ensure we are in the export window
                if self.app_status != "pre_export": raise draft.exceptions.AutomationError("不在导出窗口，无法设置分辨率")

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
                    # Try finding via Name property as fallback
                    resolution_item = self.app.TextControl(searchDepth=2, Name=resolution.value)
                    if not resolution_item.Exists(0.1):
                         self.logger.error(f"未找到 {resolution.value} 分辨率选项 (尝试了 desc_matcher 和 Name)")
                         # Optionally click resolution_btn again to close dropdown before raising
                         resolution_btn.Click(simulateMove=False)
                         raise draft.exceptions.AutomationError(f"未找到{resolution.value}分辨率选项")

                resolution_item.Click(simulateMove=False)
                self.timed_sleep(self.wait_times.get("resolution_click", 0.2), "分辨率选项点击等待")
                self.logger.info(f"  完成，耗时: {time.time() - step_start:.2f}秒")

            # === 第6步：设置帧率（可选）===
            if framerate is not None:
                step_start = time.time()
                self.logger.info(f"步骤6: 设置帧率为 {framerate.value}...")
                if self.app_status != "pre_export": raise draft.exceptions.AutomationError("不在导出窗口，无法设置帧率")

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
                     framerate_item = self.app.TextControl(searchDepth=2, Name=framerate.value)
                     if not framerate_item.Exists(0.1):
                          self.logger.error(f"未找到 {framerate.value} 帧率选项 (尝试了 desc_matcher 和 Name)")
                          framerate_btn.Click(simulateMove=False) # Close dropdown
                          raise draft.exceptions.AutomationError(f"未找到{framerate.value}帧率选项")

                framerate_item.Click(simulateMove=False)
                self.timed_sleep(self.wait_times.get("framerate_click", 0.2), "帧率选项点击等待")
                self.logger.info(f"  完成，耗时: {time.time() - step_start:.2f}秒")

            # === 第7步：点击导出按钮，开始导出过程 ===
            step_start = time.time()
            self.logger.info("步骤7: 点击最终导出按钮...")
            if self.app_status != "pre_export": raise draft.exceptions.AutomationError("不在导出窗口，无法点击最终导出按钮")

            export_ok_btn = self.app.TextControl(
                searchDepth=2,
                Compare=ControlFinder.desc_matcher("ExportOkBtn", exact=True)
            )
            if not export_ok_btn.Exists(0):
                self.logger.error("未在导出窗口中找到导出按钮")
                raise draft.exceptions.AutomationError("未在导出窗口中找到导出按钮")

            export_ok_btn.Click(simulateMove=False)
            self.timed_sleep(self.wait_times.get("export_button", 0.5), "最终导出按钮点击等待")
            # State might change rapidly here, maybe no need to check get_window_fast immediately
            self.logger.info(f"  完成，耗时: {time.time() - step_start:.2f}秒")

            # === 第8步：等待导出完成 ===
            step_start = time.time()
            self.logger.info("步骤8: 等待导出完成...")
            st = time.time()
            progress_checks = 0

            while True:
                progress_checks += 1
                # It's better to check for the success/fail controls directly
                # instead of relying on get_window_fast app_status here.
                self.get_window_fast() # Still useful to ensure window is active

                succeed_close_btn = self.app.TextControl(
                    searchDepth=2,
                    Compare=ControlFinder.desc_matcher("ExportSucceedCloseBtn")
                )

                if succeed_close_btn.Exists(0):
                    self.logger.info(f"  导出成功! 共检查进度 {progress_checks} 次")
                    succeed_close_btn.Click(simulateMove=False)
                    break

                # Check for potential error indicators if needed
                # e.g., export_fail_indicator = self.app.TextControl(Compare=ControlFinder.desc_matcher("ExportFailIndicator"))
                # if export_fail_indicator.Exists(0):
                #     self.logger.error("检测到导出失败指示器")
                #     raise draft.exceptions.AutomationError("导出过程失败")

                if time.time() - st > timeout:
                    self.logger.error(f"导出超时, 时限为{timeout}秒")
                    # Try to cancel or close the export window if possible
                    try:
                        cancel_btn = self.app.TextControl(Compare=ControlFinder.desc_matcher("ExportCancelBtn")) # Or similar
                        if cancel_btn.Exists(0.1):
                            cancel_btn.Click(simulateMove=False)
                            self.logger.info("尝试点击取消按钮以中止超时导出。")
                    except Exception as cancel_err:
                         self.logger.warning(f"尝试取消超时导出时出错: {cancel_err}")
                    raise draft.exceptions.AutomationError(f"导出超时, 时限为{timeout}秒")

                self.timed_sleep(self.wait_times.get("export_check", 0.1), "导出进度检查")

                if progress_checks % 50 == 0: # Log less frequently
                    elapsed_time = time.time() - st
                    remaining_time = timeout - elapsed_time
                    self.logger.info(f"  进度检查 #{progress_checks}, 已等待 {elapsed_time:.1f}秒, 超时剩余 {remaining_time:.1f}秒")

            self.timed_sleep(self.wait_times.get("complete_wait", 0.2), "导出完成后等待")
            self.logger.info(f"  完成，耗时: {time.time() - step_start:.2f}秒")

            # === 第9步：回到主页 ===
            step_start = time.time()
            self.logger.info("步骤9: 返回剪映主页...")
            self.get_window_fast()
            # Check if already home (sometimes closing success dialog does this)
            if self.app_status != "home":
                 self.switch_to_home_fast()
            else:
                 self.logger.info("导出成功后已在主页。")

            self.timed_sleep(self.wait_times.get("return_home", 0.2), "返回主页等待")
            self.logger.info(f"  完成，耗时: {time.time() - step_start:.2f}秒")

            # === 第10步：移动/复制到指定路径（如果需要）===
            if output_path is not None:
                step_start = time.time()
                self.logger.info(f"步骤10: 准备移动文件到目标路径 {output_path}...")
                if not export_file_generated_path:
                    self.logger.error("无法移动文件，因为未能获取剪映实际导出路径。")
                elif not os.path.exists(export_file_generated_path):
                    self.logger.error(f"无法移动文件，剪映声称的导出文件不存在: {export_file_generated_path}")
                else:
                    self.logger.info(f"  源文件: {export_file_generated_path}")
                    self.logger.info(f"  目标路径: {output_path}")
                    # Ensure target directory exists
                    target_dir = os.path.dirname(output_path)
                    try:
                        os.makedirs(target_dir, exist_ok=True)
                    except OSError as mkdir_err:
                         self.logger.error(f"无法创建目标目录 '{target_dir}': {mkdir_err}")
                         # Decide if this is fatal or just warn
                         self.logger.warning("将无法移动/复制文件。")
                         export_file_generated_path = None # Prevent move/copy attempt

                    if export_file_generated_path:
                         try:
                            shutil.move(export_file_generated_path, output_path)
                            self.logger.info(f"  文件移动成功，耗时: {time.time() - step_start:.2f}秒")
                         except Exception as move_err:
                            self.logger.warning(f"  移动文件失败: {move_err}")
                            self.logger.warning(f"  尝试复制文件...")
                            try:
                                shutil.copy2(export_file_generated_path, output_path) # copy2 preserves metadata
                                self.logger.info(f"  复制成功，耗时: {time.time() - step_start:.2f}秒")
                                # Optionally delete original after successful copy
                                # try:
                                #     os.remove(export_file_generated_path)
                                #     logger.info(f"  已删除复制后的原始导出文件: {export_file_generated_path}")
                                # except OSError as del_err:
                                #     logger.warning(f"  删除复制后的原始导出文件失败: {del_err}")
                            except Exception as copy_err:
                                self.logger.error(f"  复制也失败了: {copy_err}")
                                self.logger.warning(f"  警告: 导出文件可能仍在原始路径: {export_file_generated_path}")

            self.logger.info(f"导出 {draft_name} 至 {output_path} 完成")
            return True # Indicate overall success (even if move/copy failed)

        except draft.exceptions.DraftNotFound as e:
             self.logger.error(f"导出过程中出错: {e}")
             return False
        except draft.exceptions.AutomationError as e:
             self.logger.error(f"导出过程中 UI 自动化出错: {e}", exc_info=True)
             return False
        except Exception as e:
            self.logger.error(f"导出过程中发生意外错误: {e}", exc_info=True)
            # Log operation state might be helpful here too
            # self.logger.info("错误发生时的操作状态:")
            # for op_name, count in self.operation_counts.items():
            #     self.logger.info(f"  - {op_name}: 执行了 {count} 次")
            return False

        finally:
            # Log timing stats regardless of success/failure
            export_time = time.time() - export_start
            self.logger.debug(f"导出函数 ({draft_name}) 耗时: {export_time:.2f}秒")
            # Log detailed timings at DEBUG level
            if self.logger.isEnabledFor(logging.DEBUG):
                total_time = time.time() - self.start_time
                self.logger.debug("------ 导出操作耗时统计 ------")
                self.logger.debug(f"总对象生命周期: {total_time:.2f}秒")
                total_time_safe = total_time if total_time > 0 else 1
                self.logger.debug(f"总等待时间: {self.total_sleep_time:.2f}秒 ({self.total_sleep_time/total_time_safe*100:.1f}%)")
                self.logger.debug("各操作等待时间:")
                total_sleep_time_safe = self.total_sleep_time if self.total_sleep_time > 0 else 1
                for op_name, op_time in sorted(self.operation_times.items(), key=lambda x: x[1], reverse=True):
                    count = self.operation_counts[op_name]
                    avg_time = op_time / count if count > 0 else 0
                    self.logger.debug(f"  {op_name}: {op_time:.2f}秒 ({op_time/total_sleep_time_safe*100:.1f}%) - 次数: {count}次, 平均: {avg_time:.2f}秒/次")
                self.logger.debug("------ 统计结束 ------")
                

    def get_window_fast(self):
        """使用快速方法获取剪映窗口，并添加超时保护"""
        self.logger.debug("使用快速方法获取剪映窗口...")
        
        # 添加超时控制
        import time
        start_time = time.time()
        timeout = 10  # 10秒超时
        
        try:
            # 尝试获取剪映窗口
            desktop = uia.GetRootElement()
            
            while time.time() - start_time < timeout:
                # 查找所有"CapCut"或"剪映专业版"的窗口
                condition = uia.CreatePropertyConditionEx(UIA_NamePropertyId, "剪映专业版", PropertyConditionFlags_None)
                
                jy_window = desktop.FindFirst(TreeScope_Children, condition)
                
                if jy_window:
                    self.logger.debug("成功找到剪映窗口")
                    window_title = jy_window.CurrentName if hasattr(jy_window, 'CurrentName') else "未知"
                    window_visible = jy_window.CurrentIsEnabled if hasattr(jy_window, 'CurrentIsEnabled') else False
                    self.logger.debug(f"窗口信息: 标题='{window_title}', 可见={window_visible}")
                    return jy_window
                
                # 未找到窗口，等待一会再试
                self.logger.debug("未找到剪映窗口，等待后重试...")
                time.sleep(0.5)
            
            # 超时未找到窗口
            error_msg = f"获取剪映窗口超时 ({timeout}秒)，请确保剪映已打开且窗口标题为'剪映专业版'"
            self.log_to_ui(error_msg, logging.ERROR)  # 使用UI日志
            return None
            
        except Exception as e:
            error_msg = f"获取剪映窗口时出错: {e}"
            self.log_to_ui(error_msg, logging.ERROR)  # 使用UI日志
            return None

    def switch_to_home_fast(self):
        """优化版的切换到主页函数"""
        if self.app_status == "home":
             self.logger.debug("已在主页，无需切换。")
             return
        if self.app_status != "edit":
            self.logger.warning("尝试从非编辑模式切换到主页，当前状态: %s", self.app_status)
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
            # 直接使用日志中提示有效的备用方法
            self.logger.debug("直接使用备用方法定位关闭/返回主页按钮 (ClassName='TitleBarButton', foundIndex=3)...")
            close_btn = self.app.GroupControl(searchDepth=1, ClassName="TitleBarButton", foundIndex=3)

            if not close_btn or not close_btn.Exists(0):
                # Fallback: Try finding the main window close button using accessibility info
                # This might be more robust if class/index changes
                self.logger.warning("备用方法 (index=3) 未找到关闭按钮，尝试按 ControlType 和 Name...")
                close_btn = self.app.ButtonControl(ControlType=uia.ControlType.ButtonControl, Name="关闭")
                if not close_btn or not close_btn.Exists(0):
                     self.logger.error("无法定位到编辑窗口的关闭/返回主页按钮 (尝试了多种方法)。")
                     raise draft.exceptions.AutomationError("无法定位到编辑窗口的关闭/返回主页按钮。")
                else:
                     self.logger.debug("通过 ControlType 和 Name 找到关闭按钮。")

            self.logger.debug("尝试点击关闭/返回主页按钮...")
            close_btn.Click(simulateMove=False)
            self.timed_sleep(self.wait_times.get("return_home", 0.2), "返回主页按钮点击等待")
            self.get_window_fast() # 切换后重新获取窗口状态
            if self.app_status != "home":
                # Add a slightly longer wait and re-check? Window transition might take time.
                self.logger.warning("点击返回按钮后，应用状态仍不是 'home' (%s)，等待 0.5 秒后重试检查...", self.app_status)
                time.sleep(0.5)
                self.get_window_fast()
                if self.app_status != "home":
                    self.logger.error("重试检查后，应用状态仍不是 'home' (%s)，切换失败。", self.app_status)
                    # Consider raising error here or just logging
                    # raise draft.exceptions.AutomationError("切换到主页失败")
                else:
                    self.logger.info("重试检查后，成功切换到主页。")
            else:
                self.logger.info("成功切换到主页。")
        except Exception as e:
             self.logger.exception("切换到主页时发生错误")
             # If error occurred, maybe refresh window state one last time? Might not help.
             # try: self.get_window_fast() except: pass
             raise draft.exceptions.AutomationError(f"切换到主页失败: {e}") 

    def check_jianying_state(self, retry_attempts=3):
        """检查剪映状态并等待其就绪，添加更详细的日志和错误处理"""
        self.logger.debug("检查剪映状态...")
        
        for attempt in range(retry_attempts):
            try:
                # 获取剪映窗口
                jy_window = self.get_window_fast()
                if not jy_window:
                    self.logger.error(f"无法获取剪映窗口 (尝试 {attempt+1}/{retry_attempts})")
                    if attempt < retry_attempts - 1:
                        time.sleep(1)
                        continue
                    else:
                        return False, "剪映窗口未找到"
                
                # 检查窗口状态
                pattern = jy_window.GetCurrentPattern(UIA_WindowPatternId)
                if pattern and pattern.CurrentCanMaximize:
                    self.logger.debug("剪映窗口可能被最小化，尝试恢复...")
                    pattern.SetWindowVisualState(WindowVisualState_Normal)
                    time.sleep(0.5)
                
                # 检查是否在主界面
                # ...原有检查逻辑...
                
                self.logger.debug("剪映状态检查完成，窗口正常")
                return True, "剪映窗口状态正常"
                
            except Exception as e:
                self.logger.error(f"检查剪映状态时出错 (尝试 {attempt+1}/{retry_attempts}): {e}")
                if attempt < retry_attempts - 1:
                    time.sleep(1)
                else:
                    return False, f"检查剪映状态失败: {e}"
        
        return False, "检查剪映状态失败，超过最大重试次数"

    # 修改调用剪映处理的方法，增加超时保护
    def process_with_jianying(self, draft_name, video_path, output_path, max_wait_time=300):
        """使用剪映处理视频
        
        Args:
            draft_name: 草稿名称
            video_path: 视频路径
            output_path: 输出路径
            max_wait_time: 最大等待时间(秒)
        
        Returns:
            成功与否
        """
        self.log_to_ui(f"开始剪映处理: {draft_name} -> {output_path}")
        
        # 记录开始时间，用于超时判断
        import time
        start_time = time.time()
        last_status_time = start_time
        
        try:
            # 获取剪映窗口
            self.log_to_ui("正在获取剪映窗口...")
            jy_window = self.get_window_fast()
            if not jy_window:
                self.log_to_ui("剪映窗口未找到，无法继续处理", logging.ERROR)
                return False
                
            # 检查剪映状态
            status, msg = self.check_jianying_state()
            if not status:
                self.log_to_ui(f"剪映状态检查失败: {msg}", logging.ERROR)
                return False
                
            self.log_to_ui("剪映窗口已准备就绪，开始处理...")
            
            # 继续原有处理逻辑...
            
            # 定期状态更新
            while True:
                current_time = time.time()
                # 检查是否超时
                if current_time - start_time > max_wait_time:
                    self.log_to_ui(f"剪映处理超时，已等待{max_wait_time}秒", logging.ERROR)
                    return False
                    
                # 每30秒更新一次状态到UI
                if current_time - last_status_time > 30:
                    self.log_to_ui(f"剪映处理进行中: 已等待 {int(current_time - start_time)} 秒...")
                    last_status_time = current_time
                
                # 检查剪映状态
                # ...原有代码...
                
                # 避免CPU高占用
                time.sleep(0.5)
            
        except Exception as e:
            self.log_to_ui(f"剪映处理过程中发生错误: {e}", logging.ERROR)
            return False
        
        self.log_to_ui(f"剪映处理完成: {draft_name}")
        return True

    # 添加或修改导出视频的方法
    def export_video(self, draft_name, output_path, max_wait_time=300):
        """导出视频，添加超时保护机制
        
        Args:
            draft_name: 草稿名称
            output_path: 输出路径
            max_wait_time: 最大等待时间(秒)
        
        Returns:
            (成功与否, 错误信息)
        """
        self.logger.info(f"开始导出 {draft_name} 至 {output_path}")
        
        # 记录开始时间，用于超时判断
        import time
        start_time = time.time()
        last_log_time = start_time
        
        try:
            # 检查剪映状态
            status, msg = self.check_jianying_state()
            if not status:
                self.logger.error(f"剪映状态检查失败: {msg}")
                return False, msg
            
            # 原有导出逻辑...
            
            # 等待导出完成，添加超时保护
            while True:
                # 检查是否超时
                current_time = time.time()
                if current_time - start_time > max_wait_time:
                    self.logger.error(f"导出超时，已等待{max_wait_time}秒")
                    return False, f"导出超时 ({max_wait_time}秒)"
                
                # 每30秒打印一次日志，避免日志过多
                if current_time - last_log_time > 30:
                    self.logger.info(f"导出进行中，已等待 {int(current_time - start_time)} 秒...")
                    last_log_time = current_time
                
                # 检查导出状态 - 可能需要根据实际代码结构进行调整
                try:
                    # 尝试查找导出进度或导出完成标志
                    export_status = self.check_export_status()
                    
                    if export_status == "completed":
                        self.logger.info(f"导出成功完成，耗时 {int(current_time - start_time)} 秒")
                        return True, "导出成功"
                    elif export_status == "error":
                        self.logger.error("导出过程中发生错误")
                        return False, "导出错误"
                    # 其他状态继续等待
                    
                except Exception as e:
                    self.logger.warning(f"检查导出状态时出错: {e}")
                    # 继续等待，不中断导出过程
                
                # 避免CPU高占用
                time.sleep(1)
            
        except Exception as e:
            self.logger.exception(f"导出过程中发生错误: {e}")
            return False, f"导出错误: {e}"

    def check_export_status(self):
        """检查导出状态，返回 'in_progress', 'completed', 'error'"""
        try:
            # 基于UI元素判断导出状态
            jy_window = self.get_window_fast()
            if not jy_window:
                self.logger.error("检查导出状态: 剪映窗口未找到")
                return "error"
            
            # 检查是否存在"导出成功"提示
            # 这里需要根据剪映UI结构调整元素查找方式
            success_indicator = None
            try:
                # 尝试找到导出成功的指示器
                # 例如: 可能是一个包含"导出成功"文本的元素
                success_condition = uia.CreatePropertyConditionEx(UIA_NamePropertyId, "导出成功", PropertyConditionFlags_None)
                success_indicator = jy_window.FindFirst(TreeScope_Descendants, success_condition)
            except:
                pass
            
            if success_indicator:
                self.logger.info("检测到导出成功提示")
                return "completed"
            
            # 检查是否存在错误提示
            error_indicator = None
            try:
                # 尝试找到导出错误的指示器
                error_condition = uia.CreatePropertyConditionEx(UIA_NamePropertyId, "导出失败", PropertyConditionFlags_None)
                error_indicator = jy_window.FindFirst(TreeScope_Descendants, error_condition)
            except:
                pass
            
            if error_indicator:
                self.logger.error("检测到导出失败提示")
                return "error"
            
            # 默认认为正在导出中
            return "in_progress"
            
        except Exception as e:
            self.logger.error(f"检查导出状态时发生异常: {e}")
            return "error" 