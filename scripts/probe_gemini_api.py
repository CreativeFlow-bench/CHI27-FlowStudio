#!/usr/bin/env python3
"""Probe the Gemini relay before relying on any model id (strategy doc 8.2).

Checks, in order:
1. GET {base}/models and prints available model ids (masked, no key).
2. minimal text chat/completions.
3. small multimodal request (1x1 png data URL).
4. JSON response_format support.
5. timeout/429/5xx/empty-response handling is verified by the client's bounded
   retries at runtime; the probe only reports which models answer OK.

Usage:
    GEMINI_API_KEY=... python3 scripts/probe_gemini_api.py
"""

from __future__ import annotations

import base64
import json
import os
import ssl
import struct
import sys
import urllib.error
import urllib.request
import zlib
from pathlib import Path


def _load_dotenv() -> None:
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _headers() -> dict[str, str]:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        print("GEMINI_API_KEY is required (env or repo-root .env).")
        sys.exit(2)
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _get(url: str) -> dict:
    request = urllib.request.Request(
        url, headers={"Authorization": _headers()["Authorization"]}, method="GET"
    )
    with _open(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _post(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(),
        method="POST",
    )
    with _open(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _open(request, timeout: float):
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ssl.SSLCertVerificationError):
            # Homebrew/macOS python often lacks CA roots; verified-first, then
            # fall back to unverified for the relay endpoint.
            return urllib.request.urlopen(
                request, timeout=timeout, context=ssl._create_unverified_context()
            )
        raise


def _tiny_png_data_url() -> str:
    def chunk(tag: bytes, data: bytes) -> bytes:
        payload = tag + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = b"\x00" + bytes([255, 0, 0])
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def main() -> int:
    _load_dotenv()
    base = os.environ.get("GEMINI_API_BASE", "https://128api.cn/v1").rstrip("/")
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    print(f"base={base} configured_model={model} key={'<set>' if os.environ.get('GEMINI_API_KEY') else '<missing>'}")

    models = _get(f"{base}/models").get("data", [])
    ids = [item.get("id") for item in models if isinstance(item, dict) and item.get("id")]
    print(f"models_count={len(ids)}")
    print("gemini_ids=" + json.dumps(sorted(i for i in ids if "gemini" in str(i).lower())[:40], ensure_ascii=False))
    print(f"configured_model_present={model in ids}")

    text_payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "max_tokens": 16,
    }
    text = _post(f"{base}/chat/completions", text_payload)
    print(f"text_ok=True content={text['choices'][0]['message']['content'][:40]!r}")

    image_payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe the image in one word."},
                    {
                        "type": "image_url",
                        "image_url": {"url": _tiny_png_data_url()},
                    },
                ],
            }
        ],
        "max_tokens": 32,
    }
    try:
        image = _post(f"{base}/chat/completions", image_payload)
        print(f"multimodal_ok=True content={image['choices'][0]['message']['content'][:40]!r}")
    except urllib.error.HTTPError as exc:
        print(f"multimodal_ok=False http={exc.code} body={exc.read().decode('utf-8', errors='replace')[:200]}")

    json_payload = {
        "model": model,
        "messages": [{"role": "user", "content": 'Return {"ok": true}'}],
        "max_tokens": 32,
        "response_format": {"type": "json_object"},
    }
    try:
        js = _post(f"{base}/chat/completions", json_payload)
        content = js["choices"][0]["message"]["content"]
        json.loads(content)
        print("json_object_ok=True")
    except Exception as exc:  # noqa: BLE001
        print(f"json_object_ok=False error={type(exc).__name__}: {str(exc)[:160]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
