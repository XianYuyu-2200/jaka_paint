# 线稿生成接口

`core/image_client.py` 预置了原版照片转线稿的同步接口。导入模块和启动软件不会发送请求。图片选择、生成按钮、后台任务、等待/失败提示、结果保存及预览由应用功能开发接入。

## 已提供的调用

```python
from pathlib import Path
from core.image_client import ImageServiceError, generate_lineart

# 放在应用的后台任务中执行，不要阻塞 Tkinter 主线程。
# None 表示从 XIANJIJI_API_KEY 环境变量读取；也可传入本次界面填写的值。
png_bytes = generate_lineart(
    source=Path("photo.jpg"),
    api_key=None,
    quality="high",
    timeout=240,
)
# 调用成功后，由应用将 PNG 字节保存为新的文件，再在主线程更新预览。
```

`generate_lineart(source, *, api_key=None, quality="high", timeout=240) -> bytes` 使用原版 `DEFAULT_PROMPT`，返回校验并规范化后的 PNG 字节，不自动保存文件。输入支持 PNG、JPG/JPEG、BMP，上传时统一转为 PNG；透明区域使用白底。

`generate_image()` 使用相同参数，另外接受 `prompt=`。`core/image_prompts.py` 保存原版三套提示词：`DEFAULT_PROMPT`、`EYE_CORRECTION_PROMPT`、`MOUTH_CORRECTION_PROMPT`。修正接口同样是一次额外的服务调用；本模块不自动执行眼睛或嘴部修正，也不自动重试。

## 服务配置

| 项目 | 预置值 |
|---|---|
| 服务地址 | `https://api.xianjiji.top/v1/images/edits` |
| 模型标识 | `gpt-image-2.5-flare` |
| 尺寸 | `1024x1024` |
| 质量 | `medium` / `high`，默认 `high` |
| 协议 | multipart 图片编辑请求，`response_format=b64_json` |
| 密钥来源 | 本次传入的 API Key，或 `XIANJIJI_API_KEY` 环境变量 |

以上值来自留存原版源码，不代表已验证服务当前可用、账户已开通该模型或费用不变。项目不附带真实密钥；真实调用需要联网、有效账户及额度，并会将所选图片发送到该第三方服务。不要把密钥粘贴到 AI 对话、源码、日志或仓库。界面中密钥仅在本次会话使用，不默认写入配置。

显式传入空字符串会报缺少密钥，不自动改用环境变量；若希望使用环境变量，应传 `None`。请求只发送一次，超时或失败时应由用户决定是否重试。

## 集成约定

主界面已提供 `self.get_image_generation_options()`，应先在主线程读取，获得包含 `api_key` 和 `quality` 的字典，再传入后台任务。启动时界面会读取环境变量中的密钥；该方法在当前密钥为空时抛出 `ValueError`，调用方应捕获并在请求前提示补充。不要在工作线程读取 Tkinter 变量。`self.lineart_path` 表示当前用于 TXT 转换的线稿文件，`self.conversion_parameters` 表示已有的转换参数，两者与生图参数分开管理。

1. 用后台任务调用接口，通过 Tkinter 的主线程机制更新控件。
2. 仅在用户明确点击生成时调用；开始请求前显示忙碌状态，避免重复提交。
3. 成功时保存新 PNG 并展示预览，由用户确认采用后，再设置当前线稿路径，供现有 `convert_to_jaka()` 使用。
4. 失败时捕获 `ImageServiceError` 并显示提示，保留原图、已有线稿及 TXT；不能把失败或未知显示为成功。
5. 配置的生成质量和 API Key 属于生图调用参数，不能传给 `convert_to_jaka()`。
6. 不以本地阈值处理替代用户要求的模型生图；离线模拟结果必须明确标明。

客户端只接受约定的 Base64 图片响应（包含 `data:image/...;base64,` 形式），拒绝 URL-only 响应及 HTTP 重定向，不把认证头发送到其他地址。错误消息不包含服务端原文、密钥或图像 Base64。

## 验证

```powershell
python -m unittest discover -s tests -p test_image_client.py -v
```

测试使用模拟网络，覆盖协议字段、原版提示词、输入图片转换、响应解析及错误处理，不产生收费请求。真实账户调用、实际线稿质量和网络可用性需要另行验证。
