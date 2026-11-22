/**
 * Minimal fake of the Cal.com API v2 for E2E (the API under test points CALCOM_API_URL here).
 * Accepts only the test key below; everything else is 401, as Cal.com does for a bad key.
 */
import { createServer } from "node:http";

export const E2E_CALCOM_KEY = "cal_e2e_test_key_0000000001";
const port = Number(process.env.E2E_CALCOM_PORT ?? 4181);

const send = (res, status, body) => {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
};

createServer((req, res) => {
  const url = new URL(req.url ?? "/", "http://localhost");
  if (url.pathname === "/health") return send(res, 200, { ok: true });
  if (req.headers.authorization !== `Bearer ${E2E_CALCOM_KEY}`) {
    return send(res, 401, { status: "error", error: { message: "Invalid API key" } });
  }
  if (req.method === "GET" && url.pathname === "/v2/me") {
    return send(res, 200, { status: "success", data: {
      id: 1, username: "e2e-clinic", email: "e2e@example.com", timeZone: "Africa/Lagos" } });
  }
  if (req.method === "GET" && url.pathname === "/v2/event-types") {
    if (req.headers["cal-api-version"] !== "2026-06-12") return send(res, 400, { status: "error" });
    return send(res, 200, { status: "success", data: [
      { id: 501, title: "Eye exam", lengthInMinutes: 30, hidden: false, confirmationPolicy: { disabled: true } },
      { id: 502, title: "Lens fitting", lengthInMinutes: 45, hidden: false, confirmationPolicy: { type: "always" } },
    ] });
  }
  return send(res, 404, { status: "error" });
}).listen(port, "127.0.0.1");
