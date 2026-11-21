import { ContentListPage } from "@/components/ContentPages";

export default async function Page({ params, searchParams }: {
  params: Promise<{ tenantId: string }>;
  searchParams: Promise<{ archived?: string }>;
}) {
  const [{ tenantId }, { archived }] = await Promise.all([params, searchParams]);
  return <ContentListPage tenantId={tenantId} kind="faqs" showArchived={archived === "1"} />;
}
