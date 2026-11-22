/**
 * `npm run demo:site` — a sample clinic website for LOCAL demonstrations, at
 * http://lumen-eye-clinic.localhost:4180 (browsers send *.localhost to this computer). It embeds
 * the real Engage chat widget exactly as a clinic would, with the demo clinic's public widget key.
 * Run `npm run demo:setup` first. Stop with Ctrl+C.
 */
import { createServer } from "node:http";
import { DEMO_HOST, DEMO_SITE_PORT, demoClinic, localStack, withDb } from "./demo-local.mjs";

const API = process.env.ENGAGE_API_URL ?? "http://127.0.0.1:8073";
const stack = localStack();
const clinic = await withDb(stack, demoClinic);
if (!clinic) {
  console.error("\nNo demo clinic yet. Run `npm run demo:setup` first.\n");
  process.exit(1);
}
const page = (key) => `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lumen Eye Clinic — sample clinic website</title>
<style>
  body { margin:0; font:17px/1.6 Georgia, "Times New Roman", serif; color:#2b2b2b; background:#fbfaf7; }
  header { background:#3b2f63; color:#fff; padding:18px 6vw; display:flex; justify-content:space-between; align-items:center; }
  header strong { font-size:22px; letter-spacing:.02em; } header nav a { color:#e9e4ff; margin-left:20px; text-decoration:none; font-size:15px; }
  .hero { padding:72px 6vw 56px; background:linear-gradient(180deg,#efeaff,#fbfaf7); }
  .hero h1 { font-size:44px; margin:0 0 12px; color:#3b2f63; } .hero p { max-width:620px; }
  main { padding:24px 6vw 120px; display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:24px; }
  .card { background:#fff; border:1px solid #e6e1f5; border-radius:10px; padding:20px; }
  .card h2 { font-size:20px; margin:0 0 8px; color:#3b2f63; }
  .note { position:fixed; left:16px; bottom:16px; background:#fff8e1; border:1px solid #f0d9a8; border-radius:8px; padding:8px 12px; font:13px Arial, sans-serif; max-width:340px; }
</style></head>
<body>
<header><strong>Lumen Eye Clinic</strong><nav><a href="#">Services</a><a href="#">Our team</a><a href="#">Contact</a></nav></header>
<section class="hero"><h1>Caring for your eyes, every day.</h1>
<p>A sample clinic website. The chat button at the bottom right is the real ZUVOORA Engage assistant, added to this site with one line of code.</p></section>
<main>
  <div class="card"><h2>Eye examinations</h2><p>Comprehensive checks of your vision and eye health.</p></div>
  <div class="card"><h2>Contact lenses</h2><p>Fittings, trial lenses and aftercare.</p></div>
  <div class="card"><h2>Children's eye care</h2><p>Friendly eye tests for children aged 4 and over.</p></div>
</main>
<p class="note">Demo website on this computer only (sample data, not a real clinic).</p>
<script src="${API}/widget/v1/loader.js" data-engage-key="${key}" async></script>
</body></html>`;

async function handle(req, res) {
  const host = (req.headers.host ?? "").replace(/:\d+$/, "");
  if (host !== DEMO_HOST) {
    res.writeHead(302, { Location: `http://${DEMO_HOST}:${DEMO_SITE_PORT}/` }).end();
    return;
  }
  if ((req.url ?? "/") !== "/") {
    res.writeHead(404).end("not found");
    return;
  }
  // Looked up on every visit, so re-running demo:setup never leaves a stale key here.
  const current = await withDb(stack, demoClinic).catch(() => null);
  if (!current || !/^[0-9a-f]{32}$/.test(current.public_key)) {
    res.writeHead(503, { "Content-Type": "text/plain; charset=utf-8" }).end("No demo clinic. Run: npm run demo:setup");
    return;
  }
  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
  res.end(page(current.public_key));
}

// Loopback only (this computer), on both IPv4 and IPv6: browsers may resolve *.localhost to either.
createServer(handle).listen(DEMO_SITE_PORT, "127.0.0.1", () => {
  console.log(`\nSample clinic website: http://${DEMO_HOST}:${DEMO_SITE_PORT}`);
  console.log(`Clinic: ${clinic.display_name} - chat widget ${clinic.enabled ? "on" : "OFF (turn it on in the dashboard)"}`);
  console.log("Press Ctrl+C to stop.\n");
});
createServer(handle).listen(DEMO_SITE_PORT, "::1").on("error", () => { /* no IPv6 loopback: IPv4 is enough */ });
