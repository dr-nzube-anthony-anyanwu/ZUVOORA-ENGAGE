import { ContentItemPage } from "@/components/ContentPages";

export default async function Page({ params }: {
  params: Promise<{ tenantId: string; itemId: string }>;
}) {
  const { tenantId, itemId } = await params;
  return <ContentItemPage tenantId={tenantId} kind="faqs" itemId={itemId} />;
}
