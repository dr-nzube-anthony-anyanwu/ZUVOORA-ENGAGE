import "server-only";

import { notFound, redirect } from "next/navigation";
import { cache } from "react";
import { ApiRequestError, apiGet, isUuid, tenantPath } from "@/lib/api";
import type { TenantDetail } from "@/lib/types";

/** Turn API failures on a page load into the right navigation (login, 404) or rethrow. */
export function handlePageError(error: unknown): never {
  if (error instanceof ApiRequestError) {
    if (error.status === 401) redirect("/login");
    if (error.status === 404 || error.status === 403 || error.status === 422) notFound();
  }
  throw error;
}

/** Load the clinic the user is viewing; 404 for malformed ids or clinics they cannot access. */
export const loadClinic = cache(async (tenantId: string): Promise<TenantDetail> => {
  if (!isUuid(tenantId)) notFound();
  try {
    return await apiGet<TenantDetail>(tenantPath(tenantId));
  } catch (error) {
    handlePageError(error);
  }
});

/** 404 unless every id from the URL is a canonical UUID. */
export function requireIds(...values: string[]): void {
  if (!values.every(isUuid)) notFound();
}

/** GET a tenant-scoped API resource for a page, with the same error handling. */
export async function load<T>(tenantId: string, ...segments: string[]): Promise<T> {
  return loadWithQuery<T>(tenantId, segments, {});
}

/** Like `load`, with a query string built from fixed keys and encoded values. */
export async function loadWithQuery<T>(
  tenantId: string, segments: string[], query: Record<string, string>,
): Promise<T> {
  const search = new URLSearchParams(query).toString();
  try {
    return await apiGet<T>(tenantPath(tenantId, ...segments) + (search ? `?${search}` : ""));
  } catch (error) {
    handlePageError(error);
  }
}
