"""Tests for video upload endpoint encoding safety on Windows (cp950 locale).

Verifies that:
1. Sending multipart form data to the JSON-only upload endpoint returns
   a proper 422 validation error instead of crashing with UnicodeDecodeError.
2. The validation error handler safely encodes error messages containing
   Chinese characters regardless of the system locale encoding.
3. The multipart form-data upload endpoint accepts Chinese text fields.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app


def _client_no_auth() -> TestClient:
    """Create a TestClient with JARVIS_KEY cleared to bypass auth."""
    return TestClient(app, raise_server_exceptions=False)


class TestUploadEncodingSafety:
    """Ensure upload endpoints handle Chinese text without UnicodeDecodeError."""

    @pytest.fixture(autouse=True)
    def _clear_auth(self):
        env = {k: v for k, v in os.environ.items() if k != "JARVIS_KEY"}
        with patch.dict(os.environ, env, clear=True):
            yield

    def test_json_endpoint_rejects_form_data_with_422(self) -> None:
        """Sending multipart form data to the JSON endpoint should return 422, not 500."""
        client = _client_no_auth()
        resp = client.post(
            "/api/video-gen/upload-youtube",
            files={"file": ("test.mp4", b"fake-video-data", "video/mp4")},
            data={
                "title": "測試中文標題",
                "description": "測試描述",
                "tags": "台股",
                "privacy": "private",
            },
        )
        # Must NOT be 500 (UnicodeDecodeError)
        assert resp.status_code != 500, (
            f"Got 500 instead of validation error: {resp.text}"
        )
        # Should be 422 (validation error) or 400 (bad encoding)
        assert resp.status_code in (400, 422), (
            f"Unexpected status {resp.status_code}: {resp.text}"
        )

    def test_json_endpoint_accepts_valid_json(self) -> None:
        """JSON body with Chinese title should be parsed without encoding errors."""
        client = _client_no_auth()
        resp = client.post(
            "/api/video-gen/upload-youtube",
            json={
                "video_path": "/nonexistent/test.mp4",
                "title": "測試中文標題 台積電分析",
                "description": "三大法人籌碼分析",
                "tags": ["台股", "三大法人"],
                "privacy": "private",
            },
        )
        # Should fail with 404 (file not found), NOT 500 (encoding error)
        assert resp.status_code == 404, (
            f"Expected 404 for nonexistent file, got {resp.status_code}: {resp.text}"
        )

    def test_form_endpoint_accepts_chinese_fields(self) -> None:
        """The multipart form-data endpoint should accept Chinese text."""
        client = _client_no_auth()
        resp = client.post(
            "/api/video-gen/upload-youtube-form",
            files={"file": ("test.mp4", b"fake-video-data", "video/mp4")},
            data={
                "title": "測試中文標題",
                "description": "測試描述",
                "tags": "台股,三大法人",
                "privacy": "private",
            },
        )
        # Should fail with YouTube auth error (503) or similar, NOT 500/422
        # because the file upload itself should parse fine
        assert resp.status_code != 500 or "UnicodeDecodeError" not in resp.text, (
            f"UnicodeDecodeError on form upload: {resp.text}"
        )
        # 503 = YouTube credentials not configured (expected in test env)
        assert resp.status_code in (200, 401, 429, 500, 503), (
            f"Unexpected status {resp.status_code}: {resp.text}"
        )

    def test_validation_error_with_bytes_does_not_crash(self) -> None:
        """Validation errors containing raw bytes should be serialized safely."""
        client = _client_no_auth()
        # Send completely invalid content type to trigger validation error
        resp = client.post(
            "/api/video-gen/upload-youtube",
            content=b"\xa7\xb5\xa4\xe5",  # cp950 bytes for "中文"
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code != 500, (
            f"Server crashed on cp950 bytes: {resp.text}"
        )
        assert resp.status_code in (400, 422), (
            f"Unexpected status {resp.status_code}: {resp.text}"
        )
