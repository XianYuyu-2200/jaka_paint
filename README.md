# JAKA Paint

这是 JAKA 机械臂线稿绘图软件的基础版本。当前版本提供核心能力：

```text
固定线稿样例 -> 骨架/轨迹提取 -> JAKA ZU Script TXT 点位文件 -> 点位/轨迹预览
```

当前版本暂未提供图片选择、参数设置、控制器 IP 连接、程序发送或启动绘图功能。

## 运行

需要 Python 3.10+，安装依赖后运行：

```powershell
python -m pip install -r requirements.txt
python jaka_paint_app.py
```

也可以双击 `run_jaka_paint.cmd`。点击“生成 TXT 点位”后，结果保存在 `output/`：

- `lineart_sample_jaka.txt`：JAKA ZU Script 点位程序；
- `preview/points.png`：点位分布；
- `preview/trajectory.png`：连线轨迹；
- `preview/diagnostic.png`：诊断预览。

## 开发助手提示词

仓库内的 `AI_DEVELOPMENT_PROMPT.md` 是配套的开发助手提示词。支持读取 `AGENTS.md` 的 Vibe Coding 工具在打开本项目后会先加载项目开发约束；其他工具可在软件中点击“开发助手”复制提示词，粘贴到 AI 对话后追加课堂指定的一个当前任务。直接使用提示词文件时，只复制通用提示词代码块；任务模板仅供参考。提示词要求 AI 分阶段修改、保留线稿转 TXT 核心，并在控制器功能阶段先使用模拟环境。提示词提供约束和验收流程，不能替代测试或现场安全确认。

命令行核心转换也可以直接调用：

```powershell
python core/lineart_to_points.py samples/lineart_sample.png --output output/from_cli.txt
```

## 目录说明

- `jaka_paint_app.py`：主界面，只调用核心转换，不包含控制器通信；
- `core/lineart_to_points.py`：线稿骨架、路径和 JAKA TXT 生成算法；
- `core/jaka_txt_to_pointmap.py`：TXT 点位、轨迹和诊断图预览；
- `samples/lineart_sample.png`：内置线稿样例；
- `tests/`：核心离线回归测试。

## 后续功能

后续版本可逐步加入以下功能：

1. 在 `jaka_paint_app.py` 中增加图片文件选择和图片预览，把选中的线稿传给 `convert_to_jaka`；
2. 增加参数设置区域，让用户修改画布尺寸、点间距、阈值、原点、镜像和 JAKA 位姿等参数；
3. 增加控制器 IP 输入、连接状态和错误提示；
4. 增加 TXT 发送、人工确认、启动和停止流程。该模块必须先使用模拟控制器测试，再由设备负责人进行真机验证。

不要把 API Key、控制器密码或未经确认的现场坐标提交到仓库。仅生成 TXT 或连接成功不能证明机械臂可以安全运行；Tool ID、User Frame ID、画笔高度和工作范围必须按现场设备确认。

## 核心算法调用

```python
from core.lineart_to_points import convert_to_jaka

output, path_count, point_count, scale = convert_to_jaka(
    "samples/lineart_sample.png",
    "output/example_jaka.txt",
    width_mm=152.4,
    height_mm=152.4,
    spacing_mm=1.0,
    threshold=180,
)
```

`lineart_to_points.py` 提供核心转换接口。新增 UI 和设备模块时，建议避免直接改动核心算法。
