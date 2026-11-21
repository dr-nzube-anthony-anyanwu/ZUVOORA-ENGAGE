/**
 * ZUVOORA Engage embed script. A clinic adds:
 *   <script src="https://API_HOST/widget/v1/loader.js" data-engage-key="PUBLIC_KEY" async></script>
 *
 * It only adds a button and an isolated iframe served by the Engage API. Nothing from the host
 * page is read except its hostname; nothing is written to the host page's storage or cookies.
 * The iframe is refused by the browser unless the page is on one of the clinic's verified
 * domains (frame-ancestors).
 */
(() => {
  const script = document.currentScript as HTMLScriptElement | null;
  if (!script || (window as unknown as { __engageLoaded?: boolean }).__engageLoaded) return;
  (window as unknown as { __engageLoaded?: boolean }).__engageLoaded = true;

  const key = script.dataset.engageKey ?? "";
  if (!/^[0-9a-f]{32}$/.test(key)) {
    console.warn("[ZUVOORA Engage] Missing or invalid data-engage-key.");
    return;
  }
  const apiOrigin = new URL(script.src).origin;
  const label = (script.dataset.label ?? "Chat with us").slice(0, 40);

  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.setAttribute("aria-haspopup", "dialog");
  button.setAttribute("aria-expanded", "false");
  button.style.cssText =
    "position:fixed;right:20px;bottom:20px;z-index:2147483000;border:0;border-radius:999px;" +
    "padding:14px 18px;background:#15324b;color:#fff;font:600 14px Arial,sans-serif;" +
    "cursor:pointer;box-shadow:0 6px 18px rgba(0,0,0,.2)";

  let frame: HTMLIFrameElement | null = null;

  function open(): void {
    if (!frame) {
      frame = document.createElement("iframe");
      const src = new URL("/widget/v1/frame", apiOrigin);
      src.searchParams.set("key", key);
      src.searchParams.set("host", window.location.hostname);
      frame.src = src.toString();
      frame.title = "Clinic chat assistant";
      // Scripts and forms inside the frame only; no top navigation, popups or downloads.
      frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-forms");
      frame.referrerPolicy = "strict-origin";
      frame.style.cssText =
        "position:fixed;right:20px;bottom:84px;z-index:2147483000;width:min(380px,calc(100vw - 40px));" +
        "height:min(560px,calc(100vh - 120px));border:1px solid #dce5e9;border-radius:16px;" +
        "background:#fff;box-shadow:0 12px 32px rgba(0,0,0,.18)";
      document.body.appendChild(frame);
    }
    frame.style.display = "block";
    button.setAttribute("aria-expanded", "true");
    frame.focus();
  }

  function close(): void {
    if (frame) frame.style.display = "none";
    button.setAttribute("aria-expanded", "false");
    button.focus();
  }

  button.addEventListener("click", () => {
    if (frame && frame.style.display !== "none") close();
    else open();
  });

  // Only the Engage frame itself may ask to be closed.
  window.addEventListener("message", (event: MessageEvent) => {
    if (event.origin !== apiOrigin || !frame || event.source !== frame.contentWindow) return;
    if (event.data && (event.data as { type?: string }).type === "engage:close") close();
  });

  document.body.appendChild(button);
})();
