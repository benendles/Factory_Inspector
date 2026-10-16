import { InspectionForm } from "@/components/InspectionForm";
import { PageHeader } from "@/components/PageHeader";

export default function InspectionPage() {
  return <><PageHeader eyebrow="AI INSPECTION CENTER" title="Begin evidence-first inspection" description="Upload machine imagery, select the registered machine and simulated scenario, then review every agent decision before human controls become available." /><InspectionForm /></>;
}
