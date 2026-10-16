import { EquipmentRegistry } from "@/components/EquipmentRegistry";
import { PageHeader } from "@/components/PageHeader";

export default function RegistryPage() {
  return <><PageHeader eyebrow="ASSET REGISTRY" title="Registered equipment" description="Registry records are candidates for matching; they never replace an audited physical identity decision." /><EquipmentRegistry /></>;
}
