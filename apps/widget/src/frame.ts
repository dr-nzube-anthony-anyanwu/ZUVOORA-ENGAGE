/**
 * Chat UI inside the Engage iframe (served by the Engage API, same origin as the public API).
 * All text is inserted with textContent; nothing is ever parsed as HTML. The conversation token
 * is kept in memory only.
 */
(() => {
  type Config = { ticket: string; clinic: string; greeting: string; booking?: boolean };
  type ApiError = { error?: { code?: string; message?: string; details?: { msg: string }[] } };

  const root = document.getElementById("engage-app");
  if (!root) return;
  const app: HTMLElement = root;
  const params = new URLSearchParams(window.location.search);
  // The embedding page's origin (the loader sets referrerPolicy "strict-origin" on the iframe).
  const parentOrigin = (() => {
    try {
      return document.referrer ? new URL(document.referrer).origin : null;
    } catch {
      return null;
    }
  })();
  let config: Config = { ticket: "", clinic: "", greeting: "" };
  let token: string | null = null;
  let busy = false;

  function el<K extends keyof HTMLElementTagNameMap>(
    tag: K, className?: string, text?: string,
  ): HTMLElementTagNameMap[K] {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // ----- layout ---------------------------------------------------------------------------------
  const header = el("header", "head");
  const title = el("strong", "title", "Clinic assistant");
  header.append(title);
  const closeBtn = el("button", "close", "×");
  closeBtn.type = "button";
  closeBtn.setAttribute("aria-label", "Close chat");
  closeBtn.addEventListener("click", () => {
    // Only ever tell the embedding page itself (never a wildcard target origin).
    if (parentOrigin) window.parent.postMessage({ type: "engage:close" }, parentOrigin);
  });
  header.append(closeBtn);

  const log = el("div", "log");
  log.setAttribute("role", "log");
  log.setAttribute("aria-live", "polite");

  const form = el("form", "composer");
  const input = el("textarea");
  input.name = "text";
  input.rows = 2;
  input.maxLength = 1000;
  input.required = true;
  input.placeholder = "Type your question…";
  input.setAttribute("aria-label", "Your message");
  const send = el("button", "send", "Send");
  send.type = "submit";
  form.append(input, send);

  const handover = buildHandoverForm();
  // A person is always one click away, not only when the assistant cannot answer.
  const askTeam = el("button", "ask-team", "Contact the clinic team");
  askTeam.type = "button";
  askTeam.addEventListener("click", () => showHandover());
  const booking = el("section", "booking");
  booking.hidden = true;
  booking.setAttribute("aria-label", "Book an appointment");
  const bookOpen = el("button", "ask-team", "Book an appointment");
  bookOpen.type = "button";
  bookOpen.addEventListener("click", () => void openBooking());
  const actions = el("div", "actions");
  actions.append(bookOpen, askTeam);
  const footer = el("p", "foot",
    "Automated assistant for clinic information — not medical advice. In an emergency, go to the nearest emergency department.");

  void start();

  async function start(): Promise<void> {
    try {
      config = await post<Config>("/api/v1/public/widget/frame-config", {
        key: params.get("key") ?? "",
        host: params.get("host") ?? "",
      });
    } catch {
      app.append(el("p", "unavailable", "This chat is not available on this website."));
      return;
    }
    title.textContent = config.clinic;
    document.title = `Chat with ${config.clinic}`;
    bookOpen.hidden = !config.booking;
    app.append(header, log, handover, booking, form, actions, footer);
    addMessage("assistant", config.greeting);
  }

  // ----- behaviour ------------------------------------------------------------------------------
  function addMessage(role: "visitor" | "assistant" | "system", text: string): void {
    const bubble = el("div", `msg ${role}`, text);
    log.append(bubble);
    log.scrollTop = log.scrollHeight;
  }

  async function post<T>(path: string, body: unknown): Promise<T> {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      credentials: "omit",
    });
    const data = (await response.json().catch(() => ({}))) as T & ApiError;
    if (!response.ok) {
      const detail = data.error?.details?.[0]?.msg;
      throw Object.assign(new Error(detail ?? data.error?.message ?? "Something went wrong. Please try again."),
                          { code: data.error?.code ?? "" });
    }
    return data;
  }

  async function ensureSession(): Promise<string> {
    if (token) return token;
    const session = await post<{ token: string }>("/api/v1/public/widget/session",
                                                  { ticket: config.ticket });
    token = session.token;
    return token;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text || busy) return;
    busy = true;
    send.disabled = true;
    addMessage("visitor", text);
    input.value = "";
    try {
      const result = await post<{ reply: { content: string; offer_handover: boolean } }>(
        "/api/v1/public/widget/messages", { token: await ensureSession(), text });
      addMessage("assistant", result.reply.content);
      if (result.reply.offer_handover) showHandover(false);
    } catch (error) {
      addMessage("system", (error as Error).message);
    } finally {
      busy = false;
      send.disabled = false;
      input.focus();
    }
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  // ----- booking (Phase 4c): type -> time -> details -> result --------------------------------
  type BookingType = { id: string; name: string; duration_minutes: number; requires_confirmation: boolean };
  const visitorZone = (() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    } catch {
      return "UTC";
    }
  })();

  function bookingStep(heading: string, ...children: HTMLElement[]): void {
    const close = el("button", "link", "Cancel");
    close.type = "button";
    close.addEventListener("click", () => {
      booking.hidden = true;
      bookOpen.hidden = false;
    });
    const top = el("div", "booking-head");
    top.append(el("p", "handover-title", heading), close);
    booking.replaceChildren(top, ...children);
    booking.hidden = false;
    bookOpen.hidden = true;
    (booking.querySelector("button.choice, input") as HTMLElement | null)?.focus();
  }

  async function openBooking(): Promise<void> {
    bookingStep("Book an appointment", el("p", "hint", "Loading…"));
    try {
      const options = await post<{ available: boolean; types: BookingType[] }>(
        "/api/v1/public/widget/booking/options", { token: await ensureSession() });
      if (!options.available) {
        bookingStep("Book an appointment", el("p", "hint", "Online booking is not available right now."));
        return;
      }
      const list = el("div", "choices");
      for (const kind of options.types) {
        const choice = el("button", "choice", `${kind.name} · ${kind.duration_minutes} min`);
        choice.type = "button";
        choice.addEventListener("click", () => void chooseTime(kind));
        list.append(choice);
      }
      bookingStep("What would you like to book?", list);
    } catch (error) {
      bookingStep("Book an appointment", el("p", "hint", (error as Error).message));
    }
  }

  async function chooseTime(kind: BookingType, notice?: string): Promise<void> {
    bookingStep(kind.name, el("p", "hint", "Finding available times…"));
    try {
      const result = await post<{ slots: string[] }>("/api/v1/public/widget/booking/slots",
        { token: await ensureSession(), appointment_type_id: kind.id });
      const days = new Map<string, Date[]>();
      const dayLabel = new Intl.DateTimeFormat(undefined, { weekday: "long", day: "numeric", month: "long", timeZone: visitorZone });
      for (const iso of result.slots) {
        const moment = new Date(iso);
        const label = dayLabel.format(moment);
        days.set(label, [...(days.get(label) ?? []), moment]);
      }
      const children: HTMLElement[] = [];
      if (notice) children.push(el("p", "notice", notice));
      if (days.size === 0) {
        children.push(el("p", "hint", "No times are available in the next two weeks. You can ask the clinic team to contact you."));
      }
      const time = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", timeZone: visitorZone });
      for (const [label, moments] of [...days].slice(0, 7)) {
        const group = el("div", "day");
        group.append(el("p", "day-label", label));
        const row = el("div", "choices times");
        for (const moment of moments) {
          const choice = el("button", "choice", time.format(moment));
          choice.type = "button";
          choice.setAttribute("aria-label", `${label}, ${time.format(moment)}`);
          choice.addEventListener("click", () => details(kind, moment, `${label}, ${time.format(moment)}`));
          row.append(choice);
        }
        group.append(row);
        children.push(group);
      }
      children.push(el("p", "hint", `Times are shown in your time zone (${visitorZone}).`));
      bookingStep(`${kind.name}: choose a time`, ...children);
    } catch (error) {
      bookingStep(kind.name, el("p", "hint", (error as Error).message));
    }
  }

  function details(kind: BookingType, moment: Date, label: string): void {
    const box = el("form", "booking-form");
    const fields: [string, string, string, boolean, number][] = [
      ["name", "Full name", "text", true, 120],
      ["email", "Email", "email", true, 254],
      ["phone", "Phone (optional)", "tel", false, 30],
    ];
    for (const [name, text, type, required, max] of fields) {
      const wrap = el("label", "field", text);
      const field = el("input");
      field.name = name;
      field.type = type;
      field.required = required;
      field.maxLength = max;
      field.setAttribute("autocomplete", name === "phone" ? "tel" : name);
      wrap.append(field);
      box.append(wrap);
    }
    const consentWrap = el("label", "consent");
    const consent = el("input");
    consent.type = "checkbox";
    consent.required = true;
    consentWrap.append(consent, el("span", undefined,
      ` I agree that ${config.clinic} may use these details to manage this appointment.`));
    const submit = el("button", "send", kind.requires_confirmation ? "Request this time" : "Book this time");
    submit.type = "submit";
    box.append(consentWrap, el("p", "hint", "Please don't include medical details."), submit);
    box.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(box);
      const value = (k: string) => String(data.get(k) ?? "").trim();
      submit.disabled = true;
      submit.textContent = "Booking…";
      try {
        const result = await post<{ status: string; message: string }>("/api/v1/public/widget/booking", {
          token: await ensureSession(), appointment_type_id: kind.id, start: moment.toISOString(),
          name: value("name"), email: value("email"), phone: value("phone") || null,
          time_zone: visitorZone, consent: consent.checked,
        });
        booking.hidden = true;
        bookOpen.hidden = false;
        addMessage("system", result.message);
      } catch (error) {
        const failure = error as Error & { code?: string };
        if (failure.code === "slot_unavailable") {
          void chooseTime(kind, failure.message);
          return;
        }
        submit.disabled = false;
        submit.textContent = kind.requires_confirmation ? "Request this time" : "Book this time";
        addMessage("system", failure.message);
      }
    });
    bookingStep(`${kind.name}: ${label}`, box);
  }

  function showHandover(focus = true): void {
    handover.hidden = false;
    askTeam.hidden = true;
    if (focus) handover.querySelector("input")?.focus();
  }

  function buildHandoverForm(): HTMLFormElement {
    const box = el("form", "handover");
    box.hidden = true;
    box.append(el("p", "handover-title", "Ask the clinic team to contact you"));
    const fields: [string, string, string][] = [
      ["name", "Name (optional)", "text"],
      ["phone", "Phone", "tel"],
      ["email", "Email", "email"],
    ];
    for (const [name, label, type] of fields) {
      const wrap = el("label", "field", label);
      const field = el("input");
      field.name = name;
      field.type = type;
      field.maxLength = name === "email" ? 254 : name === "phone" ? 30 : 120;
      wrap.append(field);
      box.append(wrap);
    }
    const consentWrap = el("label", "consent");
    const consent = el("input");
    consent.type = "checkbox";
    consent.name = "consent";
    consent.required = true;
    consentWrap.append(consent, el("span", undefined,
      " I agree that the clinic may use these details to contact me about my enquiry."));
    box.append(consentWrap, el("p", "hint", "Please don't include medical details here."));
    const submit = el("button", "send", "Send my details");
    submit.type = "submit";
    box.append(submit);

    box.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(box);
      const value = (k: string) => String(data.get(k) ?? "").trim() || null;
      if (!value("phone") && !value("email")) {
        addMessage("system", "Please give a phone number or an email address.");
        return;
      }
      submit.disabled = true;
      try {
        const result = await post<{ message: string }>("/api/v1/public/widget/handover", {
          token: await ensureSession(), name: value("name"), phone: value("phone"),
          email: value("email"), consent: consent.checked,
        });
        box.hidden = true;
        addMessage("assistant", result.message);
      } catch (error) {
        addMessage("system", (error as Error).message);
        submit.disabled = false;
      }
    });
    return box;
  }
})();
