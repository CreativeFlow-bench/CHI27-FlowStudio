"""FlowStudio planner server — Qwen2.5-VL (multimodal).

OpenAI-compatible /v1/chat/completions that accepts text and image_url content
parts. Replaces the text-only Qwen3-8B planner on the same host/port so the
existing westd tunnel (18085 -> weste 18084) keeps working unchanged.
"""

from __future__ import annotations

import base64
import io
import os
import time
import uuid
from typing import Any, Optional

import requests
import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


MODEL_PATH = os.getenv("FLOWSTUDIO_VL_MODEL_PATH", "/root/models_vl/Qwen/Qwen2.5-VL-7B-Instruct")
SERVED_MODEL = os.getenv("FLOWSTUDIO_VL_MODEL_NAME", "qwen2.5-vl-planner")


class ChatMessage(BaseModel):
    role: str
    content: Any


class ChatRequest(BaseModel):
    model: Optional[str] = SERVED_MODEL
    messages: list[ChatMessage]
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None


app = FastAPI(title="FlowStudio VL Planner")
model: Any = None
processor: Any = None


def _content_parts(content: Any) -> list[dict[str, Any]]:
    """Normalize message content into OpenAI-style parts (text / image_url)."""
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        parts: list[dict[str, Any]] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                parts.append({"type": "text", "text": str(item.get("text", ""))})
            elif item.get("type") == "image_url":
                url = ""
                raw = item.get("image_url")
                if isinstance(raw, str):
                    url = raw
                elif isinstance(raw, dict):
                    url = str(raw.get("url") or "")
                parts.append({"type": "image_url", "image_url": {"url": url}})
        return parts
    return [{"type": "text", "text": str(content)}]


def _load_image(url: str) -> Any:
    """Fetch image from data URL or http(s) and return a PIL image."""
    from PIL import Image

    if url.startswith("data:"):
        _, payload = url.split(",", 1)
        raw = base64.b64decode(payload)
        return Image.open(io.BytesIO(raw)).convert("RGB")
    if url.startswith(("http://", "https://")):
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGB")
    raise ValueError(f"unsupported image url: {url[:80]}")


def _load_model() -> None:
    global model, processor
    from transformers import AutoModelForImageTextToText, AutoProcessor

    processor = AutoProcessor.from_pretrained(MODEL_PATH, trust_remote_code=True)
    model = AutoModelForImageTextToText.from_pretrained(
        MODEL_PATH,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
        low_cpu_mem_usage=True,
    )
    model.eval()


@app.on_event("startup")
def startup() -> None:
    _load_model()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": model is not None,
        "model": SERVED_MODEL,
        "model_path": MODEL_PATH,
        "cuda": torch.cuda.is_available(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }


@app.get("/v1/models")
def models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [{"id": SERVED_MODEL, "object": "model", "created": 0, "owned_by": "flowstudio"}],
    }


@app.post("/v1/chat/completions")
def chat(req: ChatRequest) -> dict[str, Any]:
    if model is None or processor is None:
        raise HTTPException(status_code=503, detail="model not loaded")
    try:
        messages = [_content_parts(message.content) for message in req.messages]
        roles = [message.role for message in req.messages]
        conversation: list[dict[str, Any]] = []
        images: list[Any] = []
        for role, parts in zip(roles, messages):
            text_chunks: list[str] = []
            for part in parts:
                if part["type"] == "text":
                    text_chunks.append(part["text"])
                elif part["type"] == "image_url":
                    images.append(_load_image(part["image_url"]["url"]))
                    # Qwen2.5-VL 的聊天模板只识别官方视觉 token；
                    # image_pad 会在 processor 里按 patch 数展开。
                    text_chunks.append("<|vision_start|><|image_pad|><|vision_end|>")
            conversation.append({"role": role, "content": "\n".join(text_chunks) or "<image>"})
        if not images:
            images = None
        text = processor.apply_chat_template(conversation, tokenize=False, add_generation_prompt=True)
        inputs = processor(
            text=text,
            images=images,
            return_tensors="pt",
        ).to(model.device)
        max_new_tokens = max(1, min(int(req.max_tokens or 512), 2048))
        temperature = float(req.temperature if req.temperature is not None else 0.2)
        do_sample = temperature > 0.001
        gen_kwargs: dict[str, Any] = {
            "max_new_tokens": max_new_tokens,
            "do_sample": do_sample,
            "pad_token_id": processor.tokenizer.eos_token_id,
        }
        if do_sample:
            gen_kwargs["temperature"] = max(0.01, temperature)
            gen_kwargs["top_p"] = float(req.top_p or 0.9)
        with torch.inference_mode():
            output_ids = model.generate(**inputs, **gen_kwargs)
        input_len = inputs["input_ids"].shape[-1]
        new_ids = output_ids[0][input_len:]
        text = processor.decode(new_ids, skip_special_tokens=True).strip()
        if "</think>" in text:
            text = text.split("</think>", 1)[1].strip()
        created = int(time.time())
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": created,
            "model": req.model or SERVED_MODEL,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": int(input_len),
                "completion_tokens": int(len(new_ids)),
                "total_tokens": int(input_len + len(new_ids)),
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"VL inference failed: {exc}") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("FLOWSTUDIO_VL_PORT", "18084")))
