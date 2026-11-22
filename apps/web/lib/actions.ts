"use server";

/**
 * Server Actions for the clinic dashboard. They run on the Next.js server and call the Engage
 * API with the signed-in user's session; the browser never sees the API or a token.
 *
 * Security: every argument (including values bound with .bind) can be altered by the client,
 * so ids are checked to be UUIDs, kinds/actions against fixed lists, and the API re-authorises
 * every call (tenant membership, role, RLS). Next.js rejects cross-origin action calls (CSRF).
 */
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { ApiRequestError, apiFetch, isUuid, tenantPath } from "@/lib/api";
import type { ActionState } from "@/lib/types";

const CONTENT_KINDS = ["branches", "services", "faqs"] as const;
type ContentKind = (typeof CONTENT_KINDS)[number];
const ITEM_ACTIONS = ["publish", "unpublish", "archive", "restore"] as const;
const DOCUMENT_ACTIONS = ["unpublish", "archive", "restore"] as const;
const ROLES = ["owner", "admin", "receptionist", "viewer"] as const;
const HANDOVER_STATUSES = ["new", "in_progress", "resolved"] as const;
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

class InvalidInput extends Error {}
/** Input problems whose message is safe and useful to show to the user. */
class UserInputError extends Error {}

function ids(...values: unknown[]): void {
  if (!values.every(isUuid)) throw new InvalidInput("invalid id");
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[]): T {
  if (typeof value !== "string" || !(allowed as readonly string[]).includes(value)) {
    throw new InvalidInput("invalid choice");
  }
  return value as T;
}

function revisionOf(value: unknown): number {
  const n = Number(value);
  if (!Number.isInteger(n) || n < 1) throw new InvalidInput("invalid revision");
  return n;
}

function text(form: FormData, name: string): string | null {
  const value = form.get(name);
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

/** Numbers are sent as numbers when well-formed; otherwise as text so the API reports why. */
function integer(form: FormData, name: string): number | string | null {
  const value = text(form, name);
  if (value === null) return null;
  return /^\d{1,6}$/.test(value) ? Number(value) : value;
}

function checked(form: FormData, name: string): boolean {
  return form.get(name) === "on";
}

function failure(error: unknown): ActionState {
  if (error instanceof ApiRequestError) {
    if (error.status === 401) redirect("/login");
    if (error.status === 404) return { error: "This item no longer exists or you no longer have access." };
    return { error: error.userMessage, details: error.details };
  }
  if (error instanceof UserInputError) return { error: error.message };
  if (error instanceof InvalidInput) return { error: "The request was not valid." };
  return { error: "Something went wrong. Please try again." };
}

function refresh(tenantId: string): void {
  revalidatePath(`/clinics/${tenantId}`, "layout");
}

// ----- content builders ------------------------------------------------------------------------
function profileContent(form: FormData) {
  return {
    about: text(form, "about"),
    public_phone: text(form, "public_phone"),
    public_email: text(form, "public_email"),
    website_url: text(form, "website_url"),
    emergency_guidance: text(form, "emergency_guidance"),
  };
}

function ranges(form: FormData, prefix: string, count: number) {
  const out: { open: string; close: string }[] = [];
  for (let i = 0; i < count; i += 1) {
    const open = text(form, `${prefix}_open_${i}`);
    const close = text(form, `${prefix}_close_${i}`);
    if (open || close) out.push({ open: open ?? "", close: close ?? "" });
  }
  return out;
}

function openingHours(form: FormData) {
  if (!checked(form, "hours_enabled")) return null;
  const weekly = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"].map((day) => {
    const closed = checked(form, `${day}_closed`);
    return { day, closed, ranges: closed ? [] : ranges(form, day, 3) };
  });
  const exceptions = form
    .getAll("ex_index")
    .map(String)
    .filter((i) => /^\d{1,2}$/.test(i))
    .flatMap((i) => {
      const date = text(form, `ex_${i}_date`);
      if (!date) return [];
      const closed = checked(form, `ex_${i}_closed`);
      return [{ date, closed, ranges: closed ? [] : ranges(form, `ex_${i}`, 1),
                note: text(form, `ex_${i}_note`) }];
    });
  return { weekly, exceptions };
}

function contentFor(kind: ContentKind, form: FormData) {
  switch (kind) {
    case "branches":
      return {
        name: text(form, "name") ?? "",
        address: text(form, "address"),
        city: text(form, "city"),
        phone: text(form, "phone"),
        email: text(form, "email"),
        timezone: text(form, "timezone") ?? "Africa/Lagos",
        opening_hours: openingHours(form),
        notes: text(form, "notes"),
      };
    case "services":
      return {
        name: text(form, "name") ?? "",
        category: text(form, "category"),
        description: text(form, "description"),
        duration_minutes: integer(form, "duration_minutes"),
        price_note: text(form, "price_note"),
      };
    case "faqs":
      return {
        question: text(form, "question") ?? "",
        answer: text(form, "answer") ?? "",
        category: text(form, "category"),
        sort_order: integer(form, "sort_order") ?? 0,
      };
  }
}

// ----- clinic profile --------------------------------------------------------------------------
export async function saveProfile(
  tenantId: string, revision: number, _prev: ActionState, form: FormData,
): Promise<ActionState> {
  try {
    ids(tenantId);
    await apiFetch(tenantPath(tenantId, "profile", "draft"), {
      method: "PATCH",
      json: { revision: revisionOf(revision), content: profileContent(form) },
    });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  return { ok: "Draft saved. Publish it to make it live." };
}

export async function profileAction(
  tenantId: string, action: string, revision: number, _prev: ActionState,
): Promise<ActionState> {
  try {
    ids(tenantId);
    const verb = oneOf(action, ["publish", "unpublish"] as const);
    await apiFetch(tenantPath(tenantId, "profile", verb), {
      method: "POST",
      json: verb === "publish" ? { revision: revisionOf(revision) } : undefined,
    });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  return { ok: action === "publish" ? "Published." : "Unpublished." };
}

// ----- branches, services, FAQs ----------------------------------------------------------------
export async function createContent(
  kind: string, tenantId: string, _prev: ActionState, form: FormData,
): Promise<ActionState> {
  let created: { id: string };
  let safeKind: ContentKind;
  try {
    ids(tenantId);
    safeKind = oneOf(kind, CONTENT_KINDS);
    created = await apiFetch<{ id: string }>(tenantPath(tenantId, safeKind), {
      method: "POST",
      json: { content: contentFor(safeKind, form) },
    });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  redirect(`/clinics/${tenantId}/${safeKind}/${created.id}?saved=1`);
}

export async function saveContent(
  kind: string, tenantId: string, itemId: string, revision: number,
  _prev: ActionState, form: FormData,
): Promise<ActionState> {
  try {
    ids(tenantId, itemId);
    const safeKind = oneOf(kind, CONTENT_KINDS);
    await apiFetch(tenantPath(tenantId, safeKind, itemId, "draft"), {
      method: "PATCH",
      json: { revision: revisionOf(revision), content: contentFor(safeKind, form) },
    });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  return { ok: "Draft saved. Publish it to make it live." };
}

export async function contentAction(
  kind: string, tenantId: string, itemId: string, action: string, revision: number,
  _prev: ActionState,
): Promise<ActionState> {
  try {
    ids(tenantId, itemId);
    const safeKind = oneOf(kind, CONTENT_KINDS);
    const verb = oneOf(action, ITEM_ACTIONS);
    await apiFetch(tenantPath(tenantId, safeKind, itemId, verb), {
      method: "POST",
      json: verb === "publish" ? { revision: revisionOf(revision) } : undefined,
    });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  const done = { publish: "Published.", unpublish: "Unpublished.", archive: "Archived.",
                 restore: "Restored as a draft." } as const;
  return { ok: done[action as keyof typeof done] };
}

// ----- website domains -------------------------------------------------------------------------
export async function addDomain(tenantId: string, _prev: ActionState, form: FormData): Promise<ActionState> {
  try {
    ids(tenantId);
    await apiFetch(tenantPath(tenantId, "domains"), {
      method: "POST", json: { hostname: text(form, "hostname") ?? "" },
    });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  return { ok: "Domain added. Publish the DNS record below, then verify." };
}

export async function verifyDomain(
  tenantId: string, domainId: string, _prev: ActionState,
): Promise<ActionState> {
  let result: { status: string; last_check_result: string | null };
  try {
    ids(tenantId, domainId);
    result = await apiFetch(tenantPath(tenantId, "domains", domainId, "verify"), { method: "POST" });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  if (result.status === "verified") return { ok: "Verified." };
  const why: Record<string, string> = {
    not_found: "The TXT record was not found yet. DNS changes can take a few minutes.",
    mismatch: "A TXT record exists but its value does not match. Check it was copied exactly.",
    dns_error: "The DNS lookup failed. Try again shortly.",
    timeout: "The DNS lookup timed out. Try again shortly.",
  };
  return { error: why[result.last_check_result ?? ""] ?? "Not verified yet." };
}

export async function removeDomain(
  tenantId: string, domainId: string, _prev: ActionState,
): Promise<ActionState> {
  try {
    ids(tenantId, domainId);
    await apiFetch(tenantPath(tenantId, "domains", domainId, "remove"), { method: "POST" });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  return { ok: "Domain removed." };
}

// ----- knowledge documents ---------------------------------------------------------------------
function uploadForm(form: FormData, withTitle: boolean): FormData {
  const file = form.get("file");
  if (!(file instanceof File) || file.size === 0) throw new UserInputError("Choose a file to upload.");
  if (file.size > MAX_UPLOAD_BYTES) throw new UserInputError("Files can be at most 10 MB.");
  const out = new FormData();
  if (withTitle) out.append("title", text(form, "title") ?? "");
  out.append("file", file, file.name);
  return out;
}

export async function uploadDocument(
  tenantId: string, _prev: ActionState, form: FormData,
): Promise<ActionState> {
  let created: { id: string };
  try {
    ids(tenantId);
    created = await apiFetch<{ id: string }>(tenantPath(tenantId, "knowledge"), {
      method: "POST", form: uploadForm(form, true),
    });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  redirect(`/clinics/${tenantId}/documents/${created.id}`);
}

export async function uploadVersion(
  tenantId: string, documentId: string, _prev: ActionState, form: FormData,
): Promise<ActionState> {
  try {
    ids(tenantId, documentId);
    await apiFetch(tenantPath(tenantId, "knowledge", documentId, "versions"), {
      method: "POST", form: uploadForm(form, false),
    });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  return { ok: "New version uploaded. Review it before it goes live." };
}

export async function reviewVersion(
  tenantId: string, documentId: string, versionId: string, decision: string,
  _prev: ActionState, form: FormData,
): Promise<ActionState> {
  try {
    ids(tenantId, documentId, versionId);
    const verb = oneOf(decision, ["approve", "reject"] as const);
    await apiFetch(tenantPath(tenantId, "knowledge", documentId, "versions", versionId, verb), {
      method: "POST", json: { note: text(form, "note") },
    });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  redirect(`/clinics/${tenantId}/documents/${documentId}`);
}

export async function documentAction(
  tenantId: string, documentId: string, action: string, _prev: ActionState,
): Promise<ActionState> {
  try {
    ids(tenantId, documentId);
    const verb = oneOf(action, DOCUMENT_ACTIONS);
    await apiFetch(tenantPath(tenantId, "knowledge", documentId, verb), { method: "POST" });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  return { ok: "Done." };
}

export async function renameDocument(
  tenantId: string, documentId: string, _prev: ActionState, form: FormData,
): Promise<ActionState> {
  try {
    ids(tenantId, documentId);
    await apiFetch(tenantPath(tenantId, "knowledge", documentId), {
      method: "PATCH", json: { title: text(form, "title") ?? "" },
    });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  return { ok: "Renamed." };
}

// ----- team ------------------------------------------------------------------------------------
export async function inviteMember(tenantId: string, _prev: ActionState, form: FormData): Promise<ActionState> {
  try {
    ids(tenantId);
    await apiFetch(tenantPath(tenantId, "members"), {
      method: "POST",
      json: { email: text(form, "email") ?? "", role: oneOf(text(form, "role"), ROLES) },
    });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  return { ok: "Invitation sent." };
}

export async function changeMemberRole(
  tenantId: string, membershipId: string, _prev: ActionState, form: FormData,
): Promise<ActionState> {
  try {
    ids(tenantId, membershipId);
    await apiFetch(tenantPath(tenantId, "members", membershipId), {
      method: "PATCH", json: { role: oneOf(text(form, "role"), ROLES) },
    });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  return { ok: "Role updated." };
}

export async function revokeMember(
  tenantId: string, membershipId: string, _prev: ActionState,
): Promise<ActionState> {
  try {
    ids(tenantId, membershipId);
    await apiFetch(tenantPath(tenantId, "members", membershipId, "revoke"), { method: "POST" });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  return { ok: "Access revoked." };
}

// ----- chat widget -----------------------------------------------------------------------------
export async function saveWidgetGreeting(
  tenantId: string, _prev: ActionState, form: FormData,
): Promise<ActionState> {
  try {
    ids(tenantId);
    await apiFetch(tenantPath(tenantId, "widget"), {
      method: "PATCH", json: { greeting: text(form, "greeting") ?? "" },
    });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  return { ok: "Greeting saved." };
}

export async function setWidgetEnabled(
  tenantId: string, enabled: boolean, _prev: ActionState,
): Promise<ActionState> {
  try {
    ids(tenantId);
    if (typeof enabled !== "boolean") throw new InvalidInput("invalid choice");
    await apiFetch(tenantPath(tenantId, "widget"), { method: "PATCH", json: { enabled } });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  return { ok: enabled ? "The chat is on." : "The chat is off." };
}

export async function rotateWidgetKey(tenantId: string, _prev: ActionState): Promise<ActionState> {
  try {
    ids(tenantId);
    await apiFetch(tenantPath(tenantId, "widget", "rotate-key"), { method: "POST" });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  return { ok: "New key created. Update the snippet on your website." };
}

// ----- inbox (Phase 3e) -------------------------------------------------------------------------
const HANDOVER_MESSAGES: Record<(typeof HANDOVER_STATUSES)[number], string> = {
  new: "Moved back to new.",
  in_progress: "Marked as in progress.",
  resolved: "Marked as resolved.",
};

export async function setHandoverStatus(
  tenantId: string, handoverId: string, status: string, _prev: ActionState,
): Promise<ActionState> {
  let next: (typeof HANDOVER_STATUSES)[number];
  try {
    ids(tenantId, handoverId);
    next = oneOf(status, HANDOVER_STATUSES);
    await apiFetch(tenantPath(tenantId, "handovers", handoverId), {
      method: "PATCH", json: { status: next },
    });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  return { ok: HANDOVER_MESSAGES[next] };
}

export async function closeConversation(
  tenantId: string, conversationId: string, _prev: ActionState,
): Promise<ActionState> {
  try {
    ids(tenantId, conversationId);
    await apiFetch(tenantPath(tenantId, "conversations", conversationId, "close"), {
      method: "POST",
    });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  return { ok: "Conversation closed. The visitor can start a new one by reloading the page." };
}

// ----- scheduling (Phase 4b) --------------------------------------------------------------------
const PROVIDER_EVENT_TYPE_ID = /^[A-Za-z0-9_.:/-]{1,200}$/;

export async function connectScheduling(
  tenantId: string, _prev: ActionState, form: FormData,
): Promise<ActionState> {
  try {
    ids(tenantId);
    const apiKey = form.get("api_key");
    if (typeof apiKey !== "string" || apiKey.trim().length < 10) {
      throw new UserInputError("Paste the API key from your Cal.com settings.");
    }
    // The key goes straight to the API, which verifies, encrypts and stores it. It is never
    // logged, returned or kept in the dashboard.
    await apiFetch(tenantPath(tenantId, "scheduling", "connect"), {
      method: "POST", json: { provider: "calcom", api_key: apiKey.trim() },
    });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  return { ok: "Cal.com connected. Now choose which appointment types patients can book." };
}

export async function disconnectScheduling(
  tenantId: string, _prev: ActionState,
): Promise<ActionState> {
  try {
    ids(tenantId);
    await apiFetch(tenantPath(tenantId, "scheduling", "disconnect"), { method: "POST" });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  return { ok: "Disconnected. You can also delete the API key in Cal.com." };
}

export async function saveAppointmentTypes(
  tenantId: string, _prev: ActionState, form: FormData,
): Promise<ActionState> {
  try {
    ids(tenantId);
    const items = form.getAll("type_id").map((raw) => {
      if (typeof raw !== "string" || !PROVIDER_EVENT_TYPE_ID.test(raw)) {
        throw new InvalidInput("invalid appointment type");
      }
      return {
        provider_event_type_id: raw,
        name: text(form, `name:${raw}`),
        enabled: form.get(`offer:${raw}`) === "on",
      };
    }).filter((item) => item.enabled);
    await apiFetch(tenantPath(tenantId, "scheduling", "appointment-types"), {
      method: "PUT", json: { items },
    });
  } catch (error) {
    return failure(error);
  }
  refresh(tenantId);
  return { ok: "Appointment types saved." };
}
