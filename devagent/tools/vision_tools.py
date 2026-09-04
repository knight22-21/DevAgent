"""Phase 16 — Vision tools: read_image and take_screenshot.

Images are embedded in tool result strings using a sentinel marker so the
existing message format (AgentMessage.content: str) needs no change.
The LLM message converters in core/llm.py detect the sentinel and build
proper image content blocks for Anthropic and OpenAI.

Sentinel format:  <text>\n__image__:<media_type>:<base64_data>

Providers without vision support (Ollama, Gemini) receive only the text
part — the converter strips the image block before sending.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

# Sentinel shared with devagent/core/llm.py message converters
IMAGE_SENTINEL = "\n__image__:"

# Providers that natively support image content blocks
_VISION_PROVIDERS: frozenset[str] = frozenset({"anthropic", "openai", "groq"})

_SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
})


def register_vision_tools(
    registry,
    project_root: str,
    provider: str = "ollama",
) -> None:
    """Register read_image (and take_screenshot if available)."""

    def read_image(args: dict[str, Any]) -> str:
        path = args.get("path", "").strip()
        if not path:
            return "[error] path is required"
        target = Path(project_root) / path
        if not target.exists():
            return f"[error] File not found: {path}"
        ext = target.suffix.lower()
        if ext not in _SUPPORTED_EXTENSIONS:
            return (
                f"[error] Unsupported image format: {ext}. "
                f"Supported: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}"
            )
        media_type = mimetypes.guess_type(str(target))[0] or "image/png"
        data = base64.standard_b64encode(target.read_bytes()).decode()
        size_kb = target.stat().st_size // 1024
        text = f"Image loaded: {path} ({media_type}, {size_kb} KB)"
        if provider not in _VISION_PROVIDERS:
            return (
                f"{text}\n[Vision not supported for provider '{provider}' — "
                "image content omitted. Switch to 'anthropic' or 'openai'.]"
            )
        return f"{text}{IMAGE_SENTINEL}{media_type}:{data}"

    registry.register(
        "read_image",
        (
            "Load an image file from the project and pass it to the LLM for analysis. "
            "Supported formats: PNG, JPEG, GIF, WebP, BMP. "
            "Use this to inspect screenshots, diagrams, UI mockups, or any visual output."
        ),
        {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the image file, relative to the project root",
                },
            },
            "required": ["path"],
        },
        read_image,
    )

    # take_screenshot: only register when mss or Pillow is available
    try:
        import mss  # noqa: F401
        _register_screenshot(registry, project_root, provider)
    except ImportError:
        try:
            from PIL import ImageGrab  # noqa: F401
            _register_screenshot_pil(registry, project_root, provider)
        except ImportError:
            pass  # screenshot tool omitted — no screen capture library available


def _register_screenshot(registry, project_root: str, provider: str) -> None:
    """Register take_screenshot using mss."""

    def take_screenshot(args: dict[str, Any]) -> str:
        import mss
        import mss.tools

        out_path = Path(project_root) / ".devagent" / "screenshot.png"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with mss.mss() as sct:
            sct.shot(output=str(out_path))

        media_type = "image/png"
        data = base64.standard_b64encode(out_path.read_bytes()).decode()
        text = f"Screenshot captured: {out_path.name}"
        if provider not in _VISION_PROVIDERS:
            return f"{text}\n[Vision not supported for provider '{provider}']"
        return f"{text}{IMAGE_SENTINEL}{media_type}:{data}"

    registry.register(
        "take_screenshot",
        "Capture a screenshot of the current screen and pass it to the LLM.",
        {"type": "object", "properties": {}},
        take_screenshot,
    )


def _register_screenshot_pil(registry, project_root: str, provider: str) -> None:
    """Register take_screenshot using Pillow ImageGrab."""

    def take_screenshot(args: dict[str, Any]) -> str:
        import io

        from PIL import ImageGrab

        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = base64.standard_b64encode(buf.getvalue()).decode()
        text = "Screenshot captured"
        if provider not in _VISION_PROVIDERS:
            return f"{text}\n[Vision not supported for provider '{provider}']"
        return f"{text}{IMAGE_SENTINEL}image/png:{data}"

    registry.register(
        "take_screenshot",
        "Capture a screenshot of the current screen and pass it to the LLM.",
        {"type": "object", "properties": {}},
        take_screenshot,
    )
