from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
from fastapi import APIRouter, Response

from app.config import get_settings

router = APIRouter()

# Tiny 256x256 gray PNG fallback if upstream is unreachable.
EMPTY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000001000000010008060000005c72a866"
    "0000000a4944415478daedc1010100000080b0fe3b16000100d5d8d8d800000000"
    "49454e44ae426082"
)


@router.get("/tiles/{z}/{x}/{y}.png")
async def tiles(z: int, x: int, y: int):
    settings = get_settings()
    if z < 10 or z > 16:
        return Response(content=_blank(), media_type="image/png")
    cache_dir = Path(settings.tile_cache_dir) / str(z) / str(x)
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / f"{y}.png"
    if dest.exists() and dest.stat().st_size > 100:
        return Response(content=dest.read_bytes(), media_type="image/png", headers={"Cache-Control": "public, max-age=2592000"})
    url = f"{settings.tile_upstream}/{z}/{x}/{y}.png"
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            r = await client.get(
                url,
                headers={"User-Agent": "KinTraficLive/1.0 (https://127.0.0.1:43147; tile cache for Kinshasa PWA)"},
            )
            if r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n":
                dest.write_bytes(r.content)
                return Response(content=r.content, media_type="image/png", headers={"Cache-Control": "public, max-age=2592000"})
    except Exception:
        pass
    return Response(content=_blank(), media_type="image/png")


def _blank() -> bytes:
    # 256x256 light PNG generated once via hashlib cache key; return constant fallback.
    p = Path(get_settings().tile_cache_dir) / "_blank.png"
    if p.exists():
        return p.read_bytes()
    p.parent.mkdir(parents=True, exist_ok=True)
    # Minimal valid 1x1 PNG stretched by leaflet is ugly; use a small generated gray tile.
    try:
        from PIL import Image
        import io

        im = Image.new("RGB", (256, 256), (232, 228, 216))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        data = buf.getvalue()
        p.write_bytes(data)
        return data
    except Exception:
        return EMPTY_PNG
