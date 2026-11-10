from __future__ import annotations

import base64
from email import policy
from email.parser import BytesParser
from http.client import IncompleteRead
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from PIL import Image

from core.image_client import (
    API_URL,
    IMAGE_SIZE,
    MAX_RESPONSE_BYTES,
    MODEL,
    ImageServiceError,
    _NoRedirectHandler,
    generate_image,
    generate_lineart,
)
from core.image_prompts import DEFAULT_PROMPT, MOUTH_CORRECTION_PROMPT


def picture(format: str = "PNG") -> bytes:
    stream = BytesIO()
    Image.new("RGB", (8, 6), "white").save(stream, format=format)
    return stream.getvalue()


class ImageClientTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = Path(self.directory.name) / "测试 图片.png"
        self.source.write_bytes(picture())
        self.key = "test-key-not-a-real-credential"
        self.payload = json.dumps({"data": [{"b64_json": base64.b64encode(picture()).decode("ascii")}]}).encode("utf-8")
        self.patch = patch("core.image_client.urllib.request.build_opener")
        self.opener_factory = self.patch.start()
        self.addCleanup(self.patch.stop)
        self.transport = self.opener_factory.return_value.open
        self.response = MagicMock()
        self.response.read.return_value = self.payload
        self.transport.return_value.__enter__.return_value = self.response

    def assert_png(self, raw):
        with Image.open(BytesIO(raw)) as image:
            self.assertEqual(image.format, "PNG")
            image.load()

    def request_parts(self):
        request = self.transport.call_args.args[0]
        mime = f"Content-Type: {request.get_header('Content-type')}\r\nMIME-Version: 1.0\r\n\r\n".encode("ascii") + request.data
        message = BytesParser(policy=policy.default).parsebytes(mime)
        parts = {part.get_param("name", header="Content-Disposition"): part for part in message.iter_parts()}
        return request, parts

    def test_lineart_uses_original_protocol_prompt_and_png_upload(self):
        result = generate_lineart(self.source, api_key=self.key, quality="medium", timeout=12)
        self.assert_png(result)
        request, parts = self.request_parts()
        self.assertEqual(request.full_url, API_URL)
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.get_header("Authorization"), f"Bearer {self.key}")
        expected = {"model": MODEL, "prompt": DEFAULT_PROMPT, "size": IMAGE_SIZE, "quality": "medium", "response_format": "b64_json"}
        for key, value in expected.items():
            self.assertEqual(parts[key].get_payload(decode=True).decode("utf-8"), value)
        self.assertEqual(parts["image"].get_content_type(), "image/png")
        self.assertEqual(parts["image"].get_filename(), "source.png")
        self.assert_png(parts["image"].get_payload(decode=True))
        self.assertEqual(self.transport.call_args.kwargs["timeout"], 12)
        self.transport.assert_called_once()

    def test_jpeg_and_bmp_are_normalized_before_upload(self):
        for format in ("JPEG", "BMP"):
            with self.subTest(format=format):
                self.source.write_bytes(picture(format))
                generate_lineart(self.source, api_key=self.key)
                _, parts = self.request_parts()
                self.assert_png(parts["image"].get_payload(decode=True))

    def test_environment_key_and_data_url_response(self):
        self.response.read.return_value = json.dumps({"data": [{"b64_json": "data:image/png;base64," + base64.b64encode(picture()).decode("ascii")}]}).encode("utf-8")
        with patch.dict(os.environ, {"XIANJIJI_API_KEY": self.key}):
            self.assert_png(generate_lineart(self.source))
        request, _ = self.request_parts()
        self.assertEqual(request.get_header("Authorization"), f"Bearer {self.key}")

    def test_optional_prompt_supports_original_correction_prompts(self):
        generate_image(self.source, api_key=self.key, prompt=MOUTH_CORRECTION_PROMPT)
        _, parts = self.request_parts()
        self.assertEqual(parts["prompt"].get_payload(decode=True).decode("utf-8"), MOUTH_CORRECTION_PROMPT)

    def test_internal_key_whitespace_is_rejected_before_network_use(self):
        for whitespace in (" ", "\t", "\r", "\n", "\u00a0", "\u3000"):
            with self.subTest(whitespace=repr(whitespace)):
                with self.assertRaisesRegex(ImageServiceError, "不能包含空白字符"):
                    generate_lineart(self.source, api_key="test" + whitespace + "key")
        self.transport.assert_not_called()

    def test_surrounding_key_whitespace_is_trimmed_like_the_ui(self):
        generate_lineart(self.source, api_key=" \t" + self.key + "\r\n")
        request, _ = self.request_parts()
        self.assertEqual(request.get_header("Authorization"), f"Bearer {self.key}")

    def test_missing_or_invalid_configuration_never_contacts_service(self):
        with patch.dict(os.environ, {}, clear=True):
            for options in ({}, {"api_key": ""}, {"api_key": "x\r\nInjected: key"}):
                with self.subTest(options=options):
                    with self.assertRaises(ImageServiceError):
                        generate_lineart(self.source, **options)
        for quality in ("low", "unknown", None):
            with self.subTest(quality=quality):
                with self.assertRaises(ImageServiceError):
                    generate_lineart(self.source, api_key=self.key, quality=quality)
        for timeout in (0, -1, float("nan"), float("inf"), "240", True):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ImageServiceError):
                    generate_lineart(self.source, api_key=self.key, timeout=timeout)
        self.transport.assert_not_called()

    def test_unreadable_or_unsupported_input_never_contacts_service(self):
        self.source.write_bytes(b"not a picture")
        with self.assertRaises(ImageServiceError):
            generate_lineart(self.source, api_key=self.key)
        self.source.write_bytes(picture("GIF"))
        with self.assertRaises(ImageServiceError):
            generate_lineart(self.source, api_key=self.key)
        with self.assertRaises(ImageServiceError):
            generate_lineart(self.source.with_name("missing.png"), api_key=self.key)
        self.transport.assert_not_called()

    def test_malformed_or_nonimage_responses_are_rejected_without_raw_text(self):
        responses = [
            b"not json " + self.key.encode("ascii"),
            b"[]",
            b'{"data":[]}',
            b'{"data":[null]}',
            json.dumps({"data": [{"url": "https://example.invalid/private/" + self.key}]}).encode("utf-8"),
            b'{"data":[{"b64_json":"%%%"}]}',
            json.dumps({"data": [{"b64_json": base64.b64encode(self.key.encode()).decode("ascii")}]}).encode(),
            json.dumps({"data": [{"b64_json": "data:text/plain;base64,aGk="}]}).encode(),
        ]
        for payload in responses:
            with self.subTest(payload=payload[:30]):
                self.response.read.return_value = payload
                with self.assertRaises(ImageServiceError) as failure:
                    generate_lineart(self.source, api_key=self.key)
                self.assertNotIn(self.key, str(failure.exception))

    def test_http_failure_does_not_echo_body_and_does_not_retry(self):
        self.transport.side_effect = urllib.error.HTTPError(API_URL, 401, self.key, {}, BytesIO(self.key.encode()))
        with self.assertRaisesRegex(ImageServiceError, "HTTP 401") as failure:
            generate_lineart(self.source, api_key=self.key)
        self.assertNotIn(self.key, str(failure.exception))
        self.assertTrue(failure.exception.__suppress_context__)
        self.transport.assert_called_once()

    def test_timeout_and_network_failures_are_sanitized_without_retry(self):
        for error in (TimeoutError(self.key), urllib.error.URLError(TimeoutError(self.key)), urllib.error.URLError(self.key), OSError(self.key)):
            with self.subTest(error=type(error).__name__):
                self.transport.reset_mock()
                self.transport.side_effect = error
                with self.assertRaises(ImageServiceError) as failure:
                    generate_lineart(self.source, api_key=self.key)
                self.assertNotIn(self.key, str(failure.exception))
                self.assertTrue(failure.exception.__suppress_context__)
                self.transport.assert_called_once()

    def test_redirect_is_refused_instead_of_forwarding_key(self):
        handler = _NoRedirectHandler()
        self.assertIsNone(handler.redirect_request(None, None, 302, "moved", {}, "https://another.invalid"))

    def test_incomplete_response_read_is_sanitized_without_retry(self):
        self.response.read.side_effect = IncompleteRead(self.key.encode())
        with self.assertRaises(ImageServiceError) as failure:
            generate_lineart(self.source, api_key=self.key)
        self.assertNotIn(self.key, str(failure.exception))
        self.assertTrue(failure.exception.__suppress_context__)
        self.transport.assert_called_once()

    def test_response_read_is_bounded_and_oversize_is_rejected(self):
        self.response.read.return_value = b"x" * (MAX_RESPONSE_BYTES + 1)
        with self.assertRaisesRegex(ImageServiceError, "过大"):
            generate_lineart(self.source, api_key=self.key)
        self.response.read.assert_called_once_with(MAX_RESPONSE_BYTES + 1)
        self.transport.assert_called_once()


if __name__ == "__main__":
    unittest.main()
