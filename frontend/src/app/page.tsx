import { FactoryOverview } from "@/components/FactoryOverview";
import { PageHeader } from "@/components/PageHeader";

export default function HomePage() {
  return <><PageHeader eyebrow="OPERATIONS OVERVIEW" title="Factory control surface" description="Monitor persisted registry data and begin an evidence-first AI inspection workflow." /><FactoryOverview /></>;
}
