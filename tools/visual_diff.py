#!/usr/bin/env python3
"""Deterministic PNG visual comparison for Android App Builder.

No third-party image dependency is required. Supports 8-bit non-interlaced PNG
color types commonly emitted by Android screencap and Chromium screenshots.
"""
from __future__ import annotations

import json
import math
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class ImageRGB:
    width: int
    height: int
    pixels: bytes  # tightly packed RGB


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def read_png(path: Path) -> ImageRGB:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError(f"not a PNG file: {path}")
    pos = len(PNG_SIGNATURE)
    width = height = bit_depth = color_type = interlace = None
    compressed = bytearray()
    while pos + 12 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if len(body) != length:
            raise ValueError("truncated PNG chunk")
        pos += 12 + length
        if kind == b"IHDR":
            if length != 13:
                raise ValueError("invalid PNG IHDR")
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(">IIBBBBB", body)
            if compression != 0 or filtering != 0:
                raise ValueError("unsupported PNG compression/filter method")
        elif kind == b"IDAT":
            compressed.extend(body)
        elif kind == b"IEND":
            break
    if not width or not height:
        raise ValueError("PNG missing dimensions")
    if bit_depth != 8 or interlace != 0:
        raise ValueError("only 8-bit non-interlaced PNG is supported")
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise ValueError(f"unsupported PNG color type: {color_type}")
    raw = zlib.decompress(bytes(compressed))
    stride = width * channels
    expected = height * (stride + 1)
    if len(raw) != expected:
        raise ValueError(f"unexpected PNG payload size: {len(raw)} != {expected}")

    rows: list[bytearray] = []
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        scan = bytearray(raw[offset:offset + stride])
        offset += stride
        prior = rows[-1] if rows else bytearray(stride)
        for i in range(stride):
            left = scan[i - channels] if i >= channels else 0
            up = prior[i]
            upper_left = prior[i - channels] if i >= channels else 0
            if filter_type == 0:
                pass
            elif filter_type == 1:
                scan[i] = (scan[i] + left) & 0xFF
            elif filter_type == 2:
                scan[i] = (scan[i] + up) & 0xFF
            elif filter_type == 3:
                scan[i] = (scan[i] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                scan[i] = (scan[i] + _paeth(left, up, upper_left)) & 0xFF
            else:
                raise ValueError(f"unsupported PNG filter: {filter_type}")
        rows.append(scan)

    rgb = bytearray(width * height * 3)
    out = 0
    for row in rows:
        for x in range(width):
            i = x * channels
            if color_type == 0:
                r = g = b = row[i]
                a = 255
            elif color_type == 2:
                r, g, b = row[i:i + 3]
                a = 255
            elif color_type == 4:
                r = g = b = row[i]
                a = row[i + 1]
            else:
                r, g, b, a = row[i:i + 4]
            # Composite transparency over white for deterministic screenshot comparison.
            if a != 255:
                r = (r * a + 255 * (255 - a)) // 255
                g = (g * a + 255 * (255 - a)) // 255
                b = (b * a + 255 * (255 - a)) // 255
            rgb[out:out + 3] = bytes((r, g, b))
            out += 3
    return ImageRGB(width=width, height=height, pixels=bytes(rgb))


def write_png(path: Path, image: ImageRGB) -> None:
    if len(image.pixels) != image.width * image.height * 3:
        raise ValueError("invalid RGB buffer length")
    rows = bytearray()
    stride = image.width * 3
    for y in range(image.height):
        rows.append(0)
        start = y * stride
        rows.extend(image.pixels[start:start + stride])

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    payload = bytearray(PNG_SIGNATURE)
    payload.extend(chunk(b"IHDR", struct.pack(">IIBBBBB", image.width, image.height, 8, 2, 0, 0, 0)))
    payload.extend(chunk(b"IDAT", zlib.compress(bytes(rows), 9)))
    payload.extend(chunk(b"IEND", b""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(payload))


def solid_image(width: int, height: int, rgb: tuple[int, int, int]) -> ImageRGB:
    return ImageRGB(width, height, bytes(rgb) * (width * height))


def _sample(image: ImageRGB, grid: int) -> list[tuple[int, int, int]]:
    result: list[tuple[int, int, int]] = []
    for gy in range(grid):
        sy = min(image.height - 1, int((gy + 0.5) * image.height / grid))
        for gx in range(grid):
            sx = min(image.width - 1, int((gx + 0.5) * image.width / grid))
            i = (sy * image.width + sx) * 3
            result.append((image.pixels[i], image.pixels[i + 1], image.pixels[i + 2]))
    return result


def _luma(pixel: tuple[int, int, int]) -> float:
    r, g, b = pixel
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _edge_map(samples: list[tuple[int, int, int]], grid: int) -> list[float]:
    lum = [_luma(p) for p in samples]
    edges: list[float] = []
    for y in range(grid):
        for x in range(grid):
            i = y * grid + x
            right = lum[i + 1] if x + 1 < grid else lum[i]
            down = lum[i + grid] if y + 1 < grid else lum[i]
            edges.append(min(255.0, abs(right - lum[i]) + abs(down - lum[i])))
    return edges


def compare_images(reference: Path, candidate: Path, *, grid_size: int = 64, max_score: float = 0.18,
                   diff_path: Path | None = None) -> dict:
    if not 16 <= grid_size <= 256:
        raise ValueError("grid_size must be in [16,256]")
    if not 0.0 <= max_score <= 1.0:
        raise ValueError("max_score must be in [0,1]")
    ref = read_png(reference)
    cand = read_png(candidate)
    a = _sample(ref, grid_size)
    b = _sample(cand, grid_size)
    n = len(a)

    rgb_sum = 0.0
    luma_sum = 0.0
    diffs: list[float] = []
    for pa, pb in zip(a, b):
        per = (abs(pa[0] - pb[0]) + abs(pa[1] - pb[1]) + abs(pa[2] - pb[2])) / (3.0 * 255.0)
        diffs.append(per)
        rgb_sum += per
        luma_sum += abs(_luma(pa) - _luma(pb)) / 255.0
    edge_a = _edge_map(a, grid_size)
    edge_b = _edge_map(b, grid_size)
    edge_mae = sum(abs(x - y) / 255.0 for x, y in zip(edge_a, edge_b)) / n
    rgb_mae = rgb_sum / n
    luma_mae = luma_sum / n

    ref_aspect = ref.width / ref.height
    cand_aspect = cand.width / cand.height
    aspect_delta = min(1.0, abs(math.log(ref_aspect / cand_aspect)))
    # Color remains important, but edge/layout and aspect prevent a same-color blank page from passing.
    score = min(1.0, 0.50 * rgb_mae + 0.25 * luma_mae + 0.20 * edge_mae + 0.05 * aspect_delta)
    result = {
        "ok": score <= max_score,
        "schema": "android-visual-diff-v1",
        "score": round(score, 6),
        "similarity": round(1.0 - score, 6),
        "max_score": max_score,
        "grid_size": grid_size,
        "metrics": {
            "rgb_mae": round(rgb_mae, 6),
            "luma_mae": round(luma_mae, 6),
            "edge_mae": round(edge_mae, 6),
            "aspect_delta": round(aspect_delta, 6),
        },
        "reference": {"width": ref.width, "height": ref.height, "path": str(reference)},
        "candidate": {"width": cand.width, "height": cand.height, "path": str(candidate)},
    }
    if diff_path is not None:
        heat = bytearray(grid_size * grid_size * 3)
        for i, value in enumerate(diffs):
            intensity = max(0, min(255, int(round(value * 255))))
            heat[i * 3:i * 3 + 3] = bytes((intensity, 0, 255 - intensity))
        write_png(diff_path, ImageRGB(grid_size, grid_size, bytes(heat)))
        result["diff_path"] = str(diff_path)
    return result


def write_result(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
