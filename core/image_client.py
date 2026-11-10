"""Explicit, synchronous image-service calls; importing this module never uses the network.

The application supplies its own background task, state management and file saving.
No API key is persisted or logged here. Calls are not retried automatically.
"""
from __future__ import annotations

import base64
import binascii
from http.client import HTTPException
from io import BytesIO
import json
import math
import os
from pathlib import Path
import socket
import urllib.error
import urllib.request
import uuid

from PIL import Image, ImageOps, UnidentifiedImageError

from .image_prompts import DEFAULT_PROMPT


API_URL = "https://api.xianjiji.top/v1/images/edits"
MODEL = "gpt-image-2.5-flare"
IMAGE_SIZE = "1024x1024"
SUPPORTED_QUALITIES = ("medium", "high")
API_KEY_ENV = "XIANJIJI_API_KEY"
MAX_RESPONSE_BYTES = 32 * 1024 * 1024


class ImageServiceError(RuntimeError):
    """A user-facing failure that omits credentials and raw service responses."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # urllib can otherwise forward an Authorization header to a new host.
        return None


def _normalize_png(raw: bytes, *, source: bool) -> bytes:
    try:
        with Image.open(BytesIO(raw)) as image:
            if source and image.format not in {"PNG", "JPEG", "BMP"}:
                raise ImageServiceError("仅支持 PNG、JPG/JPEG、BMP 图片。")
            image.load()
            oriented = ImageOps.exif_transpose(image).convert("RGBA")
            background = Image.new("RGBA", oriented.size, "white")
            background.alpha_composite(oriented)
            output = BytesIO()
            background.convert("RGB").save(output, format="PNG")
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        if source:
            raise ImageServiceError("无法读取图片，请选择有效的 PNG、JPG/JPEG 或 BMP 文件。") from None
        raise ImageServiceError("图像服务返回的内容不是可读取的图片。") from None


def _multipart(fields: dict[str, str], image: bytes) -> tuple[bytes, str]:
    boundary = "----JakaPaint" + uuid.uuid4().hex
    parts: list[bytes] = []
    for key, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode("utf-8")
        )
    parts.extend([
        f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="source.png"\r\nContent-Type: image/png\r\n\r\n'.encode("ascii"),
        image,
        f"\r\n--{boundary}--\r\n".encode("ascii"),
    ])
    return b"".join(parts), boundary


def _decode_response(raw: bytes) -> bytes:
    try:
        payload = json.loads(raw.decode("utf-8"))
        items = payload.get("data") if isinstance(payload, dict) else None
        item = items[0] if isinstance(items, list) and items else None
        value = item.get("b64_json") if isinstance(item, dict) else None
        if not isinstance(value, str) or not value:
            raise ImageServiceError("图像服务未返回约定的 b64_json 图片数据。")
        if value.startswith("data:"):
            header, value = value.split(",", 1)
            if not header.startswith("data:image/") or not header.endswith(";base64"):
                raise ValueError
        image = base64.b64decode(value, validate=True)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, binascii.Error):
        raise ImageServiceError("图像服务返回的数据格式无效。") from None
    return _normalize_png(image, source=False)


def generate_image(
    source: str | Path,
    *,
    api_key: str | None = None,
    quality: str = "high",
    prompt: str = DEFAULT_PROMPT,
    timeout: float = 240,
) -> bytes:
    """Upload one image and return a verified PNG; no files are written.

    ``api_key=None`` reads XIANJIJI_API_KEY. An explicit empty key fails rather
    than silently falling back. This blocking call belongs in a background task.
    The provider protocol is preserved from the original source; availability
    and model access still require a separately configured account.
    """
    key = os.environ.get(API_KEY_ENV, "") if api_key is None else api_key
    if not isinstance(key, str) or not key.strip():
        raise ImageServiceError("请填写 API Key，或配置 XIANJIJI_API_KEY 环境变量。")
    key = key.strip()
    if any(character.isspace() for character in key):
        raise ImageServiceError("API Key 不能包含空白字符。")
    if any(ord(character) < 32 or ord(character) > 126 for character in key):
        raise ImageServiceError("API Key 格式无效。")
    if quality not in SUPPORTED_QUALITIES:
        raise ImageServiceError("生成质量只能选择 medium 或 high。")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ImageServiceError("请求超时必须是大于 0 的有限秒数。")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ImageServiceError("生图提示词不能为空。")
    try:
        raw_source = Path(source).read_bytes()
    except (OSError, ValueError, TypeError):
        raise ImageServiceError("无法读取所选图片文件。") from None
    image = _normalize_png(raw_source, source=True)
    body, boundary = _multipart({
        "model": MODEL,
        "prompt": prompt,
        "size": IMAGE_SIZE,
        "quality": quality,
        "response_format": "b64_json",
    }, image)
    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        opener = urllib.request.build_opener(_NoRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        # Never include the error body, which may echo request secrets or image data.
        code = exc.code
        exc.close()
        if code in {401, 403}:
            raise ImageServiceError(f"图像服务拒绝认证或访问（HTTP {code}），请检查 API Key 和模型权限。") from None
        raise ImageServiceError(f"图像服务请求失败（HTTP {code}），未自动重试。") from None
    except (socket.timeout, TimeoutError):
        raise ImageServiceError("图像服务请求超时，未自动重试，请稍后手动重试。") from None
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (socket.timeout, TimeoutError)):
            raise ImageServiceError("图像服务请求超时，未自动重试，请稍后手动重试。") from None
        raise ImageServiceError("无法连接图像服务，请检查网络和服务可用性。") from None
    except (OSError, HTTPException):
        raise ImageServiceError("图像服务通信失败，请检查网络和服务可用性。") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ImageServiceError("图像服务返回的数据过大。")
    return _decode_response(raw)


def generate_lineart(
    source: str | Path,
    *,
    api_key: str | None = None,
    quality: str = "high",
    timeout: float = 240,
) -> bytes:
    """Generate line art with the original DEFAULT_PROMPT and return PNG bytes."""
    return generate_image(source, api_key=api_key, quality=quality, prompt=DEFAULT_PROMPT, timeout=timeout)
