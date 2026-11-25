"""Pure-Python PNG decoder and pixel-accurate visual regression diffing engine with Region Masking & Anti-Aliasing Filter.

Supports 8-bit RGB (color_type=2) and RGBA (color_type=6) non-interlaced PNG
images with all 5 standard PNG scanline filters (None, Sub, Up, Average, Paeth),
bounding-box ignore masks (x, y, width, height), subpixel anti-aliasing edge
tolerance, and magenta diff heatmap PNG output.
"""
from __future__ import annotations

import struct
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .visual_evidence import _encode_rgb_png

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def parse_mask_spec(spec: str) -> tuple[int, int, int, int]:
    """Parse an 'x,y,w,h' bounding-box mask string into validated non-negative integers."""
    parts = [p.strip() for p in spec.split(",")]
    if len(parts) != 4:
        raise ValueError(f"mask region must have format 'x,y,w,h', got {spec!r}")
    x, y, w, h = (int(v) for v in parts)
    if x < 0 or y < 0 or w <= 0 or h <= 0:
        raise ValueError(f"mask region requires x>=0, y>=0, w>0, h>0, got {spec!r}")
    return x, y, w, h


@dataclass(frozen=True)
class VisualDiffResult:
    """Result of comparing a baseline PNG against a current PNG screenshot."""

    passed: bool
    dimensions_match: bool
    baseline_size: tuple[int, int]
    current_size: tuple[int, int]
    total_pixels: int
    mismatch_pixels: int
    mismatch_pct: float
    max_channel_delta: int
    threshold_pct: float
    pixel_tolerance: int
    masked_pixels: int = 0
    antialiased_pixels: int = 0
    diff_image_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "dimensions_match": self.dimensions_match,
            "baseline_size": list(self.baseline_size),
            "current_size": list(self.current_size),
            "total_pixels": self.total_pixels,
            "masked_pixels": self.masked_pixels,
            "antialiased_pixels": self.antialiased_pixels,
            "mismatch_pixels": self.mismatch_pixels,
            "mismatch_pct": self.mismatch_pct,
            "max_channel_delta": self.max_channel_delta,
            "threshold_pct": self.threshold_pct,
            "pixel_tolerance": self.pixel_tolerance,
            "diff_image_path": str(self.diff_image_path) if self.diff_image_path else None,
        }


def _paeth_predictor(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def decode_png_rgb(path: Path) -> tuple[int, int, bytearray]:
    """Decode an 8-bit RGB or RGBA non-interlaced PNG file into flat RGB bytes."""
    raw = path.read_bytes()
    if len(raw) < 24 or raw[:8] != _PNG_SIGNATURE:
        raise ValueError(f"not a valid PNG file: {path}")

    offset = 8
    width = height = bit_depth = color_type = interlace = 0
    idat_chunks: list[bytes] = []

    while offset + 8 <= len(raw):
        length = struct.unpack(">I", raw[offset : offset + 4])[0]
        chunk_type = raw[offset + 4 : offset + 8]
        chunk_data = raw[offset + 8 : offset + 8 + length]
        offset += 12 + length

        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", chunk_data)
        elif chunk_type == b"IDAT":
            idat_chunks.append(chunk_data)
        elif chunk_type == b"IEND":
            break

    if width <= 0 or height <= 0:
        raise ValueError(f"PNG missing valid IHDR dimensions: {path}")
    if interlace != 0 or bit_depth != 8 or color_type not in {2, 6}:
        raise ValueError(
            f"unsupported PNG format (bit_depth={bit_depth}, color_type={color_type}, interlace={interlace}); "
            "expected 8-bit non-interlaced RGB/RGBA"
        )

    bpp = 3 if color_type == 2 else 4
    stride = width * bpp
    decompressed = zlib.decompress(b"".join(idat_chunks))
    expected_len = height * (1 + stride)
    if len(decompressed) < expected_len:
        raise ValueError(f"truncated PNG image data in {path}")

    prev_row = bytearray(stride)
    rgb_out = bytearray(width * height * 3)
    out_idx = 0
    pos = 0

    for _ in range(height):
        filter_type = decompressed[pos]
        pos += 1
        cur_row = bytearray(decompressed[pos : pos + stride])
        pos += stride

        if filter_type == 1:
            for i in range(bpp, stride):
                cur_row[i] = (cur_row[i] + cur_row[i - bpp]) & 0xFF
        elif filter_type == 2:
            for i in range(stride):
                cur_row[i] = (cur_row[i] + prev_row[i]) & 0xFF
        elif filter_type == 3:
            for i in range(stride):
                left = cur_row[i - bpp] if i >= bpp else 0
                cur_row[i] = (cur_row[i] + ((left + prev_row[i]) >> 1)) & 0xFF
        elif filter_type == 4:
            for i in range(stride):
                left = cur_row[i - bpp] if i >= bpp else 0
                up = prev_row[i]
                up_left = prev_row[i - bpp] if i >= bpp else 0
                cur_row[i] = (cur_row[i] + _paeth_predictor(left, up, up_left)) & 0xFF
        elif filter_type != 0:
            raise ValueError(f"unsupported PNG scanline filter {filter_type}")

        if bpp == 3:
            rgb_out[out_idx : out_idx + stride] = cur_row
            out_idx += stride
        else:
            for px in range(0, stride, 4):
                rgb_out[out_idx] = cur_row[px]
                rgb_out[out_idx + 1] = cur_row[px + 1]
                rgb_out[out_idx + 2] = cur_row[px + 2]
                out_idx += 3
        prev_row = cur_row

    return width, height, rgb_out


def _pixel_lum(rgb: bytearray, idx: int) -> float:
    return rgb[idx] * 0.299 + rgb[idx + 1] * 0.587 + rgb[idx + 2] * 0.114


def _is_antialiased_pixel(rgb: bytearray, x: int, y: int, width: int, height: int) -> bool:
    """Detect whether (x, y) sits on a high-contrast 1px gradient edge (font/vector anti-aliasing)."""
    if x <= 0 or y <= 0 or x >= width - 1 or y >= height - 1:
        return False
    center = _pixel_lum(rgb, (y * width + x) * 3)
    min_lum = center
    max_lum = center
    zero_Siblings = 0
    for ny in (y - 1, y, y + 1):
        row_base = ny * width
        for nx in (x - 1, x, x + 1):
            if nx == x and ny == y:
                continue
            lum = _pixel_lum(rgb, (row_base + nx) * 3)
            if abs(lum - center) < 1.5:
                zero_Siblings += 1
            if lum < min_lum:
                min_lum = lum
            if lum > max_lum:
                max_lum = lum
    # True anti-aliased edge pixel sits strictly between darker and brighter neighbors on a sharp edge
    return (max_lum - min_lum) >= 45.0 and min_lum < center - 3.0 and max_lum > center + 3.0 and zero_Siblings <= 2


def compare_png_images(
    baseline_path: Path,
    current_path: Path,
    diff_output_path: Path | None = None,
    *,
    pixel_tolerance: int = 10,
    max_mismatch_pct: float = 0.5,
    mask_regions: Sequence[tuple[int, int, int, int]] = (),
    ignore_antialiasing: bool = False,
) -> VisualDiffResult:
    """Compare two PNG images pixel-by-pixel with optional bounding-box masks and anti-aliasing filter."""
    if pixel_tolerance < 0 or pixel_tolerance > 255:
        raise ValueError("pixel_tolerance must be between 0 and 255")
    if max_mismatch_pct < 0 or max_mismatch_pct > 100:
        raise ValueError("max_mismatch_pct must be between 0 and 100")

    bw, bh, b_rgb = decode_png_rgb(baseline_path)
    cw, ch, c_rgb = decode_png_rgb(current_path)

    if (bw, bh) != (cw, ch):
        total = max(bw * bh, cw * ch)
        return VisualDiffResult(
            passed=False,
            dimensions_match=False,
            baseline_size=(bw, bh),
            current_size=(cw, ch),
            total_pixels=total,
            mismatch_pixels=total,
            mismatch_pct=100.0,
            max_channel_delta=255,
            threshold_pct=max_mismatch_pct,
            pixel_tolerance=pixel_tolerance,
            diff_image_path=None,
        )

    total_pixels = bw * bh
    mask_bitmap: bytearray | None = None
    masked_pixels = 0
    if mask_regions:
        mask_bitmap = bytearray(total_pixels)
        for mx, my, mw, mh in mask_regions:
            x0, y0 = max(0, mx), max(0, my)
            x1, y1 = min(bw, mx + mw), min(bh, my + mh)
            if x0 >= x1 or y0 >= y1:
                continue
            span = x1 - x0
            ones = b"\x01" * span
            for py in range(y0, y1):
                start = py * bw + x0
                mask_bitmap[start : start + span] = ones
        masked_pixels = mask_bitmap.count(1)

    mismatch_pixels = 0
    antialiased_pixels = 0
    max_delta = 0
    diff_pixels = bytearray(len(b_rgb)) if diff_output_path is not None else None

    for p_idx in range(total_pixels):
        idx = p_idx * 3
        if mask_bitmap is not None and mask_bitmap[p_idx]:
            if diff_pixels is not None:
                # Cool slate-cyan tint for masked / ignored regions
                lum = int(_pixel_lum(b_rgb, idx) * 0.25)
                diff_pixels[idx] = lum
                diff_pixels[idx + 1] = min(255, lum + 50)
                diff_pixels[idx + 2] = min(255, lum + 80)
            continue

        dr = abs(b_rgb[idx] - c_rgb[idx])
        dg = abs(b_rgb[idx + 1] - c_rgb[idx + 1])
        db = abs(b_rgb[idx + 2] - c_rgb[idx + 2])
        local_max = dr if dr >= dg and dr >= db else (dg if dg >= db else db)
        if local_max > max_delta:
            max_delta = local_max

        if local_max > pixel_tolerance:
            if ignore_antialiasing:
                px_x = p_idx % bw
                px_y = p_idx // bw
                if _is_antialiased_pixel(b_rgb, px_x, px_y, bw, bh) or _is_antialiased_pixel(c_rgb, px_x, px_y, bw, bh):
                    antialiased_pixels += 1
                    if diff_pixels is not None:
                        # Subtle amber tint for ignored anti-aliased edge pixels
                        diff_pixels[idx] = 180
                        diff_pixels[idx + 1] = 140
                        diff_pixels[idx + 2] = 40
                    continue
            mismatch_pixels += 1
            if diff_pixels is not None:
                diff_pixels[idx] = 255
                diff_pixels[idx + 1] = 45
                diff_pixels[idx + 2] = 85
        elif diff_pixels is not None:
            lum = int(_pixel_lum(b_rgb, idx) * 0.35)
            diff_pixels[idx] = lum
            diff_pixels[idx + 1] = lum
            diff_pixels[idx + 2] = lum

    if diff_output_path is not None and diff_pixels is not None:
        diff_output_path.parent.mkdir(parents=True, exist_ok=True)
        diff_output_path.write_bytes(_encode_rgb_png(bw, bh, diff_pixels))

    effective_pixels = max(1, total_pixels - masked_pixels)
    mismatch_pct = round((mismatch_pixels / effective_pixels) * 100.0, 4)
    passed = mismatch_pct <= max_mismatch_pct

    return VisualDiffResult(
        passed=passed,
        dimensions_match=True,
        baseline_size=(bw, bh),
        current_size=(cw, ch),
        total_pixels=total_pixels,
        mismatch_pixels=mismatch_pixels,
        mismatch_pct=mismatch_pct,
        max_channel_delta=max_delta,
        threshold_pct=max_mismatch_pct,
        pixel_tolerance=pixel_tolerance,
        masked_pixels=masked_pixels,
        antialiased_pixels=antialiased_pixels,
        diff_image_path=diff_output_path,
    )
