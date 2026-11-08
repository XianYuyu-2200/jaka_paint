# JAKA Paint 教学半成品

这是 JAKA 机械臂线稿绘图项目的教学起点。当前版本只保留已经完成的核心能力：

```text
固定线稿样例 -> 骨架/轨迹提取 -> JAKA ZU Script TXT 点位文件 -> 点位/轨迹预览
```

软件暂时**没有**图片选择、参数设置、控制器 IP 连接、程序发送或启动绘图功能。这些模块故意留给培训学员使用 Vibe Coding 完成。

## 运行

需要 Python 3.10+，安装依赖后运行：

```powershell
python -m pip install -r requirements.txt
python half_finished_app.py
```

也可以双击 `run_half_finished.cmd`。点击“生成 TXT 点位”后，结果保存在 `output/`：

- `lineart_sample_jaka.txt`：JAKA ZU Script 点位程序；
- `preview/points.png`：点位分布；
- `preview/trajectory.png`：连线轨迹；
- `preview/diagnostic.png`：诊断预览。

命令行核心转换也可以直接调用：

```powershell
python core/lineart_to_points.py samples/lineart_sample.png --output output/from_cli.txt
```

## 目录说明

- `half_finished_app.py`：教学界面，只调用核心转换，不包含控制器通信；
- `core/lineart_to_points.py`：线稿骨架、路径和 JAKA TXT 生成算法；
- `core/jaka_txt_to_pointmap.py`：TXT 点位、轨迹和诊断图预览；
- `samples/lineart_sample.png`：固定教学样例；
- `tests/`：核心离线回归测试。

## 培训待开发任务

建议按小任务逐个完成，并在每次修改后运行样例确认结果：

1. 在 `half_finished_app.py` 中增加图片文件选择和图片预览，把选中的线稿传给 `convert_to_jaka`；
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

`lineart_to_points.py` 的算法属于现有核心功能，培训时先把它当作稳定接口使用。新增 UI 和设备模块时，避免直接改动核心算法。
