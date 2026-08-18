"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import DirectorNoteForm from "@/components/director-note-form";

type Department = "vfx" | "color" | "sound" | "editorial";
type Priority = "low" | "medium" | "high" | "critical";
type TicketStatus = "pending_review" | "approved" | "rejected";
type Ticket = { id: string; shot_id: string; director_note: string; department: Department; priority: Priority; status: TicketStatus };

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";
const columns: { status: TicketStatus; title: string; description: string }[] = [
  { status: "pending_review", title: "Por revisar", description: "Requiere decisión del supervisor" },
  { status: "approved", title: "Aprobadas", description: "Listas para asignación" },
  { status: "rejected", title: "Rechazadas", description: "No pasan a producción" },
];
const departmentLabel: Record<Department, string> = { vfx: "VFX", color: "Color", sound: "Sonido", editorial: "Edición" };
const priorityLabel: Record<Priority, string> = { low: "Baja", medium: "Media", high: "Alta", critical: "Crítica" };

export default function Home() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [processingId, setProcessingId] = useState<string | null>(null);

  const loadTickets = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/tickets`);
      if (!response.ok) throw new Error();
      setTickets(await response.json());
    } catch {
      setError("No se pudo conectar con el backend. Confirma que Uvicorn esté activo en el puerto 8000.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { void loadTickets(); }, [loadTickets]);

  async function reviewTicket(ticketId: string, decision: "approve" | "reject") {
    setProcessingId(ticketId);
    try {
      const response = await fetch(`${apiBaseUrl}/tickets/${ticketId}/review`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision }) });
      if (!response.ok) throw new Error();
      const updatedTicket: Ticket = await response.json();
      setTickets((current) => current.map((ticket) => ticket.id === ticketId ? updatedTicket : ticket));
    } catch { setError("No se pudo registrar la decisión. Inténtalo de nuevo."); }
    finally { setProcessingId(null); }
  }

  const pendingCount = useMemo(() => tickets.filter((ticket) => ticket.status === "pending_review").length, [tickets]);

  return <main className="min-h-screen bg-[#09111d] px-5 py-8 text-slate-100 sm:px-8 lg:px-12"><section className="mx-auto max-w-7xl">
    <header className="mb-10 flex flex-col justify-between gap-6 border-b border-slate-700/70 pb-7 md:flex-row md:items-end"><div><p className="mb-3 text-xs font-bold tracking-[0.22em] text-cyan-300">FRAMEFLOW / POST-PRODUCTION CONTROL</p><h1 className="text-4xl font-semibold tracking-tight text-white sm:text-5xl">Sala de decisiones</h1><p className="mt-3 max-w-xl text-slate-400">Revisa las notas analizadas por IA y valida el flujo de trabajo antes de asignar artistas.</p></div><div className="rounded-xl border border-cyan-400/20 bg-cyan-400/10 px-5 py-3"><p className="text-xs font-medium uppercase tracking-wider text-cyan-200">Pendientes de aprobación</p><p className="mt-1 text-3xl font-semibold text-white">{pendingCount}</p></div></header>
    <DirectorNoteForm onCreated={(ticket) => setTickets((current) => [ticket, ...current])} />
    {error && <div className="mb-6 flex items-center justify-between gap-4 rounded-lg border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100"><span>{error}</span><button className="underline underline-offset-4" onClick={() => void loadTickets()}>Reintentar</button></div>}
    <section className="grid gap-6 lg:grid-cols-3">{columns.map((column) => { const columnTickets = tickets.filter((ticket) => ticket.status === column.status); return <div key={column.status} className="rounded-2xl border border-slate-700/70 bg-[#101b2b] p-4 shadow-2xl shadow-black/10"><div className="mb-5 flex items-start justify-between"><div><h2 className="font-semibold text-white">{column.title}</h2><p className="mt-1 text-xs text-slate-500">{column.description}</p></div><span className="rounded-full bg-slate-800 px-2.5 py-1 text-xs font-semibold text-slate-300">{columnTickets.length}</span></div><div className="space-y-3">{loading && <p className="rounded-xl border border-dashed border-slate-700 p-5 text-sm text-slate-500">Cargando tickets…</p>}{!loading && columnTickets.length === 0 && <p className="rounded-xl border border-dashed border-slate-700 p-5 text-sm text-slate-500">Sin tickets en esta columna.</p>}{columnTickets.map((ticket) => <article key={ticket.id} className="rounded-xl border border-slate-700 bg-[#162337] p-4 transition hover:border-slate-500"><div className="mb-3 flex items-center justify-between gap-3"><span className="font-mono text-xs text-cyan-300">{ticket.shot_id}</span><span className={`priority priority-${ticket.priority}`}>{priorityLabel[ticket.priority]}</span></div><p className="text-sm leading-6 text-slate-200">{ticket.director_note}</p><div className="mt-4 flex items-center justify-between border-t border-slate-700 pt-3"><span className="text-xs font-medium uppercase tracking-wide text-slate-400">{departmentLabel[ticket.department]}</span>{ticket.status === "pending_review" && <div className="flex gap-2"><button disabled={processingId === ticket.id} onClick={() => void reviewTicket(ticket.id, "reject")} className="action-button reject">Rechazar</button><button disabled={processingId === ticket.id} onClick={() => void reviewTicket(ticket.id, "approve")} className="action-button approve">Aprobar</button></div>}</div></article>)}</div></div>; })}</section>
  </section></main>;
}
