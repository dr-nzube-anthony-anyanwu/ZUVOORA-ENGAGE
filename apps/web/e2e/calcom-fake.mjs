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
  if (req.method === "GET" && url.pathname === "/v2/slots") {
    if (req.headers["cal-api-version"] !== "2024-09-04") return send(res, 400, { status: "error" });
    const from = new Date(url.searchParams.get("start"));
    const to = new Date(url.searchParams.get("end"));
    const data = {};
    for (const start of offeredTimes()) {
      if (start < from || start > to || booked.has(start.toISOString())) continue;
      const day = start.toISOString().slice(0, 10);
      const end = new Date(start.getTime() + 30 * 60_000);
      (data[day] ??= []).push({ start: start.toISOString(), end: end.toISOString() });
    }
    return send(res, 200, { status: "success", data });
  }
  if (req.method === "POST" && url.pathname === "/v2/bookings") {
    if (req.headers["cal-api-version"] !== "2026-02-25") return send(res, 400, { status: "error" });
    let raw = "";
    req.on("data", (chunk) => { raw += chunk; });
    req.on("end", () => {
      const body = JSON.parse(raw || "{}");
      const start = new Date(body.start).toISOString();
      if (booked.has(start)) return send(res, 400, { status: "error", error: { message: "Slot taken" } });
      booked.add(start);
      const end = new Date(new Date(start).getTime() + 30 * 60_000).toISOString();
      return send(res, 201, { status: "success", data: {
        uid: `e2e${booked.size}`, status: "accepted", start, end, metadata: body.metadata ?? {} } });
    });
    return undefined;
  }
  return send(res, 404, { status: "error" });
}).listen(port, "127.0.0.1");

const booked = new Set();

/** 09:00 and 10:00 UTC on each of the next three days. */
function offeredTimes() {
  const base = new Date();
  base.setUTCHours(0, 0, 0, 0);
  const times = [];
  for (let day = 1; day <= 3; day += 1) {
    for (const hour of [9, 10]) times.push(new Date(base.getTime() + (day * 24 + hour) * 3_600_000));
  }
  return times;
}
