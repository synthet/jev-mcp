"""Opt-in image assets for Jev 1.14+ System One requests.

Images leave this machine for a paid external service, so they are disabled unless
JEV_IMAGE_ROOTS lists allowed directories. Agents pass local paths (never pixels) and
place the exact string "{{image:<alias>}}" as a whole value in state; questions refer
to that state field by name.
"""

from __future__ import annotations

import os
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import error

IMAGES_HEADER = "TypeSafe-Danger-Zone-Images"
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
    path: Path
    data: bytes
    format: str
    width: int
    height: int


def image_roots(environ: dict[str, str] | None = None) -> list[Path]:
    env = environ if environ is not None else os.environ
    raw = env.get(ROOTS_ENV, "")
    return [Path(p).resolve() for p in raw.split(os.pathsep) if p.strip()]


def image_size(data: bytes) -> tuple[str, int, int] | None:
    """(format, width, height) from PNG/JPEG headers, or None if neither."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        width, height = struct.unpack(">II", data[16:24])
        return "png", width, height
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        (length,) = struct.unpack(">H", data[i + 2:i + 4])
        # SOF0-SOF15 except DHT (C4), JPG (C8) and DAC (CC) carry the frame size.
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
            return "jpeg", width, height
        i += 2 + length
    return None


def _inside(path: Path, roots: list[Path]) -> bool:
    return any(path == r or r in path.parents for r in roots)


def load_images(images: dict[str, str], roots: list[Path]) -> dict[str, LoadedImage]:
    if not roots:
        raise error("images_disabled", "Image inputs are disabled on this server.",
                    next_steps=[f"Set {ROOTS_ENV} to the directories images may be read from."])
    if not isinstance(images, dict) or not images or len(images) > MAX_IMAGES:
        raise error("invalid_input", f"images must map 1-{MAX_IMAGES} aliases to file paths.")
    loaded: dict[str, LoadedImage] = {}
    total = 0
    for alias, raw_path in images.items():
        valid_alias = isinstance(alias, str) and ALIAS.fullmatch(alias)
        if not valid_alias or not isinstance(raw_path, str):
            raise error("invalid_input", "Image aliases must match [A-Za-z0-9_-]{1,64}.")
        path = Path(raw_path).resolve()  # resolves symlinks and '..' before the root check
        if not _inside(path, roots):
            raise error("invalid_input", f"Image '{alias}' is outside the allowed directories.")
        if path.suffix.lower() not in (".png", ".jpg", ".jpeg") or not path.is_file():
            raise error("invalid_input", f"Image '{alias}' must be an existing .png/.jpg file.")
        if path.stat().st_size > MAX_IMAGE_BYTES:
            raise error("invalid_input", f"Image '{alias}' exceeds 16 MiB.")
        data = path.read_bytes()
        info = image_size(data)
        if info is None:
            raise error("invalid_input", f"Image '{alias}' is not a valid PNG or JPEG.")
        fmt, width, height = info
        if not (MIN_SIDE <= width <= MAX_SIDE and MIN_SIDE <= height <= MAX_SIDE):
            raise error("invalid_input",
                        f"Image '{alias}' is {width}x{height}; "
                        f"each side must be {MIN_SIDE}-{MAX_SIDE} px.",
                        next_steps=["Resize or pad the image before sending; Jev does not resize."])
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise error("request_too_large", "Images exceed the 32 MiB request budget.")
        loaded[alias] = LoadedImage(path, data, fmt, width, height)
    return loaded


def substitute_images(state: Any, loaded: dict[str, LoadedImage]) -> Any:
    """Replace whole-value placeholders with SDK Image assets; every alias must be used."""
    from typesafe_sdk import Image

    assets = {alias: Image(img.data) for alias, img in loaded.items()}
    used: set[str] = set()

    def walk(value: Any) -> Any:
        if isinstance(value, str):
            match = PLACEHOLDER.fullmatch(value)
            if not match:
                return value
            alias = match.group(1)
            if alias not in assets:
                raise error("invalid_input", f"State references unknown image '{alias}'.")
            used.add(alias)
            return assets[alias]
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        return value

    result = walk(state)
    unused = sorted(set(assets) - used)
    if unused:
        raise error("invalid_input", f"Images {unused} are not referenced in state.",
                    next_steps=['Put "{{image:<alias>}}" as a whole value in state.'])
    return result


def require_image_model(model: str) -> None:
    match = IMAGE_MODEL.fullmatch(model)
    if model == "jev-preview" or (match and (int(match.group(1)), int(match.group(2))) >= (1, 14)):
        return
    raise error("invalid_input", f"Model '{model}' does not accept images.",
                next_steps=["Pin an image-capable model such as jev-1.14.0."])
