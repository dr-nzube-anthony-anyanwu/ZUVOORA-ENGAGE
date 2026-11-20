/**
 * Minimal non-functional widget shell.
 * Phase 3 replaces this with an isolated, domain-validated chat experience.
 */
(() => {
  const script = document.currentScript as HTMLScriptElement | null;
  if (!script) return;
  const widgetId = script.dataset.widgetId;
  if (!widgetId || !/^[A-Za-z0-9_-]{8,128}$/.test(widgetId)) {
    console.warn("[ZUVOORA Engage] Missing or invalid data-widget-id.");
    return;
  }
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Chat with our clinic";
  button.setAttribute("aria-label", "Open clinic assistant");
  button.style.cssText = "position:fixed;right:20px;bottom:20px;z-index:2147483000;border:0;border-radius:999px;padding:14px 18px;background:#15324b;color:#fff;font:600 14px Arial;cursor:pointer";
  button.addEventListener("click", () => window.alert("The Engage assistant will be enabled in Phase 3."));
  document.body.appendChild(button);
})();
