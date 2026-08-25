"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import DirectorNoteForm from "@/components/director-note-form";
import EditTicketDialog from "@/components/edit-ticket-dialog";

type Department = "vfx" | "color" | "sound" | "editorial";
type Priority = "low" | "medium" | "high" | "critical";
type TicketStatus = "pending_review" | "approved" | "rejected";

type Ticket = {
  id: string;
  shot_id: string;
  director_note: string;
  department: Department;
  priority: Priority;
  status: TicketStatus;
  ai_rationale?: string | null;
  supervisor_note?: string | null;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

const columns: { status: TicketStatus; title: string; description: string }[] = [
  { status: "pending_review", title: "Por revisar",  description: "Requiere decisión del supervisor" },
  { status: "approved",       title: "Aprobadas",    description: "Listas para asignación" },
  { status: "rejected",       title: "Rechazadas",   description: "No pasan a producción" },
];

const departmentLabel: Record<Department, string> = {
  vfx: "VFX", color: "Color", sound: "Sonido", editorial: "Edición",
};
const priorityLabel: Record<Priority, string> = {
  low: "Baja", medium: "Media", high: "Alta", critical: "Crítica",
};

async function fetchTickets(): Promise<Ticket[]> {
  const response = await fetch(`${apiBaseUrl}/tickets`);
  if (!response.ok) throw new Error("No se pudieron cargar los tickets.");
  return response.json();
}

export default function Home() {
  const [tickets, setTickets]       = useState<Ticket[]>([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState<string | null>(null);
  const [processingId, setProcessingId] = useState<string | null>(null);

  const loadTickets = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setTickets(await fetchTickets());
    } catch {
      setError("No se pudo conectar con el backend. Confirma que Uvicorn esté activo en el puerto 8000.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let isCurrent = true;

    async function loadInitialTickets() {
      try {
        const initialTickets = await fetchTickets();
        if (isCurrent) setTickets(initialTickets);
      } catch {
        if (isCurrent) {
          setError("No se pudo conectar con el backend. Confirma que Uvicorn esté activo en el puerto 8000.");
        }
      } finally {
        if (isCurrent) setLoading(false);
      }
    }

    void loadInitialTickets();
    return () => { isCurrent = false; };
  }, []);

  async function reviewTicket(ticketId: string, decision: "approve" | "reject") {
    setProcessingId(ticketId);
    try {
      const response = await fetch(`${apiBaseUrl}/tickets/${ticketId}/review`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
      });
      if (!response.ok) throw new Error();
      const updatedTicket: Ticket = await response.json();
      setTickets((current) =>
        current.map((t) => (t.id === ticketId ? updatedTicket : t))
      );
    } catch {
      setError("No se pudo registrar la decisión. Inténtalo de nuevo.");
    } finally {
      setProcessingId(null);
    }
  }

  function handleTicketEdited(updated: Ticket) {
    setTickets((current) => current.map((t) => (t.id === updated.id ? updated : t)));
  }

  const pendingCount = useMemo(
    () => tickets.filter((t) => t.status === "pending_review").length,
    [tickets]
  );

  return (
    <main className="min-h-screen bg-[#09111d] px-5 py-8 text-slate-100 sm:px-8 lg:px-12">
      <section className="mx-auto max-w-7xl">
        {/* Header */}
        <header className="mb-10 flex flex-col justify-between gap-6 border-b border-slate-700/70 pb-7 md:flex-row md:items-end">
          <div>
            <p className="mb-3 text-xs font-bold tracking-[0.22em] text-cyan-300">
              FRAMEFLOW / POST-PRODUCTION CONTROL
            </p>
            <h1 className="text-4xl font-semibold tracking-tight text-white sm:text-5xl">
              Sala de decisiones
            </h1>
            <p className="mt-3 max-w-xl text-slate-400">
              Revisa las notas analizadas por IA y valida el flujo de trabajo antes de asignar artistas.
            </p>
          </div>
          <div className="rounded-xl border border-cyan-400/20 bg-cyan-400/10 px-5 py-3">
            <p className="text-xs font-medium uppercase tracking-wider text-cyan-200">
              Pendientes de aprobación
            </p>
            <p className="mt-1 text-3xl font-semibold text-white">{pendingCount}</p>
          </div>
        </header>

        {/* Ingestion form */}
        <DirectorNoteForm
          onCreated={(ticket) => setTickets((current) => [ticket as Ticket, ...current])}
        />

        {/* Error banner */}
        {error && (
          <div className="mb-6 flex items-center justify-between gap-4 rounded-lg border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
            <span>{error}</span>
            <button className="underline underline-offset-4" onClick={() => void loadTickets()}>
              Reintentar
            </button>
          </div>
        )}

        {/* Kanban board */}
        <section className="grid gap-6 lg:grid-cols-3">
          {columns.map((column) => {
            const columnTickets = tickets.filter((t) => t.status === column.status);
            return (
              <div
                key={column.status}
                className="rounded-2xl border border-slate-700/70 bg-[#101b2b] p-4 shadow-2xl shadow-black/10"
              >
                {/* Column header */}
                <div className="mb-5 flex items-start justify-between">
                  <div>
                    <h2 className="font-semibold text-white">{column.title}</h2>
                    <p className="mt-1 text-xs text-slate-500">{column.description}</p>
                  </div>
                  <span className="rounded-full bg-slate-800 px-2.5 py-1 text-xs font-semibold text-slate-300">
                    {columnTickets.length}
                  </span>
                </div>

                {/* Ticket cards */}
                <div className="space-y-3">
                  {loading && (
                    <p className="rounded-xl border border-dashed border-slate-700 p-5 text-sm text-slate-500">
                      Cargando tickets…
                    </p>
                  )}
                  {!loading && columnTickets.length === 0 && (
                    <p className="rounded-xl border border-dashed border-slate-700 p-5 text-sm text-slate-500">
                      Sin tickets en esta columna.
                    </p>
                  )}
                  {columnTickets.map((ticket) => (
                    <article
                      key={ticket.id}
                      className="rounded-xl border border-slate-700 bg-[#162337] p-4 transition hover:border-slate-500"
                    >
                      {/* Card header */}
                      <div className="mb-3 flex items-center justify-between gap-3">
                        <span className="font-mono text-xs text-cyan-300">{ticket.shot_id}</span>
                        <span className={`priority priority-${ticket.priority}`}>
                          {priorityLabel[ticket.priority]}
                        </span>
                      </div>

                      {/* Director note */}
                      <p className="text-sm leading-6 text-slate-200">{ticket.director_note}</p>

                      {/* Supervisor note (shown on approved / rejected cards) */}
                      {ticket.supervisor_note && ticket.status !== "pending_review" && (
                        <div className="mt-3 rounded-lg border border-slate-600/60 bg-slate-800/50 px-3 py-2">
                          <p className="mb-0.5 text-xs font-semibold uppercase tracking-wide text-slate-400">
                            Nota del supervisor
                          </p>
                          <p className="text-xs leading-relaxed text-slate-300">
                            {ticket.supervisor_note}
                          </p>
                        </div>
                      )}

                      {/* Card footer */}
                      <div className="mt-4 flex items-center justify-between border-t border-slate-700 pt-3">
                        <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
                          {departmentLabel[ticket.department]}
                        </span>

                        {ticket.status === "pending_review" && (
                          <div className="flex gap-2">
                            {/* Reject */}
                            <button
                              disabled={processingId === ticket.id}
                              onClick={() => void reviewTicket(ticket.id, "reject")}
                              className="action-button reject"
                            >
                              Rechazar
                            </button>

                            {/* Edit — opens the dialog */}
                            <EditTicketDialog
                              ticket={ticket}
                              onUpdated={handleTicketEdited}
                            />

                            {/* Approve */}
                            <button
                              disabled={processingId === ticket.id}
                              onClick={() => void reviewTicket(ticket.id, "approve")}
                              className="action-button approve"
                            >
                              Aprobar
                            </button>
                          </div>
                        )}
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            );
          })}
        </section>
      </section>
    </main>
  );
}
