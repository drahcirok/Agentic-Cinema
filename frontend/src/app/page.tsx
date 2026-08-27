"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import DirectorNoteForm from "@/components/director-note-form";
import EditTicketDialog from "@/components/edit-ticket-dialog";

type Department = "vfx" | "color" | "sound" | "editorial";
type Priority = "low" | "medium" | "high" | "critical";
type TicketStatus = "pending_review" | "assigned" | "approved" | "in_progress" | "ready_for_qc" | "completed" | "rejected";
type View = "decisions" | "production" | "history";
type WorkflowAction = "assign" | "send_qc" | "complete" | "return_for_rework";
type Production = { id: string; name: string; current_user_role?: "producer" | "supervisor" | "artist" | null };
type ProductionMember = { uid: string; role: "producer" | "supervisor" | "artist"; department?: Department | null; display_name?: string | null; email?: string | null };

type Ticket = {
  id: string;
  shot_id: string;
  director_note: string;
  department: Department;
  priority: Priority;
  status: TicketStatus;
  ai_rationale?: string | null;
  supervisor_note?: string | null;
  artist_note?: string | null;
  supervisor_feedback?: string | null;
  assigned_to_uid?: string | null;
  assigned_to_name?: string | null;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";
const departmentLabel: Record<Department, string> = { vfx: "VFX", color: "Color", sound: "Sonido", editorial: "Edición" };
const priorityLabel: Record<Priority, string> = { low: "Baja", medium: "Media", high: "Alta", critical: "Crítica" };
const statusLabel: Record<TicketStatus, string> = {
  pending_review: "Por revisar", assigned: "Asignada", approved: "Asignada", in_progress: "En proceso",
  ready_for_qc: "Lista para QC", completed: "Completada", rejected: "Rechazada",
};

async function fetchTickets(headers: Record<string, string>, productionId?: string): Promise<Ticket[]> {
  const response = await fetch(`${apiBaseUrl}/tickets`, { headers: productionId ? { ...headers, "X-Production-Id": productionId } : headers });
  if (!response.ok) throw new Error("No se pudieron cargar los tickets.");
  return response.json();
}

async function bootstrapProduction(headers: Record<string, string>): Promise<Production> {
  const response = await fetch(`${apiBaseUrl}/productions/bootstrap`, { method: "POST", headers });
  if (!response.ok) throw new Error("No se pudo preparar tu producción.");
  return response.json();
}

async function fetchMembers(headers: Record<string, string>, productionId: string): Promise<ProductionMember[]> {
  const response = await fetch(`${apiBaseUrl}/productions/${productionId}/members`, { headers });
  if (!response.ok) throw new Error("No se pudo cargar el equipo de producción.");
  return response.json();
}

function TicketCard({ ticket, children }: { ticket: Ticket; children?: React.ReactNode }) {
  return (
    <article className="rounded-xl border border-slate-700 bg-[#162337] p-4 transition hover:border-slate-500">
      <div className="mb-3 flex items-center justify-between gap-3"><span className="font-mono text-xs text-cyan-300">{ticket.shot_id}</span><span className={`priority priority-${ticket.priority}`}>{priorityLabel[ticket.priority]}</span></div>
      <p className="text-sm leading-6 text-slate-200">{ticket.director_note}</p>
      <p className="mt-2 text-xs font-medium uppercase tracking-wide text-slate-400">{departmentLabel[ticket.department]} · {statusLabel[ticket.status]}</p>
      {ticket.artist_note && <div className="mt-3 rounded-lg border border-cyan-400/20 bg-cyan-400/5 px-3 py-2 text-xs text-slate-300"><span className="font-semibold text-cyan-300">Nota del artista: </span>{ticket.artist_note}</div>}
      {ticket.supervisor_feedback && <div className="mt-3 rounded-lg border border-amber-400/20 bg-amber-400/5 px-3 py-2 text-xs text-slate-300"><span className="font-semibold text-amber-300">Feedback del supervisor: </span>{ticket.supervisor_feedback}</div>}
      {children && <div className="mt-4 flex flex-wrap justify-end gap-2 border-t border-slate-700 pt-3">{children}</div>}
    </article>
  );
}

function TicketColumn({ title, description, tickets, loading, children }: { title: string; description: string; tickets: Ticket[]; loading: boolean; children: (ticket: Ticket) => React.ReactNode }) {
  return <section className="rounded-2xl border border-slate-700/70 bg-[#101b2b] p-4 shadow-2xl shadow-black/10"><div className="mb-5 flex items-start justify-between"><div><h2 className="font-semibold text-white">{title}</h2><p className="mt-1 text-xs text-slate-500">{description}</p></div><span className="rounded-full bg-slate-800 px-2.5 py-1 text-xs font-semibold text-slate-300">{tickets.length}</span></div><div className="space-y-3">{loading && <p className="rounded-xl border border-dashed border-slate-700 p-5 text-sm text-slate-500">Cargando tickets…</p>}{!loading && tickets.length === 0 && <p className="rounded-xl border border-dashed border-slate-700 p-5 text-sm text-slate-500">Sin tickets en esta columna.</p>}{tickets.map(children)}</div></section>;
}

export default function Home() {
  const { user, loading: authLoading, configured, signIn, signOut, getAuthHeaders } = useAuth();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [view, setView] = useState<View>("decisions");
  const [departmentFilter, setDepartmentFilter] = useState<Department>("vfx");
  const [workflowAction, setWorkflowAction] = useState<{ ticket: Ticket; type: WorkflowAction } | null>(null);
  const [workflowNote, setWorkflowNote] = useState("");
  const [production, setProduction] = useState<Production | null>(null);
  const [members, setMembers] = useState<ProductionMember[]>([]);
  const [assignedArtistId, setAssignedArtistId] = useState("");
  const [memberUid, setMemberUid] = useState("");
  const [memberName, setMemberName] = useState("");
  const [memberDepartment, setMemberDepartment] = useState<Department>("vfx");

  const loadTickets = useCallback(async () => {
    setLoading(true); setError(null);
    try { setTickets(await fetchTickets(await getAuthHeaders(), production?.id)); } catch { setError("No se pudo conectar con el backend. Inténtalo de nuevo."); } finally { setLoading(false); }
  }, [getAuthHeaders, production]);

  useEffect(() => {
    let current = true;
    async function loadInitialTickets() {
      if (!user) return;
      try {
        const headers = await getAuthHeaders();
        const currentProduction = await bootstrapProduction(headers);
        const [result, team] = await Promise.all([fetchTickets(headers, currentProduction.id), fetchMembers(headers, currentProduction.id)]);
        if (current) { setTickets(result); setProduction(currentProduction); setMembers(team); const ownMembership = team.find((member) => member.uid === user.uid); if (ownMembership?.department) setDepartmentFilter(ownMembership.department); if (ownMembership?.role === "artist") setView("production"); }
      } catch { if (current) setError("No se pudo conectar con el backend. Inténtalo de nuevo."); } finally { if (current) setLoading(false); }
    }
    void loadInitialTickets();
    return () => { current = false; };
  }, [user, getAuthHeaders]);

  async function updateTicket(ticketId: string, endpoint: string, body: object): Promise<boolean> {
    setProcessingId(ticketId); setError(null);
    try {
      if (!production) throw new Error("No hay una producción activa.");
      const response = await fetch(`${apiBaseUrl}/tickets/${ticketId}/${endpoint}`, { method: "PATCH", headers: { "Content-Type": "application/json", ...(await getAuthHeaders()), "X-Production-Id": production.id }, body: JSON.stringify(body) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? "No se pudo actualizar el ticket.");
      setTickets((current) => current.map((ticket) => ticket.id === ticketId ? data as Ticket : ticket));
      return true;
    } catch (cause) { setError(cause instanceof Error ? cause.message : "No se pudo actualizar el ticket."); } finally { setProcessingId(null); }
    return false;
  }

  async function addArtist(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!production) return;
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/productions/${production.id}/members`, { method: "POST", headers: { "Content-Type": "application/json", ...(await getAuthHeaders()) }, body: JSON.stringify({ uid: memberUid.trim(), display_name: memberName.trim() || null, role: "artist", department: memberDepartment }) });
      const created = await response.json();
      if (!response.ok) throw new Error(created.detail ?? "No se pudo agregar al artista.");
      setMembers((current) => [...current.filter((member) => member.uid !== created.uid), created as ProductionMember]);
      setMemberUid(""); setMemberName("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "No se pudo agregar al artista."); }
  }

  function reviewTicket(ticketId: string, decision: "reject") { void updateTicket(ticketId, "review", { decision }); }
  function startWork(ticket: Ticket) { void updateTicket(ticket.id, "work", { status: "in_progress" }); }
  function openWorkflowAction(ticket: Ticket, type: WorkflowAction) {
    setWorkflowAction({ ticket, type });
    setWorkflowNote(type === "send_qc" ? ticket.artist_note ?? "" : ticket.supervisor_feedback ?? "");
    setAssignedArtistId("");
  }
  async function confirmWorkflowAction() {
    if (!workflowAction) return;
    const { ticket, type } = workflowAction;
    if (type === "return_for_rework" && !workflowNote.trim()) {
      setError("Explica al artista qué debe corregir antes de devolver la tarea.");
      return;
    }
    if (type === "assign" && !assignedArtistId) { setError("Selecciona un artista para asignar esta tarea."); return; }
    const artist = members.find((member) => member.uid === assignedArtistId);
    const ok = type === "assign"
      ? await updateTicket(ticket.id, "review", { decision: "approve", assigned_to_uid: assignedArtistId, assigned_to_name: artist?.display_name ?? artist?.email ?? "Artista" })
      : type === "send_qc"
      ? await updateTicket(ticket.id, "work", { status: "ready_for_qc", artist_note: workflowNote.trim() || null })
      : await updateTicket(ticket.id, "quality-review", { decision: type === "complete" ? "approve" : "return_for_rework", supervisor_feedback: workflowNote.trim() || null });
    if (ok) setWorkflowAction(null);
  }

  const pending = useMemo(() => tickets.filter((ticket) => ticket.status === "pending_review"), [tickets]);
  const qualityQueue = useMemo(() => tickets.filter((ticket) => ticket.status === "ready_for_qc"), [tickets]);
  const productionTickets = useMemo(() => tickets.filter((ticket) => ticket.department === departmentFilter && ["assigned", "approved", "in_progress"].includes(ticket.status)), [tickets, departmentFilter]);
  const assigned = productionTickets.filter((ticket) => ticket.status === "assigned" || ticket.status === "approved");
  const inProgress = productionTickets.filter((ticket) => ticket.status === "in_progress");
  const completed = useMemo(() => tickets.filter((ticket) => ticket.status === "completed"), [tickets]);
  const rejected = useMemo(() => tickets.filter((ticket) => ticket.status === "rejected"), [tickets]);
  const canSupervise = production?.current_user_role === "producer" || production?.current_user_role === "supervisor";
  const canWork = production?.current_user_role === "artist";

  if (authLoading) return <main className="grid min-h-screen place-items-center bg-[#09111d] text-slate-300">Comprobando sesión…</main>;
  if (!configured) return <main className="grid min-h-screen place-items-center bg-[#09111d] p-6 text-center text-slate-300">Firebase Authentication aún no está configurado para este entorno.</main>;
  if (!user) return <main className="grid min-h-screen place-items-center bg-[#09111d] p-6 text-slate-100"><section className="w-full max-w-md rounded-2xl border border-slate-700 bg-[#101b2b] p-8 text-center"><p className="text-xs font-bold tracking-[0.22em] text-cyan-300">FRAMEFLOW / ACCESS CONTROL</p><h1 className="mt-4 text-3xl font-semibold text-white">Sala de decisiones privada</h1><p className="mt-3 text-sm leading-6 text-slate-400">Inicia sesión con tu cuenta de Google para ver y gestionar únicamente los tickets de tu producción.</p><button onClick={() => void signIn()} className="mt-6 rounded-lg bg-cyan-300 px-4 py-2 text-sm font-bold text-cyan-950">Continuar con Google</button></section></main>;

  return <main className="min-h-screen bg-[#09111d] px-5 py-8 text-slate-100 sm:px-8 lg:px-12"><section className="mx-auto max-w-7xl">
    <header className="mb-7 flex flex-col justify-between gap-6 border-b border-slate-700/70 pb-7 md:flex-row md:items-end"><div><p className="mb-3 text-xs font-bold tracking-[0.22em] text-cyan-300">FRAMEFLOW / POST-PRODUCTION CONTROL</p><h1 className="text-4xl font-semibold tracking-tight text-white sm:text-5xl">Sala de decisiones</h1><p className="mt-3 max-w-xl text-slate-400">Del análisis con Gemini al control de calidad del equipo de postproducción.</p></div><div className="flex items-end gap-4"><div className="hidden text-right text-xs text-slate-400 sm:block"><p>{user.displayName ?? user.email}</p><button onClick={() => void signOut()} className="mt-1 text-cyan-300 hover:underline">Cerrar sesión</button></div><div className="rounded-xl border border-cyan-400/20 bg-cyan-400/10 px-5 py-3"><p className="text-xs font-medium uppercase tracking-wider text-cyan-200">Por revisar</p><p className="mt-1 text-3xl font-semibold text-white">{pending.length}</p></div></div></header>
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3"><nav className="flex flex-wrap gap-2" aria-label="Vistas de FrameFlow">{([ ["decisions", "Sala de decisiones"], ["production", canWork ? "Mis tareas" : "Área de producción"], ["history", "Historial"] ] as const).filter(([key]) => key !== "decisions" || canSupervise).map(([key, label]) => <button key={key} onClick={() => setView(key)} className={view === key ? "rounded-lg bg-cyan-300 px-4 py-2 text-sm font-bold text-cyan-950" : "rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-300 hover:border-cyan-400"}>{label}</button>)}</nav>{production && <p className="rounded-lg border border-slate-700 bg-[#101b2b] px-3 py-2 text-xs text-slate-400"><span className="text-cyan-300">Producción: </span>{production.name} · {production.current_user_role}</p>}</div>
    {error && <div className="mb-6 flex items-center justify-between gap-4 rounded-lg border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100"><span>{error}</span><button className="underline underline-offset-4" onClick={() => void loadTickets()}>Reintentar</button></div>}
    {view === "decisions" && production && canSupervise && <><DirectorNoteForm productionId={production.id} onCreated={(ticket) => setTickets((current) => [ticket as Ticket, ...current])} /><section className="grid gap-6 lg:grid-cols-2"><TicketColumn title="Por revisar" description="Notas que requieren decisión del supervisor" tickets={pending} loading={loading}>{(ticket) => <TicketCard key={ticket.id} ticket={ticket}><button disabled={processingId === ticket.id} onClick={() => reviewTicket(ticket.id, "reject")} className="action-button reject">Rechazar</button><EditTicketDialog productionId={production.id} ticket={ticket} onUpdated={(updated) => setTickets((current) => current.map((item) => item.id === updated.id ? updated : item))} /><button disabled={processingId === ticket.id} onClick={() => openWorkflowAction(ticket, "assign")} className="action-button approve">Aprobar y asignar</button></TicketCard>}</TicketColumn><TicketColumn title="Control de calidad" description="Trabajo enviado por artistas para revisión final" tickets={qualityQueue} loading={loading}>{(ticket) => <TicketCard key={ticket.id} ticket={ticket}><button disabled={processingId === ticket.id} onClick={() => openWorkflowAction(ticket, "return_for_rework")} className="action-button reject">Devolver</button><button disabled={processingId === ticket.id} onClick={() => openWorkflowAction(ticket, "complete")} className="action-button approve">Completar</button></TicketCard>}</TicketColumn></section></>}
    {view === "production" && <><div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-700/70 bg-[#101b2b] p-4"><div><h2 className="font-semibold text-white">{canWork ? "Mis tareas asignadas" : "Área de producción"}</h2><p className="mt-1 text-xs text-slate-500">{canWork ? "Solo puedes avanzar las tareas asignadas a tu usuario." : "Asigna y sigue el trabajo por departamento."}</p></div>{!canWork && <select value={departmentFilter} onChange={(event) => setDepartmentFilter(event.target.value as Department)} className="rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm text-slate-100"><option value="vfx">VFX</option><option value="sound">Sonido</option><option value="color">Color</option><option value="editorial">Edición</option></select>}</div>{production?.current_user_role === "producer" && <section className="mb-6 rounded-xl border border-slate-700/70 bg-[#101b2b] p-4"><h2 className="font-semibold text-white">Equipo</h2><p className="mt-1 text-xs text-slate-500">El artista debe iniciar sesión una vez y enviarte su UID de Firebase. Tu UID: <span className="font-mono text-cyan-300">{user.uid}</span></p><form onSubmit={addArtist} className="mt-4 grid gap-3 md:grid-cols-4"><input required value={memberUid} onChange={(event) => setMemberUid(event.target.value)} placeholder="UID del artista" className="rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm" /><input value={memberName} onChange={(event) => setMemberName(event.target.value)} placeholder="Nombre (opcional)" className="rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm" /><select value={memberDepartment} onChange={(event) => setMemberDepartment(event.target.value as Department)} className="rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm"><option value="vfx">VFX</option><option value="sound">Sonido</option><option value="color">Color</option><option value="editorial">Edición</option></select><button className="rounded-lg bg-cyan-300 px-4 py-2 text-sm font-bold text-cyan-950">Agregar artista</button></form><div className="mt-3 flex flex-wrap gap-2">{members.map((member) => <span key={member.uid} className="rounded-full border border-slate-600 px-3 py-1 text-xs text-slate-300">{member.display_name ?? member.email ?? member.uid} · {member.role}{member.department ? ` · ${departmentLabel[member.department]}` : ""}</span>)}</div></section>}<section className="grid gap-6 lg:grid-cols-3"><TicketColumn title="Asignadas" description={`${departmentLabel[departmentFilter]} · listas para iniciar`} tickets={assigned} loading={loading}>{(ticket) => <TicketCard key={ticket.id} ticket={ticket}>{canWork && <button disabled={processingId === ticket.id} onClick={() => startWork(ticket)} className="action-button approve">Iniciar trabajo</button>}</TicketCard>}</TicketColumn><TicketColumn title="En proceso" description="El artista trabaja y luego envía a QC" tickets={inProgress} loading={loading}>{(ticket) => <TicketCard key={ticket.id} ticket={ticket}>{canWork && <button disabled={processingId === ticket.id} onClick={() => openWorkflowAction(ticket, "send_qc")} className="action-button approve">Enviar a QC</button>}</TicketCard>}</TicketColumn><TicketColumn title="Listas para QC" description="Esperando revisión del supervisor" tickets={qualityQueue.filter((ticket) => ticket.department === departmentFilter)} loading={loading}>{(ticket) => <TicketCard key={ticket.id} ticket={ticket} />}</TicketColumn></section></>}
    {view === "history" && <section className="grid gap-6 lg:grid-cols-2"><TicketColumn title="Completadas" description="Entregables aprobados por control de calidad" tickets={completed} loading={loading}>{(ticket) => <TicketCard key={ticket.id} ticket={ticket} />}</TicketColumn><TicketColumn title="Rechazadas" description="Notas que no avanzaron a producción" tickets={rejected} loading={loading}>{(ticket) => <TicketCard key={ticket.id} ticket={ticket} />}</TicketColumn></section>}
    {workflowAction && <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/75 p-4"><section role="dialog" aria-modal="true" aria-labelledby="workflow-dialog-title" className="w-full max-w-lg rounded-2xl border border-slate-700 bg-[#101b2b] p-6 shadow-2xl"><p className="text-xs font-bold tracking-[0.2em] text-cyan-300">FRAMEFLOW / WORKFLOW</p><h2 id="workflow-dialog-title" className="mt-2 text-xl font-semibold text-white">{workflowAction.type === "assign" ? "Asignar artista" : workflowAction.type === "send_qc" ? "Enviar a control de calidad" : workflowAction.type === "complete" ? "Completar tarea" : "Devolver para corrección"}</h2>{workflowAction.type === "assign" ? <label className="mt-5 block text-xs font-semibold uppercase tracking-wide text-slate-400">Artista del equipo<select autoFocus value={assignedArtistId} onChange={(event) => setAssignedArtistId(event.target.value)} className="mt-2 w-full rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm text-white outline-none focus:border-cyan-300"><option value="">Selecciona un artista…</option>{members.filter((member) => member.role === "artist" && member.department === workflowAction.ticket.department).map((member) => <option key={member.uid} value={member.uid}>{member.display_name ?? member.email ?? member.uid}</option>)}</select></label> : <><p className="mt-2 text-sm text-slate-400">{workflowAction.type === "send_qc" ? "Añade contexto para que el supervisor pueda revisar el entregable." : workflowAction.type === "complete" ? "Puedes dejar una observación final antes de archivar el trabajo." : "Describe claramente los cambios que el artista debe realizar."}</p><label className="mt-5 block text-xs font-semibold uppercase tracking-wide text-slate-400">{workflowAction.type === "send_qc" ? "Nota del artista" : "Feedback del supervisor"}<textarea autoFocus value={workflowNote} onChange={(event) => setWorkflowNote(event.target.value)} maxLength={1000} rows={4} placeholder={workflowAction.type === "return_for_rework" ? "Ej. Corregir los bordes del micrófono junto al cabello." : "Comentario opcional…"} className="mt-2 w-full rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm text-white outline-none placeholder:text-slate-500 focus:border-cyan-300" /></label></>}<div className="mt-6 flex justify-end gap-3"><button onClick={() => setWorkflowAction(null)} disabled={processingId === workflowAction.ticket.id} className="action-button reject">Cancelar</button><button onClick={() => void confirmWorkflowAction()} disabled={processingId === workflowAction.ticket.id} className="action-button approve">{processingId === workflowAction.ticket.id ? "Guardando…" : workflowAction.type === "assign" ? "Asignar tarea" : workflowAction.type === "send_qc" ? "Enviar a QC" : workflowAction.type === "complete" ? "Completar" : "Devolver tarea"}</button></div></section></div>}
  </section></main>;
}
