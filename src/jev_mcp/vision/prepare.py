"""Reproducible image preparation and pixel-edge coordinate transforms."""

from __future__ import annotations

import hashlib
import math
from io import BytesIO
from pathlib import Path

from ..errors import error
from ..images import MAX_SIDE, MIN_SIDE, pillow


def tile_regions(width: int, height: int, side: int) -> list[list[int]]:
    """Non-overlapping tiles in EXIF-oriented pixels, suitable for optional refinement."""
    if side < MIN_SIDE:
        raise error("invalid_input", "Tile side must be at least 280 pixels.")
    return [
        [x, y, min(width, x + side), min(height, y + side)]
        for y in range(0, height, side)
        for x in range(0, width, side)
    ]


def prepare_image(
    source: Path,
    output: Path,
    *,
    max_side: int = MAX_SIDE,
    quality: int = 90,
    format: str = "jpeg",
    crop: list[int] | None = None,
) -> dict:
    """Orient, crop, proportionally resize, pad, strip metadata and encode a still.

    The affine matrix maps original file pixel edges to prepared pixel edges.
    Crops use oriented coordinates. Source filenames never enter the receipt.
    """
    Image = pillow()
    from PIL import ImageCms, ImageOps

    if not MIN_SIDE <= max_side <= MAX_SIDE or not 1 <= quality <= 100:
        raise error("invalid_input", "max_side must be 280-1568 and quality 1-100.")
    if format not in ("png", "jpeg"):
        raise error("invalid_input", "Output format must be png or jpeg.")
    try:
        if source.stat().st_size > 64 * 1024 * 1024:
            raise error("request_too_large", "Preparation source exceeds 64 MiB.")
        data = source.read_bytes()
        with Image.open(BytesIO(data)) as raw:
            if getattr(raw, "n_frames", 1) != 1:
                raise error("invalid_input", "Preparation requires one still image.")
            if raw.width * raw.height > 40_000_000:
                raise error("request_too_large", "Preparation source exceeds 40 million pixels.")
            width, height = raw.size
            orientation = raw.getexif().get(274, 1)
            image = ImageOps.exif_transpose(raw)
            if raw.info.get("icc_profile"):
                image = ImageCms.profileToProfile(
                    image,
                    ImageCms.ImageCmsProfile(BytesIO(raw.info["icc_profile"])),
                    ImageCms.createProfile("sRGB"),
                    outputMode="RGB",
                )
            else:
                image = image.convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError, ImageCms.PyCMSError) as exc:
        raise error("invalid_input", "Preparation source could not be decoded.") from exc
    matrices = {
        1: (1, 0, 0, 0, 1, 0),
        2: (-1, 0, width, 0, 1, 0),
        3: (-1, 0, width, 0, -1, height),
        4: (1, 0, 0, 0, -1, height),
        5: (0, 1, 0, 1, 0, 0),
        6: (0, -1, height, 1, 0, 0),
        7: (0, -1, height, -1, 0, width),
        8: (0, 1, 0, -1, 0, width),
    }
    a, b, c, d, e, f = matrices.get(orientation, matrices[1])
    oriented_size = list(image.size)
    crop = crop if crop is not None else [0, 0, image.width, image.height]
    if (
        len(crop) != 4
        or not all(type(v) is int for v in crop)
        or not 0 <= crop[0] < crop[2] <= image.width
        or not 0 <= crop[1] < crop[3] <= image.height
    ):
        raise error("invalid_input", "Crop must lie within the oriented image.")
    image = image.crop(tuple(crop))
    scale = min(1.0, max_side / max(image.size))
    resized = [max(1, round(v * scale)) for v in image.size]
    sx, sy = resized[0] / image.width, resized[1] / image.height
    image = image.resize(tuple(resized), Image.Resampling.LANCZOS)
    size = [max(MIN_SIDE, n) for n in resized]
    px, py = (size[0] - resized[0]) // 2, (size[1] - resized[1]) // 2
    canvas = Image.new("RGB", tuple(size), "white")
    canvas.paste(image, (px, py))
    encoded = BytesIO()
    canvas.save(
        encoded,
        format.upper(),
        **({"quality": quality, "progressive": False} if format == "jpeg" else {}),
    )
    prepared = encoded.getvalue()
    digest = hashlib.sha256(prepared).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{digest}.{format}"
    path.write_bytes(prepared)
    return {
        "path": str(path.resolve()),
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "sha256": digest,
        "original_size": [width, height],
        "orientation": orientation,
        "oriented_size": oriented_size,
        "crop": crop,
        "resized_size": resized,
        "padding": [px, py],
        "output_size": size,
        "format": format,
        "quality": quality,
        "matrix": [
            sx * a,
            sx * b,
            sx * (c - crop[0]) + px,
            sy * d,
            sy * e,
            sy * (f - crop[1]) + py,
        ],
    }


def map_box(box: dict, transform: dict, *, inverse: bool = False) -> dict:
    """Map fractional box edges original ↔ prepared; do not silently clip padding."""
    a, b, c, d, e, f = transform["matrix"]
    source = transform["original_size"]
    target = transform["output_size"]
    if inverse:
        det = a * e - b * d
        a, b, c, d, e, f = (
            e / det,
            -b / det,
            (b * f - e * c) / det,
            -d / det,
            a / det,
            (d * c - a * f) / det,
        )
        source, target = target, source
    points = [
        (box[x] * source[0], box[y] * source[1])
        for x in ("left", "right")
        for y in ("top", "bottom")
    ]
    xs = [(a * x + b * y + c) / target[0] for x, y in points]
    ys = [(d * x + e * y + f) / target[1] for x, y in points]
    if not all(math.isfinite(v) for v in xs + ys):
        raise error("invalid_input", "Box coordinates must be finite.")
    return {"left": min(xs), "right": max(xs), "top": min(ys), "bottom": max(ys)}


def overlay(image_path: Path, boxes: list[dict], output: Path) -> None:
    """Save an offline overlay of normalized boxes on prepared pixels."""
    Image = pillow()
    from PIL import ImageDraw

    with Image.open(image_path) as raw:
        image = raw.convert("RGB")
    draw = ImageDraw.Draw(image)
    for box in boxes:
        draw.rectangle(
            (
                box["left"] * image.width,
                box["top"] * image.height,
                box["right"] * image.width,
                box["bottom"] * image.height,
            ),
            outline="red",
            width=3,
        )
    image.save(output, "PNG")
