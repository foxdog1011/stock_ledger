import type { NextRequest } from "next/server";

const API_URL = process.env.API_URL || "http://api:8000";

async function handler(req: NextRequest, ctx: { params: { path: string[] } }) {
  const path = (ctx.params.path || []).join("/");
  const url = `${API_URL}/api/${path}${req.nextUrl.search}`;

  const headers = new Headers(req.headers);
  headers.delete("host");

  const method = req.method.toUpperCase();
  const body =
    method === "GET" || method === "HEAD" ? undefined : await req.arrayBuffer();

  const upstream = await fetch(url, {
    method,
    headers,
    body,
    cache: "no-store",
  });

  const buf = await upstream.arrayBuffer();
  const outHeaders = new Headers(upstream.headers);
  outHeaders.delete("content-encoding");
  outHeaders.delete("content-length");

  return new Response(buf, { status: upstream.status, headers: outHeaders });
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const DELETE = handler;
export const PATCH = handler;