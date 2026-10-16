import { PageHeader } from "@/components/PageHeader";
import { WorkflowDashboard } from "@/components/WorkflowDashboard";

export default async function WorkflowPage({ params }: { params: Promise<{ threadId: string }> }) {
  const { threadId } = await params;
  return <><PageHeader eyebrow="WORKFLOW CONTROL" title="Inspection workflow" description="Follow each agent output and human decision. Supplier research and simulated verification remain evidence-bound and do not certify physical safety." /><WorkflowDashboard threadId={threadId} /></>;
}
