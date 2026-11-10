# JAKA Paint

JAKA Paint 将线稿转换为 JAKA ZU Script TXT 点位程序，并生成点位、轨迹和诊断预览。

```text
内置线稿样例 -> 参数设置 -> 轨迹提取 -> TXT 点位程序 -> 点位/轨迹预览
```

## 当前功能

已提供：

- 内置线稿样例、核心转换算法和 TXT 预览；
- 参数设置窗口，包含转换、位置、运动和图像服务配置，以及参数校验；
- 图像服务客户端 `core/image_client.py` 和完整原版生图、眼睛与嘴部处理提示词 `core/image_prompts.py`；客户端供后续界面调用，软件启动时不发送图像请求；
- 开发助手提示词、项目开发约束和离线测试。

尚待开发：

1. 本地图片选择、格式检查和预览，将选中的线稿接入 TXT 转换；
2. 使用已提供的图像客户端，将照片生成线稿的按钮、后台任务、预览、失败处理及确认后转 TXT 串联起来；
3. 控制器 IP 连接与状态查询；
4. TXT 发送、人工确认、启动、停止及运行状态。

**导入线稿与照片生成线稿是两个功能。** 本地导入不会自动把照片变成适合绘图的线条；照片生成线稿需要用户主动调用图像服务。现有参数设置无需重新开发。

## 运行

建议在 Windows 上使用 Python 3.12 64 位，并保留 Python 安装器默认的 Tcl/Tk 组件。在包含本文件的项目目录打开 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe jaka_paint_app.py
```

显式使用虚拟环境内的 Python，无需激活环境或修改 PowerShell 执行策略。再次运行只需最后一条命令，也可双击优先使用项目 `.venv` 的 `run_jaka_paint.cmd`。

**运行内置样例、设置转换参数和生成 TXT 不需要图像 API Key，也不需要调用图像服务。** 安装依赖通常需要网络。

点击“生成 TXT 点位”后，源码运行模式下结果保存在项目的 `output/`：

- `lineart_sample_jaka.txt`：JAKA ZU Script 点位程序；
- `preview/lineart_sample_jaka_points.png`：点位分布；
- `preview/lineart_sample_jaka_trajectory.png`：连线轨迹；
- `preview/lineart_sample_jaka_diagnostic.png`：诊断预览。

## 参数与图像服务

参数设置窗口已提供转换、位置、运动和图像服务配置。转换参数经 `core/parameters.py` 校验后应用，生成 TXT 时使用当前配置。应用参数只对本次运行生效，关闭后重新打开会恢复默认值。现有设备参数继承自示例配置，**不等于现场标定值**；Tool ID、User Frame ID、位置、姿态、画笔高度、速度及工作范围须由设备负责人确认。

图像服务的 API Key 仅保存在当前进程内存中，也可由当前进程的 `XIANJIJI_API_KEY` 环境变量提供。密钥不随 ZIP 提供，不应写入源码、配置文件、日志或提交记录。项目不承诺自动读取 `.env`；仅新建 `.env` 不代表密钥已生效。当前提供 `medium`、`high` 两档图像质量，默认 `high`。

预置客户端接口：

```python
from core.image_client import generate_lineart

# 后续界面集成时显式调用；本段不是应用启动流程。
png_bytes = generate_lineart(source, api_key=api_key, quality="high", timeout=240)
```

`source` 的支持类型及错误说明见 [图像服务接口说明](docs/IMAGE_SERVICE.md)。`api_key=None` 时客户端读取 `XIANJIJI_API_KEY`。界面集成应先在主线程调用 `app.get_image_generation_options()` 获取当前 `api_key`、`quality`，再将选项传入后台任务；缺少密钥时该方法抛出 `ValueError`，应在开始请求前向用户说明。

客户端预置已观察到的原版协议，本版本未完成真实联网验证。离线测试通过不能证明服务端可用、额度充足或账号具有相应权限。使用时保留完整原版提示词，不让 AI 猜测协议或自行缩写提示词。

## 开发助手

`AI_DEVELOPMENT_PROMPT.md` 提供分阶段开发提示词。支持项目 `AGENTS.md` 约定的 AI 工具可读取开发约束；其他工具可通过软件的“开发助手”复制通用提示词，再追加一个明确的当前任务。直接打开提示词文件时，只复制第一个通用提示词代码块，后面的任务模板不代表本次任务。

阶段安排为：基线检查 → 本地图片输入 → 使用预置客户端实现照片生成线稿 → 控制器连接 → TXT 发送与绘图状态。一次只开发当前明确指定的功能，完成验收后再安排下一项。提示词不能保证 AI 自动遵守，也不能替代实际测试和现场确认。

命令行核心转换也可以直接调用：

```powershell
.\.venv\Scripts\python.exe core/lineart_to_points.py samples/lineart_sample.png --output output/from_cli.txt
```

## 目录说明

- `jaka_paint_app.py`：主界面、参数设置和当前样例流程；
- `core/parameters.py`：默认转换参数与校验；
- `core/lineart_to_points.py`：线稿骨架、路径和 JAKA TXT 生成算法；
- `core/jaka_txt_to_pointmap.py`：TXT 点位、轨迹和诊断图预览；
- `core/image_client.py`：独立图像服务客户端，无界面；
- `core/image_prompts.py`：完整原版图像处理提示词；
- `docs/IMAGE_SERVICE.md`：图像服务接口、配置和验证边界；
- `samples/lineart_sample.png`：内置线稿样例；
- `tests/`：离线回归与接口模拟测试；
- `build_exe.cmd`、`requirements-build.txt` 和 `.spec`：可重复构建 Windows 发布文件的脚本与配置。

## Windows 发布文件构建

保留源码和 `.venv` 用于继续开发；修改源码后需重新构建发布版本。项目提供打包配置，可在 Windows 上运行：

```powershell
.\build_exe.cmd
```

脚本和配置不代表已经生成或验证了可发布的 EXE。构建后要检查样例、参数设置、提示词读取和输出文件，并在未安装 Python 的 Windows 电脑上另行验证。使用文件夹发布方式时应复制或压缩整个发布文件夹，不能仅取出 EXE。打包运行时输出保存在 EXE 所在目录的 `output/`；将发布文件夹放在当前用户有写入权限的位置。

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
