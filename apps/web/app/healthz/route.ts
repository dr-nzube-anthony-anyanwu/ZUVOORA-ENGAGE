/**
 * Container health check (Phase 6, R11): the dashboard server is up and answering. It does not
 * call the API or Supabase, so an outage elsewhere does not restart a healthy dashboard.
 */
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ status: "ok" }, { headers: { "Cache-Control": "no-store" } });
}
