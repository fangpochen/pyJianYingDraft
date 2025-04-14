# 剪映批量处理工具 - 处理流程说明

## 1. 应用程序概述

该应用程序是一个剪映批量处理工具，用于自动化处理视频文件并生成剪映草稿。核心功能包括：

- 扫描子文件夹中的视频文件
- 将视频分割成多个片段
- 替换剪映模板中的视频片段
- 调整BGM和主轨道音量
- 导出处理后的视频

## 2. 文件结构

应用程序的主要组件分布在以下目录：

```
app/
  ├── ui/              # 用户界面相关代码
  │   └── main_window.py  # 主窗口UI实现
  ├── core/            # 核心处理逻辑
  │   ├── orchestrator.py # 业务协调层
  │   ├── processor.py    # 视频文件处理
  │   └── draft_exporter.py # 草稿导出功能
  ├── util/            # 工具函数
  │   ├── jianying.py     # 剪映草稿处理
  │   ├── jianying_export.py # 剪映导出功能
  │   └── logging_setup.py  # 日志配置
  ├── config.py        # 配置管理
  └── main.py          # 应用程序入口
```

## 3. 处理流程

### 3.1 总体流程图

```
+---------------------------+
|                           |
|     用户界面层            |
|     app/ui/main_window.py |
|                           |
+------------+--------------+
             |
             | 用户在UI设置参数:
             | - 输入/输出文件夹
             | - 草稿名称
             | - 分割段数
             | - BGM音量
             | - 主轨道音量
             | - 保留BGM开关
             | - 删除源文件开关
             |
             v
+---------------------------+
|                           |
|     后台任务处理          |
|     ProcessingWorker类    |
|     app/ui/main_window.py |
|                           |
+------------+--------------+
             |
             | 在后台线程中启动处理
             | 传递所有UI参数
             |
             v
+---------------------------+
|                           |
|     业务编排层            |
|     app/core/orchestrator.py|
|                           |
| run_individual_video_     |
| processing()函数          |
|                           |
+--------+--------+---------+
         |        |
         |        |
         |        |
         v        +-------------------------+
+---------------------------+                |
|                           |                |
|     视频处理层 - 第一步   |                |
|     app/core/processor.py |                |
|                           |                |
| 1. find_video_tasks():    |                |
|    扫描文件夹查找视频文件 |                |
|                           |                |
| 2. split_video_ffmpeg():  |                |
|    调整视频主轨道音量     |                |
|    分割视频               |                |
|                           |                |
+------------+--------------+                |
             |                               |
             | 返回分割后的视频路径          |
             |                               |
             v                               v
+---------------------------+    +------------------------+
|                           |    |                        |
|     剪映草稿处理层 - 第二步|    | 视频成功处理后:        |
|     app/util/jianying.py  |    | 1. 删除切割片段        |
|                           |    | 2. 删除源视频(可选)    |
| 1. process_videos():      |    |                        |
|    - 加载剪映模板         |    +------------------------+
|    - 替换视频片段         |             |
|    - 设置主轨道音量       |             |
|    - 处理BGM轨道          |             |
|    - 设置BGM音量          |             |
|    - 保存草稿             |             |
|    - 导出视频             |             |
|                           |             |
+------------+--------------+             |
             |                            |
             | 调用导出功能                |
             |                            |
             v                            |
+---------------------------+             |
|                           |             |
|     剪映导出层 - 第三步   |             |
|     app/util/jianying_export.py        |
|                           |             |
| 1. Fast_Jianying_Controller:           |
|    export_draft()         |             |
|    - 获取剪映窗口         |             |
|    - 进入草稿编辑界面     |             |
|    - 点击导出按钮         |             |
|    - 设置分辨率和帧率     |             |
|    - 等待导出完成         |             |
|    - 移动导出文件到目标位置|             |
|                           |             |
+---------------------------+             |
                                          |
                                          |
                                          v
                            +---------------------------+
                            |                           |
                            |      最终处理结果         |
                            | 1. 输出文件夹中的导出视频 |
                            | 2. 更新后的剪映草稿       |
                            |                           |
                            +---------------------------+
```

### 3.2 各组件详细职责

#### 3.2.1 UI界面层 (app/ui/main_window.py)

- **MainWindow类**:
  - 提供用户界面，包括输入字段、滑块和按钮
  - 负责参数收集和验证
  - 创建后台处理线程
  - 显示处理进度和结果
  - 配置加载和保存
  
- **关键参数**:
  - `bgm_volume_slider`: 设置BGM音量(0-100%)
  - `main_volume_slider`: 设置主轨道音量(0-100%)
  - `keep_bgm_check`: 是否保留模板中的BGM
  - `num_segments_entry`: 分割视频段数

- **ProcessingWorker类**:
  - 在后台线程中执行处理任务
  - 通过信号机制向UI报告进度和结果

#### 3.2.2 业务编排层 (app/core/orchestrator.py)

- **run_individual_video_processing函数**:
  - 协调整个处理流程
  - 接收UI参数并传递给底层函数
  - 处理错误和异常
  - 返回处理结果摘要

- **执行流程**:
  1. 查找需要处理的视频任务
  2. 对每个任务，分割视频并调整音量
  3. 调用jianying.py处理剪映草稿
  4. 处理成功后清理临时文件

#### 3.2.3 视频处理层 (app/core/processor.py)

- **主要函数**:
  - `find_video_tasks()`: 扫描输入文件夹查找视频文件
  - `split_video_ffmpeg()`: 分割视频并设置主轨道音量
  - `get_video_duration()`: 获取视频时长

- **处理流程**:
  1. 查找输入文件夹中的视频文件
  2. 根据设置分割视频，同时应用主轨道音量设置
     - 使用ffmpeg命令执行分割
     - 应用`volume`滤镜调整音量
  3. 返回分割后的视频路径列表

#### 3.2.4 剪映草稿处理层 (app/util/jianying.py)

- **process_videos函数**:
  - 核心函数，处理剪映草稿文件
  - 接收分割后的视频路径和所有相关参数

- **处理流程**:
  1. 加载指定的剪映模板草稿
  2. 替换模板中的视频片段
  3. 设置主轨道音量(main_track_volume)
  4. 处理BGM轨道:
     - 如果keep_bgm=True，保留BGM轨道
     - 调整BGM时长匹配视频
     - 设置BGM音量(bgm_volume)
     - 处理BGM循环播放(如需要)
  5. 保存修改后的草稿
  6. 调用jianying_export.py中的导出功能

#### 3.2.5 剪映导出层 (app/util/jianying_export.py)

- **Fast_Jianying_Controller类**:
  - 处理剪映UI自动化导出操作
  - 通过uiautomation库控制剪映界面

- **export_draft函数**:
  - 实现剪映草稿自动化导出
  - 接收草稿名称、输出路径、分辨率和帧率参数

- **导出流程**:
  1. 获取剪映窗口并切换到主页
  2. 点击目标草稿进入编辑界面
  3. 点击导出按钮打开导出设置界面
  4. 获取默认导出路径
  5. 设置分辨率和帧率(如需要)
  6. 点击最终导出按钮开始导出
  7. 等待导出完成(监控进度)
  8. 导出完成后回到主页
  9. 将导出文件移动到指定路径
  
- **错误处理**:
  - 处理UI控件查找失败、超时等异常
  - 提供详细的操作日志记录
  - 实现在出错时自动清理和退出

## 4. 参数传递和处理

### 4.1 BGM音量处理

1. UI界面中用户通过滑块设置BGM音量(0-100%)
2. `bgm_volume`参数从UI传递到ProcessingWorker
3. ProcessingWorker将参数传递给orchestrator.py
4. orchestrator.py将参数传递给jianying.py的process_videos函数
5. process_videos函数处理BGM:
   ```python
   # 确保bgm_volume在合法范围内
   normalized_volume = max(0, min(100, bgm_volume)) / 100.0  # 转换为0.0-1.0的浮点数
   
   # 创建BGM片段时设置音量
   first_bgm_track.segments.append(
       draft.Imported_media_segment({
           # ...其他参数...
           "volume": normalized_volume,  # 应用用户设置的音量
           # ...其他参数...
       })
   )
   ```

### 4.2 主轨道音量处理

1. UI界面中用户通过滑块设置主轨道音量(0-100%)
2. `main_track_volume`参数从UI传递到ProcessingWorker
3. ProcessingWorker将参数传递给orchestrator.py
4. orchestrator.py将参数传递给:
   - processor.py的split_video_ffmpeg函数(分割视频时调整音量)
   - jianying.py的process_videos函数(设置剪映片段音量)
5. 音量调整实现方式:
   - processor.py中通过ffmpeg的volume滤镜调整
   - jianying.py中通过设置视频片段的volume属性

### 4.3 导出过程参数传递

1. 在jianying.py中，process_videos函数确定是否需要导出：
   ```python
   if export_video:
       export_success = ctrl.export_draft(
           draft_name=draft_name,
           output_path=export_file_path, 
           resolution=Export_resolution.RES_1080P if CUSTOMIZE_EXPORT else None,
           framerate=Export_framerate.FR_30 if CUSTOMIZE_EXPORT else None
       )
   ```

2. jianying_export.py的Fast_Jianying_Controller处理UI自动化导出
3. 导出成功后，视频文件被保存到指定路径

## 5. 注意事项

1. **线程安全**：应用程序使用QThread实现多线程，而非多进程
2. **参数归一化**：音量参数在UI中为0-100%，在底层处理函数中转换为0.0-1.0
3. **错误处理**：各层级函数都实现了异常捕获和错误处理
4. **资源清理**：处理完成后会清理临时文件，成功时可选择删除源文件
5. **UI自动化**：导出过程依赖于UI自动化技术，需要剪映软件已打开且处于可操作状态

## 6. 可能的改进

1. **并行处理**：目前是单线程顺序处理每个视频，可考虑实现多进程并行处理
2. **进度监控**：增强进度报告功能，提供更详细的处理进度
3. **断点续传**：允许中断后继续处理剩余任务
4. **界面优化**：提供更多视觉反馈和自定义选项
5. **UI自动化稳定性**：加强jianying_export.py中的UI自动化处理，提高在不同系统环境下的稳定性 