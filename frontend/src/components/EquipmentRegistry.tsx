"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Equipment } from "@/lib/api";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Card } from "@/components/ui/Card";

export function EquipmentRegistry() {
  const [equipment, setEquipment] = useState<Equipment[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.listEquipment().then(setEquipment).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not load equipment.")); }, []);
  return <>{error && <ApiErrorAlert message={error} />}<Card className="overflow-hidden"><div className="overflow-x-auto"><table className="w-full min-w-225 text-left text-sm"><thead className="border-b border-slate-700 bg-slate-950/50 text-xs tracking-wider text-slate-400 uppercase"><tr>{["Machine", "Manufacturer / model", "Serial / asset", "Location", ""].map((heading) => <th className="px-5 py-4" key={heading}>{heading}</th>)}</tr></thead><tbody>{equipment.map((item) => <tr className="border-b border-slate-800 last:border-0" key={item.id}><td className="px-5 py-4 font-semibold text-white">{item.machine_id}<p className="mt-1 text-xs font-normal text-slate-500">{item.equipment_type ?? "Unclassified"}</p></td><td className="px-5 py-4 text-slate-200">{item.manufacturer ?? "Unknown"}<p className="mt-1 text-xs text-slate-500">{item.model_number ?? "Model unavailable"}</p></td><td className="px-5 py-4 text-slate-300">{item.serial_number ?? "Serial unavailable"}<p className="mt-1 text-xs text-slate-500">{item.asset_tag ?? "No asset tag"}</p></td><td className="px-5 py-4 text-slate-300">{item.location ?? "Not recorded"}</td><td className="px-5 py-4 text-right"><Link href={`/inspection?machine_id=${encodeURIComponent(item.machine_id)}`} className="text-xs font-semibold text-emerald-300 hover:text-emerald-100">Inspect</Link></td></tr>)}{!equipment.length && <tr><td colSpan={5} className="px-5 py-12 text-center text-slate-400">No registered equipment is available.</td></tr>}</tbody></table></div></Card></>;
}
