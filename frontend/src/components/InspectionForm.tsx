"use client";

import { ImagePlus, LoaderCircle, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { api, type Equipment, type Scenario } from "@/lib/api";
import { rememberCurrentWorkflow } from "@/lib/currentWorkflow";

export function InspectionForm() {
  const router = useRouter();
  const [equipment, setEquipment] = useState<Equipment[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [machineId, setMachineId] = useState("");
  const [scenarioId, setScenarioId] = useState("overheating");
  const [image, setImage] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.listEquipment(), api.listScenarios()])
      .then(([machines, scenarioResponse]) => {
        setEquipment(machines);
        setScenarios(scenarioResponse.scenarios);
        const selectedMachine = new URLSearchParams(window.location.search).get("machine_id");
        if (selectedMachine && machines.some((machine) => machine.machine_id === selectedMachine)) setMachineId(selectedMachine);
        else if (machines[0]) setMachineId(machines[0].machine_id);
        if (!scenarioResponse.scenarios.some((scenario) => scenario.scenario_id === scenarioId) && scenarioResponse.scenarios[0]) setScenarioId(scenarioResponse.scenarios[0].scenario_id);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not load inspection configuration."));
    // Initial query selection is intentional; state changes must not reload options.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!image || !machineId || !scenarioId) {
      setError("Select a registered machine, a scenario, and an inspection image.");
      return;
    }
    if (image.size > 10 * 1024 * 1024) {
      setError("The inspection image exceeds the 10 MiB API limit.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const workflow = await api.startWorkflowWithImage({ scenarioId, machineId, image });
      rememberCurrentWorkflow(workflow.thread_id);
      router.push(`/workflow/${workflow.thread_id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start the inspection workflow.");
    } finally {
      setLoading(false);
    }
  };

  return <Card className="max-w-4xl p-6 sm:p-8"><form onSubmit={submit} className="space-y-6"><div className="grid gap-5 md:grid-cols-2"><label className="grid gap-2 text-sm font-medium text-slate-200">Registered machine<select value={machineId} onChange={(event) => setMachineId(event.target.value)} className="rounded-md border border-slate-600 bg-slate-950 px-3 py-2.5 text-slate-100 focus:border-emerald-300 focus:outline-none"><option value="">Select a registered machine</option>{equipment.map((item) => <option key={item.id} value={item.machine_id}>{item.machine_id} — {item.manufacturer ?? "Unknown"} {item.model_number ?? ""}</option>)}</select></label><label className="grid gap-2 text-sm font-medium text-slate-200">Simulation scenario<select value={scenarioId} onChange={(event) => setScenarioId(event.target.value)} className="rounded-md border border-slate-600 bg-slate-950 px-3 py-2.5 text-slate-100 focus:border-emerald-300 focus:outline-none">{scenarios.map((scenario) => <option key={scenario.scenario_id} value={scenario.scenario_id}>{scenario.name ?? scenario.scenario_id}</option>)}</select></label></div><label className="grid gap-3 rounded-xl border border-dashed border-slate-600 bg-slate-950/40 p-6 text-center"><input className="sr-only" type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setImage(event.target.files?.[0] ?? null)} /><ImagePlus className="mx-auto size-8 text-emerald-300" /><span className="font-medium text-slate-100">{image ? image.name : "Select a JPEG, PNG, or WEBP inspection image"}</span><span className="text-xs text-slate-400">Maximum 10 MiB. Upload evidence is processed temporarily by the API.</span></label>{error && <ApiErrorAlert message={error} />}<div className="flex flex-col justify-between gap-3 border-t border-slate-700 pt-5 sm:flex-row sm:items-center"><p className="max-w-xl text-xs leading-5 text-slate-400">Starting an inspection creates an investigation workflow. Vision and OCR outputs are candidate evidence, not physical identity proof.</p><Button disabled={loading} type="submit">{loading ? <LoaderCircle className="size-4 animate-spin" /> : <Upload className="size-4" />}{loading ? "Starting inspection…" : "Start AI inspection"}</Button></div></form></Card>;
}
