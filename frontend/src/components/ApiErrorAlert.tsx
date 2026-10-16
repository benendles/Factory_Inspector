import { AlertTriangle } from "lucide-react";

export function ApiErrorAlert({ message }: { message: string }) {
  return (
    <div role="alert" className="flex gap-3 rounded-lg border border-rose-400/40 bg-rose-400/10 p-4 text-sm text-rose-100">
      <AlertTriangle className="mt-0.5 size-5 shrink-0" aria-hidden />
      <p>{message}</p>
    </div>
  );
}
