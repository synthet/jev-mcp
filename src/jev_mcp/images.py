"""Validated opt-in images; local files are confined to configured roots."""
from __future__ import annotations

import base64
import binascii
import json
import os
import re
import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from .errors import error

IMAGES_HEADER = "TypeSafe-Danger-Zone-Images"
LONG_CONTEXT_HEADER = "TypeSafe-Danger-Zone-Long-Context"
ROOTS_ENV = "JEV_IMAGE_ROOTS"
MIN_SIDE, MAX_SIDE = 280, 1568
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_IMAGES = 16
ALIAS = re.compile(r"[A-Za-z0-9_-]{1,64}")
PLACEHOLDER = re.compile(r"\{\{image:([A-Za-z0-9_-]{1,64})\}\}")
IMAGE_MODEL = re.compile(r"jev-(\d+)\.(\d+)\.\d+")


@dataclass(frozen=True)
class LoadedImage:
    path: Path | None
    data: bytes
    format: str
    width: int
    height: int


def pillow():
    try:
        from PIL import Image
    except ImportError as exc:
        raise error(
            "missing_image_dependency", "Install jev-mcp[vision] for image support."
        ) from exc
    return Image


def image_roots(environ: dict[str, str] | None = None) -> list[Path]:
    env = environ if environ is not None else os.environ
    return [Path(p.strip()).resolve() for p in env.get(ROOTS_ENV, "").split(os.pathsep)
            if p.strip()]


def image_size(data: bytes) -> tuple[str, int, int] | None:
    """Fully decode a bounded still PNG/JPEG; header sniffing alone is insufficient."""
    Image = pillow()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as img:
                if img.format not in ("PNG", "JPEG") or getattr(img, "n_frames", 1) != 1:
                    return None
                width, height = img.size
                if not (MIN_SIDE <= width <= MAX_SIDE and MIN_SIDE <= height <= MAX_SIDE):
                    return None
                fmt = img.format.lower()
                img.verify()
            with Image.open(BytesIO(data)) as img:
                img.load()
        return fmt, width, height
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        return None


def load_images(images: dict[str, Any], roots: list[Path]) -> dict[str, LoadedImage]:
    if not isinstance(images, dict) or not images or len(images) > MAX_IMAGES:
        raise error("invalid_input", f"assets must map 1-{MAX_IMAGES} aliases to images.")
    loaded = {}
    total = 0
    for alias, source in images.items():
        if not isinstance(alias, str) or not ALIAS.fullmatch(alias):
            raise error("invalid_input", "Image aliases must match [A-Za-z0-9_-]{1,64}.")
        path = None
        declared_format = None
        if isinstance(source, dict) and set(source) == {"type", "data_base64", "format"}:
            text, declared_format = source["data_base64"], source["format"]
            if (source["type"] != "image" or declared_format not in ("png", "jpg", "jpeg")
                    or not isinstance(text, str)):
                raise error("invalid_input", "Expected a base64 PNG/JPEG image asset.")
            if len(text) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
                raise error("request_too_large", "Encoded image exceeds 16 MiB decoded.")
            try:
                data = base64.b64decode(text, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise error("invalid_input", "Invalid image base64.") from exc
        else:
            raw_path = (source.get("path") if isinstance(source, dict)
                        and set(source) == {"path"} else source)
            if not roots:
                raise error("images_disabled", f"Local paths require {ROOTS_ENV}.")
            if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
                raise error("invalid_input", "Image paths must be absolute.")
            try:
                path = Path(raw_path).resolve(strict=True)
                if not any(path.is_relative_to(root.resolve()) for root in roots):
                    raise error("invalid_input", "Image is outside the allowed directories.")
                if not path.is_file():
                    raise error("invalid_input", "Image must be a regular file.")
                with path.open("rb") as file:
                    data = file.read(MAX_IMAGE_BYTES + 1)
            except (OSError, ValueError, RuntimeError) as exc:
                raise error("invalid_input", "Image file could not be read.") from exc
        if len(data) > MAX_IMAGE_BYTES:
            raise error("request_too_large", "Image exceeds 16 MiB.")
        info = image_size(data)
        if info is None:
            raise error(
                "invalid_input",
                "Expected a complete still PNG/JPEG, each side 280-1568 px.",
            )
        fmt, width, height = info
        if declared_format and declared_format.replace("jpg", "jpeg") != fmt:
            raise error("invalid_input", "Image format does not match decoded contents.")
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise error("request_too_large", "Images exceed the 32 MiB request budget.")
        loaded[alias] = LoadedImage(path, data, fmt, width, height)
    return loaded


def substitute_images(content: Any, loaded: dict[str, LoadedImage]) -> tuple[Any, dict[str, Any]]:
    """Replace references at any nesting depth, including inside text.

    Whole values become Image objects; embedded references use the SDK string
    protocol. Explicit assets ensure both reach multipart.
    """
    from typesafe_sdk import Image

    assets = {alias: Image(img.data) for alias, img in loaded.items()}
    used: set[str] = set()
    size = len(json.dumps(content, ensure_ascii=False).encode("utf-8")) + 65536
    if size + sum(len(img.data) + 4096 for img in loaded.values()) > MAX_TOTAL_BYTES:
        raise error("request_too_large", "Multipart request exceeds 32 MiB.")

    def reference(match):
        nonlocal size
        alias = match.group(1)
        if alias not in assets:
            raise error("invalid_input", "Content references an unknown image.")
        used.add(alias)
        img = loaded[alias]
        # Conservative local estimate; provider re-encoding can differ.
        size += max(len(img.data), img.width * img.height * 3 + 4096)
        if size > MAX_TOTAL_BYTES:
            raise error("request_too_large", "Expanded image request exceeds 32 MiB.")
        return str(assets[alias])

    def walk(value):
        if isinstance(value, str):
            text = PLACEHOLDER.sub(reference, value)
            if "{{image:" in text:
                raise error("invalid_input", "Malformed image reference.")
            match = PLACEHOLDER.fullmatch(value)
            return assets[match.group(1)] if match else text
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        return value

    result = walk(content)
    if set(assets) != used:
        raise error("invalid_input", "Every asset must be referenced in request content.")
    return result, {str(asset): asset for asset in assets.values()}


def require_image_model(model: str, *, box: bool = False) -> None:
    match = IMAGE_MODEL.fullmatch(model)
    minimum = (1, 14) if box else (1, 13)
    if model == "jev-preview" or (match and (int(match[1]), int(match[2])) >= minimum):
        return
    raise error("invalid_input", "Box requires Jev 1.14+; images require Jev 1.13+.",
                next_steps=["Pin jev-1.14.0 for experimental vision requests."])
