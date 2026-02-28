#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from PIL import Image

MAGIC_GBIX = b"GBIX"
MAGIC_PVRT = b"PVRT"

PVR_PIXEL_ARGB1555 = 0x00
PVR_PIXEL_ARGB4444 = 0x02

PVR_DATA_SQUARE_TWIDDLED = 0x01
PVR_DATA_RECTANGLE = 0x09


@dataclass
class PvrMeta:
    gbix: int
    pixel_format: int
    data_format: int
    width: int
    height: int
    pvrt_size_field: int
    has_gbix: bool


def _expand_4bit(v: int) -> int:
    return (v << 4) | v


def _parse_header(raw: bytes) -> Tuple[PvrMeta, int]:
    off = 0
    has_gbix = False
    gbix = 0
    if raw[:4] == MAGIC_GBIX:
        has_gbix = True
        gbix = int.from_bytes(raw[8:12], "little", signed=False)
        off = 16
    if raw[off:off + 4] != MAGIC_PVRT:
        raise ValueError("PVRT header not found")
    size = int.from_bytes(raw[off + 4:off + 8], "little", signed=False)
    pixel_format = raw[off + 8]
    data_format = raw[off + 9]
    width = int.from_bytes(raw[off + 12:off + 14], "little", signed=False)
    height = int.from_bytes(raw[off + 14:off + 16], "little", signed=False)
    return (
        PvrMeta(
            gbix=gbix,
            pixel_format=pixel_format,
            data_format=data_format,
            width=width,
            height=height,
            pvrt_size_field=size,
            has_gbix=has_gbix,
        ),
        off + 16,
    )


def _decode_pixel(pixel_format: int, src: bytes, offset: int) -> Tuple[int, int, int, int]:
    b0 = src[offset]
    b1 = src[offset + 1]
    if pixel_format == PVR_PIXEL_ARGB4444:
        r = _expand_4bit(b1 & 0x0F)
        g = _expand_4bit((b0 >> 4) & 0x0F)
        b = _expand_4bit(b0 & 0x0F)
        a = _expand_4bit((b1 >> 4) & 0x0F)
        return (r, g, b, a)
    if pixel_format == PVR_PIXEL_ARGB1555:
        r5 = (b1 & 0x7C) >> 2
        g5 = ((b1 & 0x03) << 3) | ((b0 & 0xE0) >> 5)
        b5 = b0 & 0x1F
        a = 255 if (b1 & 0x80) else 0
        r = (r5 << 3) | (r5 >> 2)
        g = (g5 << 3) | (g5 >> 2)
        b = (b5 << 3) | (b5 >> 2)
        return (r, g, b, a)
    raise NotImplementedError(f"Unsupported PVR pixel format: 0x{pixel_format:02X}")


def _encode_pixel(pixel_format: int, rgba: Tuple[int, int, int, int]) -> bytes:
    r, g, b, a = rgba
    if pixel_format == PVR_PIXEL_ARGB4444:
        out0 = (g & 0xF0) | (b >> 4)
        out1 = (a & 0xF0) | (r >> 4)
        return bytes((out0, out1))
    if pixel_format == PVR_PIXEL_ARGB1555:
        out1 = (a & 0x80) | ((r & 0xF8) >> 1) | (g >> 6)
        out0 = ((g & 0xF8) << 2) & 0xE0 | ((b & 0xF8) >> 3)
        return bytes((out0, out1))
    raise NotImplementedError(f"Unsupported PVR pixel format: 0x{pixel_format:02X}")


def _twiddle_value(i: int) -> int:
    out = 0
    j = 0
    k = 1
    while k <= i:
        out |= (i & k) << j
        j += 1
        k <<= 1
    return out


def _twiddled_index(x: int, y: int) -> int:
    return (_twiddle_value(x) << 1) | _twiddle_value(y)


def decode_pvr_to_image(raw: bytes) -> Tuple[Image.Image, PvrMeta]:
    meta, data_off = _parse_header(raw)
    payload = raw[data_off:]
    image = Image.new("RGBA", (meta.width, meta.height))
    pixels = image.load()

    if meta.data_format == PVR_DATA_RECTANGLE:
        src = 0
        for y in range(meta.height):
            for x in range(meta.width):
                pixels[x, y] = _decode_pixel(meta.pixel_format, payload, src)
                src += 2
        return image, meta

    if meta.data_format == PVR_DATA_SQUARE_TWIDDLED:
        if meta.width != meta.height:
            raise NotImplementedError("Square twiddled texture is not square")
        for y in range(meta.height):
            for x in range(meta.width):
                src = _twiddled_index(x, y) * 2
                pixels[x, y] = _decode_pixel(meta.pixel_format, payload, src)
        return image, meta

    raise NotImplementedError(
        f"Unsupported PVR data format: pixel=0x{meta.pixel_format:02X}, data=0x{meta.data_format:02X}"
    )


def encode_image_to_pvr(image: Image.Image, meta: PvrMeta) -> bytes:
    img = image.convert("RGBA")
    if img.size != (meta.width, meta.height):
        raise ValueError(
            f"PNG size {img.size[0]}x{img.size[1]} does not match original PVR size {meta.width}x{meta.height}"
        )
    px = img.load()
    payload = bytearray(meta.width * meta.height * 2)

    if meta.data_format == PVR_DATA_RECTANGLE:
        dst = 0
        for y in range(meta.height):
            for x in range(meta.width):
                payload[dst:dst + 2] = _encode_pixel(meta.pixel_format, px[x, y])
                dst += 2
    elif meta.data_format == PVR_DATA_SQUARE_TWIDDLED:
        if meta.width != meta.height:
            raise NotImplementedError("Square twiddled texture is not square")
        for y in range(meta.height):
            for x in range(meta.width):
                dst = _twiddled_index(x, y) * 2
                payload[dst:dst + 2] = _encode_pixel(meta.pixel_format, px[x, y])
    else:
        raise NotImplementedError(
            f"Unsupported PVR data format: pixel=0x{meta.pixel_format:02X}, data=0x{meta.data_format:02X}"
        )

    result = bytearray()
    if meta.has_gbix:
        result.extend(MAGIC_GBIX)
        result.extend((8).to_bytes(4, "little", signed=False))
        result.extend(meta.gbix.to_bytes(4, "little", signed=False))
        result.extend((0x20202020).to_bytes(4, "little", signed=False))
    result.extend(MAGIC_PVRT)
    result.extend((len(payload) + 8).to_bytes(4, "little", signed=False))
    result.append(meta.pixel_format)
    result.append(meta.data_format)
    result.extend(b"\x00\x00")
    result.extend(meta.width.to_bytes(2, "little", signed=False))
    result.extend(meta.height.to_bytes(2, "little", signed=False))
    result.extend(payload)
    return bytes(result)


def save_pvr_as_png(pvr_path: Path, png_path: Path) -> PvrMeta:
    image, meta = decode_pvr_to_image(pvr_path.read_bytes())
    image.save(png_path)
    return meta


def save_png_as_pvr(png_path: Path, pvr_path: Path, meta: PvrMeta) -> None:
    image = Image.open(png_path)
    data = encode_image_to_pvr(image, meta)
    pvr_path.write_bytes(data)
