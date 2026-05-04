import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

function isPlaylist(url: string, contentType: string) {
    const lowerType = contentType.toLowerCase();
    return (
        url.toLowerCase().includes(".m3u8") ||
        lowerType.includes("mpegurl") ||
        lowerType.includes("application/x-mpegurl")
    );
}

function toAbsoluteUrl(raw: string, baseUrl: string) {
    const trimmed = raw.trim();
    if (!trimmed) return raw;
    if (trimmed.startsWith("data:") || trimmed.startsWith("blob:")) return raw;

    try {
        return new URL(trimmed, baseUrl).toString();
    } catch {
        return raw;
    }
}

function buildProxyUrl(requestUrl: URL, targetUrl: string, referer: string) {
    const params = new URLSearchParams({ url: targetUrl });
    if (referer) {
        params.set("referer", referer);
    }
    return `${requestUrl.protocol}//${requestUrl.host}/api/proxy?${params.toString()}`;
}

function rewritePlaylist(content: string, playlistUrl: string, referer: string, requestUrl: URL) {
    return content
        .split("\n")
        .map((line) => {
            const trimmed = line.trim();
            if (!trimmed) return line;

            if (trimmed.startsWith("#")) {
                return line
                    .replace(/URI="([^"]+)"/g, (_match, uri) => {
                        const absolute = toAbsoluteUrl(uri, playlistUrl);
                        return `URI="${buildProxyUrl(requestUrl, absolute, referer)}"`;
                    })
                    .replace(/URI='([^']+)'/g, (_match, uri) => {
                        const absolute = toAbsoluteUrl(uri, playlistUrl);
                        return `URI='${buildProxyUrl(requestUrl, absolute, referer)}'`;
                    });
            }

            const absolute = toAbsoluteUrl(trimmed, playlistUrl);
            return buildProxyUrl(requestUrl, absolute, referer);
        })
        .join("\n");
}

function buildUpstreamHeaders(targetUrl: URL, referer: string, rangeHeader: string | null) {
    let origin = `${targetUrl.protocol}//${targetUrl.host}`;

    if (referer) {
        try {
            const refererUrl = new URL(referer);
            origin = `${refererUrl.protocol}//${refererUrl.host}`;
        } catch {
            // Ignore malformed referer and fall back to target origin.
        }
    }

    const headers: Record<string, string> = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        Accept: "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        Referer: referer || `${targetUrl.protocol}//${targetUrl.host}/`,
        Origin: origin,
        "DNT": "1",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "video",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
    };

    if (rangeHeader) {
        headers.Range = rangeHeader;
    }

    return headers;
}

function corsHeaders() {
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "Range, Content-Type",
        "Access-Control-Expose-Headers": "Content-Range, Content-Length, Accept-Ranges",
    };
}

async function proxyRequest(request: Request, method: "GET" | "HEAD") {
    const requestUrl = new URL(request.url);
    const rawUrl = requestUrl.searchParams.get("url");
    const referer = requestUrl.searchParams.get("referer") || "";

    if (!rawUrl) {
        return method === "HEAD"
            ? new NextResponse(null, { status: 400, headers: corsHeaders() })
            : NextResponse.json({ error: "url param required" }, { status: 400, headers: corsHeaders() });
    }

    let targetUrl: URL;
    try {
        targetUrl = new URL(rawUrl);
    } catch {
        return method === "HEAD"
            ? new NextResponse(null, { status: 400, headers: corsHeaders() })
            : NextResponse.json({ error: "Invalid URL" }, { status: 400, headers: corsHeaders() });
    }

    if (!["http:", "https:"].includes(targetUrl.protocol)) {
        return method === "HEAD"
            ? new NextResponse(null, { status: 400, headers: corsHeaders() })
            : NextResponse.json({ error: "Only http/https allowed" }, { status: 400, headers: corsHeaders() });
    }

    try {
        const upstream = await fetch(targetUrl.toString(), {
            method,
            headers: buildUpstreamHeaders(targetUrl, referer, request.headers.get("range")),
            redirect: "follow",
        });

        if (!upstream.ok && upstream.status !== 206) {
            return new NextResponse(null, { status: upstream.status, headers: corsHeaders() });
        }

        const headers = new Headers(corsHeaders());
        for (const headerName of ["content-type", "content-length", "content-range", "accept-ranges", "cache-control", "etag"]) {
            const value = upstream.headers.get(headerName);
            if (value) {
                headers.set(headerName, value);
            }
        }
        if (method === "HEAD") {
            return new NextResponse(null, {
                status: upstream.status,
                headers,
            });
        }

        const contentType = upstream.headers.get("content-type") || "";
        if (isPlaylist(targetUrl.toString(), contentType)) {
            const playlist = await upstream.text();
            const rewritten = rewritePlaylist(playlist, targetUrl.toString(), referer, requestUrl);

            headers.set("content-type", "application/vnd.apple.mpegurl");
            headers.delete("content-length");

            return new NextResponse(rewritten, {
                status: 200,
                headers,
            });
        }

        return new NextResponse(upstream.body, {
            status: upstream.status,
            headers,
        });
    } catch (error) {
        const message = error instanceof Error ? error.message : "Upstream fetch failed";
        return method === "HEAD"
            ? new NextResponse(null, { status: 502, headers: corsHeaders() })
            : NextResponse.json({ error: "Upstream fetch failed", detail: message }, { status: 502, headers: corsHeaders() });
    }
}

export async function GET(request: Request) {
    return proxyRequest(request, "GET");
}

export async function HEAD(request: Request) {
    return proxyRequest(request, "HEAD");
}

export async function OPTIONS() {
    return new NextResponse(null, {
        status: 204,
        headers: corsHeaders(),
    });
}
