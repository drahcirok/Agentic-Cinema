"use client";

import { FormEvent, useState } from "react";

type Ticket = {
  id: string;
  shot_id: string;
  director_note: string;
  department: "vfx" | "color" | "sound" | "editorial";
  priority: "low" | "medium" | "high" | "critical";
  status: "pending_review" | "approved" | "rejected";
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

export default function DirectorNoteForm({ onCreated }: { onCreated: (ticket: Ticket) => void }) {
  const [shotId, setShotId] = useState("");
  const [directorNote, setDirectorNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setMessage(null);
    try {
      const response = await fetch(`${apiBaseUrl}/ingestion/director-notes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shot_id: shotId, director_note: directorNote }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "No se pudo procesar la nota.");
      onCreated(body);
      setShotId("");
      setDirectorNote("");
      setMessage("Gemini creó un ticket pendiente de revisión.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo procesar la nota.");
    } finally {
      setSubmitting(false);
    }
  }

  return <form onSubmit={submit} className="mb-7 grid gap-3 rounded-2xl border border-slate-700/70 bg-[#101b2b] p-4 md:grid-cols-[160px_1fr_auto] md:items-end">
    <label className="grid gap-1 text-xs font-semibold text-slate-400">TOMA<input required value={shotId} onChange={(event) => setShotId(event.target.value)} placeholder="SC03-SH014" className="rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm text-white outline-none focus:border-cyan-300" /></label>
    <label className="grid gap-1 text-xs font-semibold text-slate-400">NOTA DEL DIRECTOR<input required value={directorNote} onChange={(event) => setDirectorNote(event.target.value)} placeholder="Ej. Eliminar el micrófono del encuadre." className="rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm text-white outline-none focus:border-cyan-300" /></label>
    <button disabled={submitting} className="rounded-lg bg-cyan-300 px-4 py-2 text-sm font-bold text-cyan-950 disabled:opacity-50">{submitting ? "Analizando…" : "Analizar con Gemini"}</button>
    {message && <p className="text-xs text-slate-300 md:col-span-3">{message}</p>}
  </form>;
}
