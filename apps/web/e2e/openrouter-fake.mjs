/**
 * Minimal fake of OpenRouter's chat completions endpoint for E2E (Phase 3g). The API under test
 * points OPENROUTER_BASE_URL here with AI_VISION_ENABLED=true, so document reading runs end to end
 * without a real model. It refuses requests that lack the privacy settings the API must send
 * (zero data retention, no data collection, a price cap) or that carry no image.
 */
import { createServer } from "node:http";

export const E2E_OPENROUTER_KEY = "e2e-openrouter-key";
export const E2E_TRANSCRIPTION = "Price list\nComprehensive eye exam | 25,000\nContact lens fitting | 15,000";
const port = Number(process.env.E2E_OPENROUTER_PORT ?? 4182);

const send = (res, status, body) => {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
};

createServer((req, res) => {
  if (req.method === "GET" && req.url === "/health") return send(res, 200, { ok: true });
  if (req.headers.authorization !== `Bearer ${E2E_OPENROUTER_KEY}`) return send(res, 401, { error: { message: "no auth" } });
  if (req.method !== "POST" || req.url !== "/chat/completions") return send(res, 404, { error: { message: "not found" } });
  let raw = "";
  req.on("data", (chunk) => { raw += chunk; });
  req.on("end", () => {
    let body;
    try { body = JSON.parse(raw); } catch { return send(res, 400, { error: { message: "bad json" } }); }
    const provider = body.provider ?? {};
    const parts = body.messages?.[1]?.content;
    const hasImage = Array.isArray(parts)
      && parts.some((p) => p.type === "image_url" && String(p.image_url?.url).startsWith("data:image/jpeg;base64,"));
    if (provider.zdr !== true || provider.data_collection !== "deny" || !provider.max_price || !hasImage) {
      return send(res, 400, { error: { message: "request rejected by the fake" } });
    }
    send(res, 200, {
      model: body.models?.[0] ?? "fake/vision",
      choices: [{ message: { content: E2E_TRANSCRIPTION } }],
      usage: { prompt_tokens: 900, completion_tokens: 30, cost: 0.0001 },
    });
  });
}).listen(port, "127.0.0.1");
