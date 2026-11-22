"use server";

/**
 * Server Actions for the public website. They run on the Next.js server; the browser never talks
 * to the API directly. Next.js rejects cross-origin action calls (CSRF); the API validates every
 * field again, rate-limits and stores the request.
 */
import { headers } from "next/headers";
import { ApiRequestError, publicPost } from "@/lib/api";

export type DemoRequestState = { ok?: boolean; error?: string; details?: string[] } | null;

const INTERESTS = ["demo", "pilot", "pricing", "accessibility", "other"] as const;

function field(form: FormData, name: string, max: number): string | null {
  const value = form.get(name);
  if (typeof value !== "string") return null;
  const trimmed = value.trim().slice(0, max);
  return trimmed === "" ? null : trimmed;
}

const FIELD_LABELS: Record<string, string> = {
  name: "Your name", role: "Your role", "clinic name": "Clinic or organisation", city: "City",
  country: "Country", email: "Work email", phone: "Phone", message: "Message", interest: "Interested in",
};

export async function submitDemoRequest(_: DemoRequestState, form: FormData): Promise<DemoRequestState> {
  const interestValue = field(form, "interest", 20) ?? "demo";
  const interest = (INTERESTS as readonly string[]).includes(interestValue) ? interestValue : "demo";
  const body = {
    name: field(form, "name", 120) ?? "",
    role: field(form, "role", 80),
    clinic_name: field(form, "clinic_name", 160) ?? "",
    city: field(form, "city", 80),
    country: field(form, "country", 80),
    email: field(form, "email", 254) ?? "",
    phone: field(form, "phone", 30),
    interest,
    message: field(form, "message", 1000),
    consent: form.get("consent") === "on",
    website: field(form, "website", 200) ?? "",
  };
  if (!body.consent) {
    return { error: "Please agree to be contacted about your request." };
  }
  const forwarded = (await headers()).get("x-forwarded-for")?.split(",")[0]?.trim();
  try {
    await publicPost("/api/v1/public/demo-requests", body, forwarded || undefined);
    return { ok: true };
  } catch (error) {
    if (error instanceof ApiRequestError) {
      const details = error.details.map((d) => {
        const [name, ...rest] = d.split(": ");
        return FIELD_LABELS[name] ? `${FIELD_LABELS[name]}: ${rest.join(": ")}` : d;
      });
      return {
        error: error.code === "validation_error" ? "Please check the highlighted details." : error.userMessage,
        details,
      };
    }
    return { error: "Something went wrong. Please try again later." };
  }
}
