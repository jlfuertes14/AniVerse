"""Proxy media requests for HLS playback."""
from urllib.parse import urlencode, urljoin
import re

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

router = APIRouter(prefix="/proxy", tags=["proxy"])


def _is_playlist(url: str, content_type: str) -> bool:
    lower_type = content_type.lower()
    return (
        ".m3u8" in url.lower()
        or "mpegurl" in lower_type
        or "application/x-mpegurl" in lower_type
    )


def _to_absolute_url(raw: str, base_url: str) -> str:
    trimmed = raw.strip()
    if not trimmed:
        return raw
    if trimmed.startswith("data:") or trimmed.startswith("blob:"):
        return raw

    try:
        return urljoin(base_url, trimmed)
    except Exception:
        return raw


def _build_proxy_url(request: Request, target_url: str, referer: str) -> str:
    params = {"url": target_url}
    if referer:
        params["referer"] = referer
    query = urlencode(params)
    base = str(request.base_url).rstrip("/")
    path = request.url.path
    return f"{base}{path}?{query}"


def _rewrite_playlist(content: str, playlist_url: str, referer: str, request: Request) -> str:
    def rewrite_uri(raw: str) -> str:
        absolute = _to_absolute_url(raw, playlist_url)
        return _build_proxy_url(request, absolute, referer)

    lines = []
    for line in content.split("\n"):
        trimmed = line.strip()
        if not trimmed:
            lines.append(line)
            continue

        if trimmed.startswith("#"):
            updated = re.sub(r'URI="([^"]+)"', lambda m: f'URI="{rewrite_uri(m.group(1))}"', line)
            updated = re.sub(r"URI='([^']+)'", lambda m: f"URI='{rewrite_uri(m.group(1))}'", updated)
            lines.append(updated)
            continue

        lines.append(rewrite_uri(trimmed))

    return "\n".join(lines)


def _upstream_headers(target_url: str, referer: str, range_header: str | None) -> dict:
    origin = target_url
    if referer:
        try:
            parsed = httpx.URL(referer)
            origin = f"{parsed.scheme}://{parsed.host}"
        except Exception:
            origin = target_url

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "Referer": referer or target_url,
        "Origin": origin,
        "DNT": "1",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "video",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
    }
    if range_header:
        headers["Range"] = range_header
    return headers


def _cors_headers() -> dict:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "Range, Content-Type",
        "Access-Control-Expose-Headers": "Content-Range, Content-Length, Accept-Ranges",
    }


async def _proxy_request(request: Request, method: str):
    raw_url = request.query_params.get("url")
    referer = request.query_params.get("referer", "")

    if not raw_url:
        return JSONResponse({"error": "url param required"}, status_code=400, headers=_cors_headers())

    try:
        target = httpx.URL(raw_url)
    except Exception:
        return JSONResponse({"error": "Invalid URL"}, status_code=400, headers=_cors_headers())

    if target.scheme not in {"http", "https"}:
        return JSONResponse({"error": "Only http/https allowed"}, status_code=400, headers=_cors_headers())

    headers = _upstream_headers(str(target), referer, request.headers.get("range"))

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        async with client.stream(method, str(target), headers=headers) as upstream:
            if upstream.status_code not in {200, 206}:
                return Response(status_code=upstream.status_code, headers=_cors_headers())

            content_type = upstream.headers.get("content-type", "")
            if _is_playlist(str(target), content_type):
                playlist_text = await upstream.aread()
                rewritten = _rewrite_playlist(playlist_text.decode("utf-8", errors="ignore"), str(target), referer, request)
                response_headers = _cors_headers()
                response_headers.update({
                    "content-type": "application/vnd.apple.mpegurl",
                })
                return Response(content=rewritten, status_code=200, headers=response_headers)

            response_headers = _cors_headers()
            for header_name in [
                "content-type",
                "content-length",
                "content-range",
                "accept-ranges",
                "cache-control",
                "etag",
            ]:
                header_value = upstream.headers.get(header_name)
                if header_value:
                    response_headers[header_name] = header_value

            return StreamingResponse(
                upstream.aiter_bytes(),
                status_code=upstream.status_code,
                headers=response_headers,
            )


@router.get("")
async def proxy_get(request: Request):
    return await _proxy_request(request, "GET")


@router.head("")
async def proxy_head(request: Request):
    return await _proxy_request(request, "HEAD")


@router.options("")
async def proxy_options():
    return Response(status_code=204, headers=_cors_headers())
