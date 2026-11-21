/**
 * Minimal "clinic website" for E2E: serves a page that embeds the real Engage loader.
 * Hostnames (clinic-site / evil-site .engage-e2e.test) are mapped to 127.0.0.1 by Chromium.
 */
import { createServer } from "node:http";

const port = Number(process.env.E2E_SITE_PORT ?? 4180);
const api = process.env.E2E_API_ORIGIN ?? "http://127.0.0.1:8073";

createServer((req, res) => {
  const url = new URL(req.url ?? "/", "http://localhost");
  const key = url.searchParams.get("key") ?? "";
  if (url.pathname !== "/" || !/^[0-9a-f]{32}$/.test(key)) {
    res.writeHead(404).end("not found");
    return;
  }
  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
  res.end(`<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Clinic website</title></head>
<body><h1>Clinic website</h1>
<script src="${api}/widget/v1/loader.js" data-engage-key="${key}" async></script></body></html>`);
}).listen(port, "127.0.0.1");
