"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import DirectorNoteForm from "@/components/director-note-form";
import EditTicketDialog from "@/components/edit-ticket-dialog";

type Department = "vfx" | "color" | "sound" | "editorial";
type Priority = "low" | "medium" | "high" | "critical";
type TicketStatus =
  | "pending_review"
  | "assigned"
  | "approved"
  | "in_progress"
  | "ready_for_qc"
  | "completed"
  | "rejected";
type View = "decisions" | "production" | "history" | "team";
type WorkflowAction = "assign" | "send_qc" | "complete" | "return_for_rework";
type Production = {
  id: string;
  name: string;
  current_user_role?: "producer" | "supervisor" | "artist" | null;
};
type ProductionMember = {
  production_id?: string;
  production_name?: string | null;
  uid: string;
  role: "producer" | "supervisor" | "artist";
  department?: Department | null;
  display_name?: string | null;
  email?: string | null;
  membership_status?: "pending" | "accepted" | "declined";
};

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

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";
const departmentLabel: Record<Department, string> = {
  vfx: "VFX",
  color: "Color",
  sound: "Sonido",
  editorial: "Edición",
};
const priorityLabel: Record<Priority, string> = {
  low: "Baja",
  medium: "Media",
  high: "Alta",
  critical: "Crítica",
};
const statusLabel: Record<TicketStatus, string> = {
  pending_review: "Por revisar",
  assigned: "Asignada",
  approved: "Asignada",
  in_progress: "En proceso",
  ready_for_qc: "Lista para QC",
  completed: "Completada",
  rejected: "Rechazada",
};

async function fetchTickets(
  headers: Record<string, string>,
  productionId?: string,
): Promise<Ticket[]> {
  const response = await fetch(`${apiBaseUrl}/tickets`, {
    headers: productionId
      ? { ...headers, "X-Production-Id": productionId }
      : headers,
  });
  if (!response.ok) throw new Error("No se pudieron cargar los tickets.");
  return response.json();
}

async function fetchProductions(
  headers: Record<string, string>,
): Promise<Production[]> {
  const response = await fetch(`${apiBaseUrl}/productions`, { headers });
  if (!response.ok) throw new Error("No se pudieron cargar tus producciones.");
  return response.json();
}

async function fetchInvitations(
  headers: Record<string, string>,
): Promise<ProductionMember[]> {
  const response = await fetch(`${apiBaseUrl}/productions/invitations`, {
    headers,
  });
  if (!response.ok) throw new Error("No se pudieron cargar tus invitaciones.");
  return response.json();
}

async function fetchMembers(
  headers: Record<string, string>,
  productionId: string,
): Promise<ProductionMember[]> {
  const response = await fetch(
    `${apiBaseUrl}/productions/${productionId}/members`,
    { headers },
  );
  if (!response.ok)
    throw new Error("No se pudo cargar el equipo de producción.");
  return response.json();
}

function TicketCard({
  ticket,
  children,
}: {
  ticket: Ticket;
  children?: React.ReactNode;
}) {
  return (
    <article className="rounded-xl border border-slate-700 bg-[#162337] p-4 transition hover:border-slate-500">
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="font-mono text-xs text-cyan-300">
          {ticket.shot_id}
        </span>
        <span className={`priority priority-${ticket.priority}`}>
          {priorityLabel[ticket.priority]}
        </span>
      </div>
      <p className="text-sm leading-6 text-slate-200">{ticket.director_note}</p>
      <p className="mt-2 text-xs font-medium uppercase tracking-wide text-slate-400">
        {departmentLabel[ticket.department]} · {statusLabel[ticket.status]}
      </p>
      {ticket.artist_note && (
        <div className="mt-3 rounded-lg border border-cyan-400/20 bg-cyan-400/5 px-3 py-2 text-xs text-slate-300">
          <span className="font-semibold text-cyan-300">
            Nota del artista:{" "}
          </span>
          {ticket.artist_note}
        </div>
      )}
      {ticket.supervisor_feedback && (
        <div className="mt-3 rounded-lg border border-amber-400/20 bg-amber-400/5 px-3 py-2 text-xs text-slate-300">
          <span className="font-semibold text-amber-300">
            Feedback del supervisor:{" "}
          </span>
          {ticket.supervisor_feedback}
        </div>
      )}
      {children && (
        <div className="mt-4 flex flex-wrap justify-end gap-2 border-t border-slate-700 pt-3">
          {children}
        </div>
      )}
    </article>
  );
}

function TicketColumn({
  title,
  description,
  tickets,
  loading,
  children,
}: {
  title: string;
  description: string;
  tickets: Ticket[];
  loading: boolean;
  children: (ticket: Ticket) => React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-slate-700/70 bg-[#101b2b] p-4 shadow-2xl shadow-black/10">
      <div className="mb-5 flex items-start justify-between">
        <div>
          <h2 className="font-semibold text-white">{title}</h2>
          <p className="mt-1 text-xs text-slate-500">{description}</p>
        </div>
        <span className="rounded-full bg-slate-800 px-2.5 py-1 text-xs font-semibold text-slate-300">
          {tickets.length}
        </span>
      </div>
      <div className="space-y-3">
        {loading && (
          <p className="rounded-xl border border-dashed border-slate-700 p-5 text-sm text-slate-500">
            Cargando tickets…
          </p>
        )}
        {!loading && tickets.length === 0 && (
          <p className="rounded-xl border border-dashed border-slate-700 p-5 text-sm text-slate-500">
            Sin tickets en esta columna.
          </p>
        )}
        {tickets.map(children)}
      </div>
    </section>
  );
}

export default function Home() {
  const {
    user,
    loading: authLoading,
    configured,
    signIn,
    signOut,
    getAuthHeaders,
  } = useAuth();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [view, setView] = useState<View>("decisions");
  const [departmentFilter, setDepartmentFilter] = useState<Department>("vfx");
  const [workflowAction, setWorkflowAction] = useState<{
    ticket: Ticket;
    type: WorkflowAction;
  } | null>(null);
  const [workflowNote, setWorkflowNote] = useState("");
  const [production, setProduction] = useState<Production | null>(null);
  const [productions, setProductions] = useState<Production[]>([]);
  const [invitations, setInvitations] = useState<ProductionMember[]>([]);
  const [newProductionName, setNewProductionName] = useState("");
  const [renamingProductionId, setRenamingProductionId] = useState<
    string | null
  >(null);
  const [renameName, setRenameName] = useState("");
  const [members, setMembers] = useState<ProductionMember[]>([]);
  const [assignedArtistId, setAssignedArtistId] = useState("");
  const [memberUid, setMemberUid] = useState("");
  const [memberName, setMemberName] = useState("");
  const [memberRole, setMemberRole] = useState<"supervisor" | "artist">(
    "artist",
  );
  const [memberDepartment, setMemberDepartment] = useState<Department>("vfx");
  const [editingMemberUid, setEditingMemberUid] = useState<string | null>(null);
  const [memberToRemove, setMemberToRemove] = useState<ProductionMember | null>(
    null,
  );

  const loadTickets = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setTickets(await fetchTickets(await getAuthHeaders(), production?.id));
    } catch {
      setError("No se pudo conectar con el backend. Inténtalo de nuevo.");
    } finally {
      setLoading(false);
    }
  }, [getAuthHeaders, production]);

  useEffect(() => {
    let current = true;
    async function loadInitialTickets() {
      if (!user) return;
      try {
        const headers = await getAuthHeaders();
        const [availableProductions, pendingInvitations] = await Promise.all([
          fetchProductions(headers),
          fetchInvitations(headers),
        ]);
        if (current) {
          setTickets([]);
          setProduction(null);
          setProductions(availableProductions);
          setInvitations(pendingInvitations);
          setMembers([]);
        }
      } catch {
        if (current)
          setError("No se pudo conectar con el backend. Inténtalo de nuevo.");
      } finally {
        if (current) setLoading(false);
      }
    }
    void loadInitialTickets();
    return () => {
      current = false;
    };
  }, [user, getAuthHeaders]);

  async function updateTicket(
    ticketId: string,
    endpoint: string,
    body: object,
  ): Promise<boolean> {
    setProcessingId(ticketId);
    setError(null);
    try {
      if (!production) throw new Error("No hay una producción activa.");
      const response = await fetch(
        `${apiBaseUrl}/tickets/${ticketId}/${endpoint}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            ...(await getAuthHeaders()),
            "X-Production-Id": production.id,
          },
          body: JSON.stringify(body),
        },
      );
      const data = await response.json();
      if (!response.ok)
        throw new Error(data.detail ?? "No se pudo actualizar el ticket.");
      setTickets((current) =>
        current.map((ticket) =>
          ticket.id === ticketId ? (data as Ticket) : ticket,
        ),
      );
      return true;
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "No se pudo actualizar el ticket.",
      );
    } finally {
      setProcessingId(null);
    }
    return false;
  }

  async function addMember(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!production) return;
    setError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/productions/${production.id}/members`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(await getAuthHeaders()),
          },
          body: JSON.stringify({
            uid: memberUid.trim(),
            display_name: memberName.trim() || null,
            role: memberRole,
            department: memberRole === "artist" ? memberDepartment : null,
          }),
        },
      );
      const created = await response.json();
      if (!response.ok)
        throw new Error(created.detail ?? "No se pudo agregar al miembro.");
      setMembers((current) => [
        ...current.filter((member) => member.uid !== created.uid),
        created as ProductionMember,
      ]);
      setMemberUid("");
      setMemberName("");
      setMemberRole("artist");
      setMemberDepartment("vfx");
      setEditingMemberUid(null);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "No se pudo gestionar el miembro.",
      );
    }
  }

  function editMember(member: ProductionMember) {
    setEditingMemberUid(member.uid);
    setMemberUid(member.uid);
    setMemberName(member.display_name ?? "");
    setMemberRole(member.role === "supervisor" ? "supervisor" : "artist");
    setMemberDepartment(member.department ?? "vfx");
  }

  async function refreshTeam() {
    if (!production) return;
    try {
      setMembers(await fetchMembers(await getAuthHeaders(), production.id));
    } catch {
      setError("No se pudo actualizar el equipo.");
    }
  }

  async function removeMember(member: ProductionMember) {
    if (!production) return;
    setError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/productions/${production.id}/members/${encodeURIComponent(member.uid)}`,
        { method: "DELETE", headers: await getAuthHeaders() },
      );
      if (!response.ok) {
        const detail = await response.json();
        throw new Error(detail.detail ?? "No se pudo retirar al miembro.");
      }
      setMembers((current) =>
        current.filter((item) => item.uid !== member.uid),
      );
      await loadTickets();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "No se pudo retirar al miembro.",
      );
    }
  }

  async function openProduction(selected: Production) {
    if (!selected || selected.id === production?.id || !user) return;
    setLoading(true);
    setError(null);
    try {
      const headers = await getAuthHeaders();
      const [result, team] = await Promise.all([
        fetchTickets(headers, selected.id),
        fetchMembers(headers, selected.id),
      ]);
      setProduction(selected);
      setTickets(result);
      setMembers(team);
      const ownMembership = team.find((member) => member.uid === user.uid);
      if (ownMembership?.department)
        setDepartmentFilter(ownMembership.department);
      setView(ownMembership?.role === "artist" ? "production" : "decisions");
    } catch {
      setError("No se pudo cambiar de producción. Inténtalo de nuevo.");
    } finally {
      setLoading(false);
    }
  }

  async function selectProduction(productionId: string) {
    const selected = productions.find((item) => item.id === productionId);
    if (selected) await openProduction(selected);
  }

  async function createProduction(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = newProductionName.trim();
    if (!name) return;
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/productions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(await getAuthHeaders()),
        },
        body: JSON.stringify({ name }),
      });
      const created = await response.json();
      if (!response.ok)
        throw new Error(created.detail ?? "No se pudo crear la producción.");
      const next = created as Production;
      setProductions((current) => [next, ...current]);
      setNewProductionName("");
      await openProduction(next);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "No se pudo crear la producción.",
      );
    }
  }

  async function respondToInvitation(
    invitation: ProductionMember,
    decision: "accepted" | "declined",
  ) {
    if (!invitation.production_id) return;
    setError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/productions/${invitation.production_id}/invitation-response`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(await getAuthHeaders()),
          },
          body: JSON.stringify({ decision }),
        },
      );
      const result = await response.json();
      if (!response.ok)
        throw new Error(
          result.detail ?? "No se pudo responder a la invitación.",
        );
      setInvitations((current) =>
        current.filter(
          (item) => item.production_id !== invitation.production_id,
        ),
      );
      if (decision === "accepted")
        setProductions(await fetchProductions(await getAuthHeaders()));
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "No se pudo responder a la invitación.",
      );
    }
  }

  async function renameProduction(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!renamingProductionId || !renameName.trim()) return;
    setError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/productions/${renamingProductionId}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            ...(await getAuthHeaders()),
          },
          body: JSON.stringify({ name: renameName.trim() }),
        },
      );
      const updated = await response.json();
      if (!response.ok)
        throw new Error(
          updated.detail ?? "No se pudo renombrar la producción.",
        );
      setProductions((current) =>
        current.map((item) =>
          item.id === updated.id ? (updated as Production) : item,
        ),
      );
      if (production?.id === updated.id) setProduction(updated as Production);
      setRenamingProductionId(null);
      setRenameName("");
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "No se pudo renombrar la producción.",
      );
    }
  }

  function reviewTicket(ticketId: string, decision: "reject") {
    void updateTicket(ticketId, "review", { decision });
  }
  function startWork(ticket: Ticket) {
    void updateTicket(ticket.id, "work", { status: "in_progress" });
  }
  function openWorkflowAction(ticket: Ticket, type: WorkflowAction) {
    setWorkflowAction({ ticket, type });
    setWorkflowNote(
      type === "send_qc"
        ? (ticket.artist_note ?? "")
        : (ticket.supervisor_feedback ?? ""),
    );
    setAssignedArtistId("");
  }
  async function confirmWorkflowAction() {
    if (!workflowAction) return;
    const { ticket, type } = workflowAction;
    if (type === "return_for_rework" && !workflowNote.trim()) {
      setError(
        "Explica al artista qué debe corregir antes de devolver la tarea.",
      );
      return;
    }
    if (type === "assign" && !assignedArtistId) {
      setError("Selecciona un artista para asignar esta tarea.");
      return;
    }
    const artist = members.find((member) => member.uid === assignedArtistId);
    const ok =
      type === "assign"
        ? await updateTicket(ticket.id, "review", {
            decision: "approve",
            assigned_to_uid: assignedArtistId,
            assigned_to_name:
              artist?.display_name ?? artist?.email ?? "Artista",
          })
        : type === "send_qc"
          ? await updateTicket(ticket.id, "work", {
              status: "ready_for_qc",
              artist_note: workflowNote.trim() || null,
            })
          : await updateTicket(ticket.id, "quality-review", {
              decision: type === "complete" ? "approve" : "return_for_rework",
              supervisor_feedback: workflowNote.trim() || null,
            });
    if (ok) setWorkflowAction(null);
  }

  const pending = useMemo(
    () => tickets.filter((ticket) => ticket.status === "pending_review"),
    [tickets],
  );
  const qualityQueue = useMemo(
    () => tickets.filter((ticket) => ticket.status === "ready_for_qc"),
    [tickets],
  );
  const productionTickets = useMemo(
    () =>
      tickets.filter(
        (ticket) =>
          ticket.department === departmentFilter &&
          ["assigned", "approved", "in_progress"].includes(ticket.status),
      ),
    [tickets, departmentFilter],
  );
  const assigned = productionTickets.filter(
    (ticket) => ticket.status === "assigned" || ticket.status === "approved",
  );
  const inProgress = productionTickets.filter(
    (ticket) => ticket.status === "in_progress",
  );
  const completed = useMemo(
    () => tickets.filter((ticket) => ticket.status === "completed"),
    [tickets],
  );
  const rejected = useMemo(
    () => tickets.filter((ticket) => ticket.status === "rejected"),
    [tickets],
  );
  const activeMembers = useMemo(
    () =>
      members.filter(
        (member) =>
          member.membership_status !== "pending" &&
          member.membership_status !== "declined",
      ),
    [members],
  );
  const pendingMembers = useMemo(
    () => members.filter((member) => member.membership_status === "pending"),
    [members],
  );
  const canSupervise =
    production?.current_user_role === "producer" ||
    production?.current_user_role === "supervisor";
  const canWork = production?.current_user_role === "artist";

  if (authLoading)
    return (
      <main className="grid min-h-screen place-items-center bg-[#09111d] text-slate-300">
        Comprobando sesión…
      </main>
    );
  if (!configured)
    return (
      <main className="grid min-h-screen place-items-center bg-[#09111d] p-6 text-center text-slate-300">
        Firebase Authentication aún no está configurado para este entorno.
      </main>
    );
  if (!user)
    return (
      <main className="grid min-h-screen place-items-center bg-[#09111d] p-6 text-slate-100">
        <section className="w-full max-w-md rounded-2xl border border-slate-700 bg-[#101b2b] p-8 text-center">
          <p className="text-xs font-bold tracking-[0.22em] text-cyan-300">
            FRAMEFLOW / ACCESS CONTROL
          </p>
          <h1 className="mt-4 text-3xl font-semibold text-white">
            Sala de decisiones privada
          </h1>
          <p className="mt-3 text-sm leading-6 text-slate-400">
            Inicia sesión con tu cuenta de Google para ver y gestionar
            únicamente los tickets de tu producción.
          </p>
          <button
            onClick={() => void signIn()}
            className="mt-6 rounded-lg bg-cyan-300 px-4 py-2 text-sm font-bold text-cyan-950"
          >
            Continuar con Google
          </button>
        </section>
      </main>
    );

  if (!production)
    return (
      <main className="min-h-screen bg-[#09111d] px-5 py-8 text-slate-100 sm:px-8 lg:px-12">
        <section className="mx-auto max-w-6xl">
          <header className="mb-8 flex flex-wrap items-end justify-between gap-5 border-b border-slate-700/70 pb-7">
            <div>
              <p className="mb-3 text-xs font-bold tracking-[0.22em] text-cyan-300">
                FRAMEFLOW / PRODUCTIONS
              </p>
              <h1 className="text-4xl font-semibold tracking-tight text-white">
                Tus producciones
              </h1>
              <p className="mt-3 max-w-xl text-slate-400">
                Elige una producción, responde tus invitaciones o crea una nueva
                sala de postproducción.
              </p>
              <p className="mt-3 text-xs text-slate-500">
                Tu UID para invitaciones:{" "}
                <span className="font-mono text-cyan-300">{user.uid}</span>
              </p>
            </div>
            <div className="text-right text-xs text-slate-400">
              <p>{user.displayName ?? user.email}</p>
              <button
                onClick={() => void signOut()}
                className="mt-1 text-cyan-300 hover:underline"
              >
                Cerrar sesión
              </button>
            </div>
          </header>
          {error && (
            <div className="mb-6 rounded-lg border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
              {error}
            </div>
          )}
          <section className="mb-8 rounded-2xl border border-cyan-400/20 bg-[#101b2b] p-5">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="font-semibold text-white">Crear producción</h2>
                <p className="mt-1 text-sm text-slate-400">
                  Serás productor y podrás invitar al equipo.
                </p>
              </div>
            </div>
            <form
              onSubmit={createProduction}
              className="mt-4 flex flex-col gap-3 sm:flex-row"
            >
              <input
                required
                maxLength={100}
                value={newProductionName}
                onChange={(event) => setNewProductionName(event.target.value)}
                placeholder="Ej. Nebula · Postproducción"
                className="min-w-0 flex-1 rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm text-white outline-none focus:border-cyan-300"
              />
              <button className="rounded-lg bg-cyan-300 px-4 py-2 text-sm font-bold text-cyan-950">
                Crear producción
              </button>
            </form>
          </section>
          {invitations.length > 0 && (
            <section className="mb-8">
              <div className="mb-3 flex items-center gap-2">
                <span className="grid h-7 w-7 place-items-center rounded-full bg-amber-400/15 text-sm text-amber-300">
                  ●
                </span>
                <h2 className="font-semibold text-white">
                  Invitaciones pendientes ({invitations.length})
                </h2>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                {invitations.map((invitation) => (
                  <article
                    key={invitation.production_id}
                    className="rounded-xl border border-amber-400/30 bg-amber-400/5 p-5"
                  >
                    <p className="font-semibold text-white">
                      {invitation.production_name ?? "Producción compartida"}
                    </p>
                    <p className="mt-1 text-sm text-slate-400">
                      Rol propuesto: {invitation.role}
                      {invitation.department
                        ? ` · ${departmentLabel[invitation.department]}`
                        : ""}
                    </p>
                    <div className="mt-4 flex gap-2">
                      <button
                        onClick={() =>
                          void respondToInvitation(invitation, "accepted")
                        }
                        className="action-button approve"
                      >
                        Aceptar
                      </button>
                      <button
                        onClick={() =>
                          void respondToInvitation(invitation, "declined")
                        }
                        className="action-button reject"
                      >
                        Rechazar
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          )}
          <section>
            <h2 className="mb-3 font-semibold text-white">
              Producciones disponibles
            </h2>
            {loading ? (
              <p className="text-sm text-slate-400">Cargando producciones…</p>
            ) : productions.length === 0 ? (
              <p className="rounded-xl border border-dashed border-slate-700 p-6 text-sm text-slate-500">
                Aún no perteneces a ninguna producción. Crea una o espera una
                invitación.
              </p>
            ) : (
              <div className="grid gap-4 md:grid-cols-2">
                {productions.map((item) => (
                  <article
                    key={item.id}
                    className="rounded-xl border border-slate-700 bg-[#101b2b] p-5"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <button
                        onClick={() => void openProduction(item)}
                        className="text-left"
                      >
                        <p className="font-semibold text-white hover:text-cyan-300">
                          {item.name}
                        </p>
                        <p className="mt-1 text-sm capitalize text-slate-400">
                          Tu rol: {item.current_user_role}
                        </p>
                      </button>
                      {item.current_user_role === "producer" && (
                        <button
                          onClick={() => {
                            setRenamingProductionId(item.id);
                            setRenameName(item.name);
                          }}
                          className="text-xs text-cyan-300 hover:underline"
                        >
                          Renombrar
                        </button>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
          {renamingProductionId && (
            <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/75 p-4">
              <form
                onSubmit={renameProduction}
                className="w-full max-w-md rounded-2xl border border-slate-700 bg-[#101b2b] p-6"
              >
                <h2 className="text-lg font-semibold text-white">
                  Renombrar producción
                </h2>
                <input
                  autoFocus
                  required
                  maxLength={100}
                  value={renameName}
                  onChange={(event) => setRenameName(event.target.value)}
                  className="mt-4 w-full rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm text-white outline-none focus:border-cyan-300"
                />
                <div className="mt-5 flex justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setRenamingProductionId(null)}
                    className="action-button reject"
                  >
                    Cancelar
                  </button>
                  <button className="action-button approve">Guardar</button>
                </div>
              </form>
            </div>
          )}
        </section>
      </main>
    );

  return (
    <main className="min-h-screen bg-[#09111d] px-5 py-8 text-slate-100 sm:px-8 lg:px-12">
      <section className="mx-auto max-w-7xl">
        <header className="mb-7 flex flex-col justify-between gap-6 border-b border-slate-700/70 pb-7 md:flex-row md:items-end">
          <div>
            <p className="mb-3 text-xs font-bold tracking-[0.22em] text-cyan-300">
              FRAMEFLOW / POST-PRODUCTION CONTROL
            </p>
            <h1 className="text-4xl font-semibold tracking-tight text-white sm:text-5xl">
              Sala de decisiones
            </h1>
            <p className="mt-3 max-w-xl text-slate-400">
              Del análisis con Gemini al control de calidad del equipo de
              postproducción.
            </p>
          </div>
          <div className="flex items-end gap-4">
            <div className="hidden text-right text-xs text-slate-400 sm:block">
              <p>{user.displayName ?? user.email}</p>
              <button
                onClick={() => void signOut()}
                className="mt-1 text-cyan-300 hover:underline"
              >
                Cerrar sesión
              </button>
            </div>
            <div className="rounded-xl border border-cyan-400/20 bg-cyan-400/10 px-5 py-3">
              <p className="text-xs font-medium uppercase tracking-wider text-cyan-200">
                Por revisar
              </p>
              <p className="mt-1 text-3xl font-semibold text-white">
                {pending.length}
              </p>
            </div>
          </div>
        </header>
        <div className="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
          <aside className="h-fit rounded-2xl border border-slate-700/70 bg-[#101b2b] p-3">
            <button
              onClick={() => setProduction(null)}
              className="mb-3 flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm font-semibold text-cyan-300 hover:bg-cyan-400/10"
            >
              ⌂ <span>Producciones</span>
            </button>
            <label className="mb-4 block border-b border-slate-700 pb-4 text-xs text-slate-500">
              Producción activa
              <select
                aria-label="Producción activa"
                value={production.id}
                onChange={(event) => void selectProduction(event.target.value)}
                className="mt-2 w-full rounded-lg border border-slate-600 bg-[#162337] px-2 py-2 text-xs text-slate-200 outline-none"
              >
                <option value={production.id}>{production.name}</option>
                {productions
                  .filter((item) => item.id !== production.id)
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
              </select>
            </label>
            <nav className="space-y-1" aria-label="Vistas de FrameFlow">
              {canSupervise && (
                <button
                  onClick={() => setView("decisions")}
                  className={
                    view === "decisions"
                      ? "w-full rounded-lg bg-cyan-300 px-3 py-2 text-left text-sm font-bold text-cyan-950"
                      : "w-full rounded-lg px-3 py-2 text-left text-sm text-slate-300 hover:bg-slate-800"
                  }
                >
                  ◈ Sala de decisiones
                </button>
              )}
              <button
                onClick={() => setView("production")}
                className={
                  view === "production"
                    ? "w-full rounded-lg bg-cyan-300 px-3 py-2 text-left text-sm font-bold text-cyan-950"
                    : "w-full rounded-lg px-3 py-2 text-left text-sm text-slate-300 hover:bg-slate-800"
                }
              >
                ▣ {canWork ? "Mis tareas" : "Tareas"}
              </button>
              {production.current_user_role === "producer" && (
                <button
                  onClick={() => {
                    setView("team");
                    void refreshTeam();
                  }}
                  className={
                    view === "team"
                      ? "w-full rounded-lg bg-cyan-300 px-3 py-2 text-left text-sm font-bold text-cyan-950"
                      : "w-full rounded-lg px-3 py-2 text-left text-sm text-slate-300 hover:bg-slate-800"
                  }
                >
                  ♙ Gestionar equipo
                </button>
              )}
              <button
                onClick={() => setView("history")}
                className={
                  view === "history"
                    ? "w-full rounded-lg bg-cyan-300 px-3 py-2 text-left text-sm font-bold text-cyan-950"
                    : "w-full rounded-lg px-3 py-2 text-left text-sm text-slate-300 hover:bg-slate-800"
                }
              >
                ◷ Historial
              </button>
            </nav>
          </aside>
          <div className="min-w-0">
            {error && (
              <div className="mb-6 flex items-center justify-between gap-4 rounded-lg border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
                <span>{error}</span>
                <button
                  className="underline underline-offset-4"
                  onClick={() => void loadTickets()}
                >
                  Reintentar
                </button>
              </div>
            )}
            {view === "decisions" && production && canSupervise && (
              <>
                <DirectorNoteForm
                  productionId={production.id}
                  onCreated={(ticket) =>
                    setTickets((current) => [ticket as Ticket, ...current])
                  }
                />
                <section className="grid gap-6 lg:grid-cols-2">
                  <TicketColumn
                    title="Por revisar"
                    description="Notas que requieren decisión del supervisor"
                    tickets={pending}
                    loading={loading}
                  >
                    {(ticket) => (
                      <TicketCard key={ticket.id} ticket={ticket}>
                        <button
                          disabled={processingId === ticket.id}
                          onClick={() => reviewTicket(ticket.id, "reject")}
                          className="action-button reject"
                        >
                          Rechazar
                        </button>
                        <EditTicketDialog
                          productionId={production.id}
                          ticket={ticket}
                          onUpdated={(updated) =>
                            setTickets((current) =>
                              current.map((item) =>
                                item.id === updated.id ? updated : item,
                              ),
                            )
                          }
                        />
                        <button
                          disabled={processingId === ticket.id}
                          onClick={() => openWorkflowAction(ticket, "assign")}
                          className="action-button approve"
                        >
                          Aprobar y asignar
                        </button>
                      </TicketCard>
                    )}
                  </TicketColumn>
                  <TicketColumn
                    title="Control de calidad"
                    description="Trabajo enviado por artistas para revisión final"
                    tickets={qualityQueue}
                    loading={loading}
                  >
                    {(ticket) => (
                      <TicketCard key={ticket.id} ticket={ticket}>
                        <button
                          disabled={processingId === ticket.id}
                          onClick={() =>
                            openWorkflowAction(ticket, "return_for_rework")
                          }
                          className="action-button reject"
                        >
                          Devolver
                        </button>
                        <button
                          disabled={processingId === ticket.id}
                          onClick={() => openWorkflowAction(ticket, "complete")}
                          className="action-button approve"
                        >
                          Completar
                        </button>
                      </TicketCard>
                    )}
                  </TicketColumn>
                </section>
              </>
            )}
            {view === "production" && (
              <>
                <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-700/70 bg-[#101b2b] p-4">
                  <div>
                    <h2 className="font-semibold text-white">
                      {canWork ? "Mis tareas asignadas" : "Área de producción"}
                    </h2>
                    <p className="mt-1 text-xs text-slate-500">
                      {canWork
                        ? "Solo puedes avanzar las tareas asignadas a tu usuario."
                        : "Asigna y sigue el trabajo por departamento."}
                    </p>
                  </div>
                  {!canWork && (
                    <select
                      value={departmentFilter}
                      onChange={(event) =>
                        setDepartmentFilter(event.target.value as Department)
                      }
                      className="rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm text-slate-100"
                    >
                      <option value="vfx">VFX</option>
                      <option value="sound">Sonido</option>
                      <option value="color">Color</option>
                      <option value="editorial">Edición</option>
                    </select>
                  )}
                </div>
                <section className="grid gap-6 lg:grid-cols-3">
                  <TicketColumn
                    title="Asignadas"
                    description={`${departmentLabel[departmentFilter]} · listas para iniciar`}
                    tickets={assigned}
                    loading={loading}
                  >
                    {(ticket) => (
                      <TicketCard key={ticket.id} ticket={ticket}>
                        {canWork && (
                          <button
                            disabled={processingId === ticket.id}
                            onClick={() => startWork(ticket)}
                            className="action-button approve"
                          >
                            Iniciar trabajo
                          </button>
                        )}
                      </TicketCard>
                    )}
                  </TicketColumn>
                  <TicketColumn
                    title="En proceso"
                    description="El artista trabaja y luego envía a QC"
                    tickets={inProgress}
                    loading={loading}
                  >
                    {(ticket) => (
                      <TicketCard key={ticket.id} ticket={ticket}>
                        {canWork && (
                          <button
                            disabled={processingId === ticket.id}
                            onClick={() =>
                              openWorkflowAction(ticket, "send_qc")
                            }
                            className="action-button approve"
                          >
                            Enviar a QC
                          </button>
                        )}
                      </TicketCard>
                    )}
                  </TicketColumn>
                  <TicketColumn
                    title="Listas para QC"
                    description="Esperando revisión del supervisor"
                    tickets={qualityQueue.filter(
                      (ticket) => ticket.department === departmentFilter,
                    )}
                    loading={loading}
                  >
                    {(ticket) => <TicketCard key={ticket.id} ticket={ticket} />}
                  </TicketColumn>
                </section>
              </>
            )}
            {view === "team" && production.current_user_role === "producer" && (
              <section className="space-y-6">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-bold tracking-[0.2em] text-cyan-300">
                      PRODUCCIÓN / ADMINISTRACIÓN
                    </p>
                    <h2 className="mt-2 text-2xl font-semibold text-white">
                      Gestionar equipo
                    </h2>
                    <p className="mt-1 text-sm text-slate-400">
                      Invita personas, revisa respuestas y actualiza sus
                      responsabilidades.
                    </p>
                  </div>
                  <button
                    onClick={() => void refreshTeam()}
                    className="action-button reject"
                  >
                    Actualizar
                  </button>
                </div>
                <section className="rounded-2xl border border-slate-700/70 bg-[#101b2b] p-5">
                  <h3 className="font-semibold text-white">
                    {editingMemberUid ? "Editar miembro" : "Invitar integrante"}
                  </h3>
                  <p className="mt-1 text-xs text-slate-500">
                    El invitado verá una notificación y debe aceptar antes de
                    acceder a esta producción.
                  </p>
                  <form
                    onSubmit={addMember}
                    className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-5"
                  >
                    <input
                      required
                      readOnly={Boolean(editingMemberUid)}
                      value={memberUid}
                      onChange={(event) => setMemberUid(event.target.value)}
                      placeholder="UID de Firebase"
                      className="rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm read-only:opacity-70"
                    />
                    <input
                      value={memberName}
                      onChange={(event) => setMemberName(event.target.value)}
                      placeholder="Nombre (opcional)"
                      className="rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm"
                    />
                    <select
                      value={memberRole}
                      onChange={(event) =>
                        setMemberRole(
                          event.target.value as "supervisor" | "artist",
                        )
                      }
                      className="rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm"
                    >
                      <option value="artist">Artista</option>
                      <option value="supervisor">Supervisor</option>
                    </select>
                    <select
                      value={memberDepartment}
                      disabled={memberRole === "supervisor"}
                      onChange={(event) =>
                        setMemberDepartment(event.target.value as Department)
                      }
                      className="rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <option value="vfx">VFX</option>
                      <option value="sound">Sonido</option>
                      <option value="color">Color</option>
                      <option value="editorial">Edición</option>
                    </select>
                    <div className="flex gap-2">
                      <button className="flex-1 rounded-lg bg-cyan-300 px-4 py-2 text-sm font-bold text-cyan-950">
                        {editingMemberUid
                          ? "Guardar cambios"
                          : "Enviar invitación"}
                      </button>
                      {editingMemberUid && (
                        <button
                          type="button"
                          onClick={() => {
                            setEditingMemberUid(null);
                            setMemberUid("");
                            setMemberName("");
                            setMemberRole("artist");
                            setMemberDepartment("vfx");
                          }}
                          className="action-button reject"
                        >
                          Cancelar
                        </button>
                      )}
                    </div>
                  </form>
                </section>
                <section className="rounded-2xl border border-amber-400/25 bg-amber-400/5 p-5">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <h3 className="font-semibold text-white">
                        Invitaciones pendientes
                      </h3>
                      <p className="mt-1 text-xs text-slate-400">
                        Aún no tienen acceso a los tickets.
                      </p>
                    </div>
                    <span className="rounded-full bg-amber-400/15 px-2.5 py-1 text-xs font-semibold text-amber-300">
                      {pendingMembers.length}
                    </span>
                  </div>
                  <div className="mt-4 space-y-2">
                    {pendingMembers.length === 0 ? (
                      <p className="text-sm text-slate-500">
                        No hay invitaciones pendientes.
                      </p>
                    ) : (
                      pendingMembers.map((member) => (
                        <div
                          key={member.uid}
                          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-400/20 px-3 py-3 text-sm"
                        >
                          <div>
                            <p className="text-slate-200">
                              {member.display_name ??
                                member.email ??
                                member.uid}
                            </p>
                            <p className="mt-1 text-xs capitalize text-slate-400">
                              {member.role}
                              {member.department
                                ? ` · ${departmentLabel[member.department]}`
                                : ""}{" "}
                              · esperando respuesta
                            </p>
                          </div>
                          <div className="flex gap-2">
                            <button
                              onClick={() => editMember(member)}
                              className="action-button reject"
                            >
                              Editar
                            </button>
                            <button
                              onClick={() => setMemberToRemove(member)}
                              className="action-button reject"
                            >
                              Cancelar invitación
                            </button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </section>
                <section className="rounded-2xl border border-slate-700/70 bg-[#101b2b] p-5">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <h3 className="font-semibold text-white">
                        Miembros activos
                      </h3>
                      <p className="mt-1 text-xs text-slate-400">
                        Ya aceptaron y pueden trabajar según su rol.
                      </p>
                    </div>
                    <span className="rounded-full bg-cyan-400/10 px-2.5 py-1 text-xs font-semibold text-cyan-300">
                      {activeMembers.length}
                    </span>
                  </div>
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    {activeMembers.map((member) => (
                      <article
                        key={member.uid}
                        className="rounded-xl border border-slate-700 bg-[#162337] p-4"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="font-medium text-slate-100">
                              {member.display_name ??
                                member.email ??
                                member.uid}
                            </p>
                            <p className="mt-1 text-xs capitalize text-slate-400">
                              {member.role}
                              {member.department
                                ? ` · ${departmentLabel[member.department]}`
                                : ""}
                            </p>
                          </div>
                          {member.role !== "producer" && (
                            <div className="flex gap-3">
                              <button
                                onClick={() => editMember(member)}
                                className="text-xs text-cyan-300 hover:underline"
                              >
                                Gestionar rol
                              </button>
                              <button
                                onClick={() => setMemberToRemove(member)}
                                className="text-xs text-rose-300 hover:underline"
                              >
                                Retirar
                              </button>
                            </div>
                          )}
                        </div>
                      </article>
                    ))}
                  </div>
                </section>
              </section>
            )}
            {view === "history" && (
              <section className="grid gap-6 lg:grid-cols-2">
                <TicketColumn
                  title="Completadas"
                  description="Entregables aprobados por control de calidad"
                  tickets={completed}
                  loading={loading}
                >
                  {(ticket) => <TicketCard key={ticket.id} ticket={ticket} />}
                </TicketColumn>
                <TicketColumn
                  title="Rechazadas"
                  description="Notas que no avanzaron a producción"
                  tickets={rejected}
                  loading={loading}
                >
                  {(ticket) => <TicketCard key={ticket.id} ticket={ticket} />}
                </TicketColumn>
              </section>
            )}
          </div>
        </div>
        {memberToRemove && (
          <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/75 p-4">
            <section
              role="dialog"
              aria-modal="true"
              aria-labelledby="remove-member-title"
              className="w-full max-w-md rounded-2xl border border-rose-400/30 bg-[#101b2b] p-6 shadow-2xl"
            >
              <p className="text-xs font-bold tracking-[0.2em] text-rose-300">
                FRAMEFLOW / EQUIPO
              </p>
              <h2
                id="remove-member-title"
                className="mt-2 text-xl font-semibold text-white"
              >
                Retirar integrante
              </h2>
              <p className="mt-3 text-sm leading-6 text-slate-300">
                Vas a retirar a{" "}
                <span className="font-semibold text-white">
                  {memberToRemove.display_name ??
                    memberToRemove.email ??
                    memberToRemove.uid}
                </span>
                . Sus tareas activas volverán a <strong>Por revisar</strong>{" "}
                para que un supervisor las reasigne.
              </p>
              <div className="mt-6 flex justify-end gap-3">
                <button
                  onClick={() => setMemberToRemove(null)}
                  className="action-button reject"
                >
                  Cancelar
                </button>
                <button
                  onClick={() => {
                    void removeMember(memberToRemove);
                    setMemberToRemove(null);
                  }}
                  className="rounded-lg bg-rose-400 px-4 py-2 text-sm font-bold text-rose-950 hover:bg-rose-300"
                >
                  Retirar integrante
                </button>
              </div>
            </section>
          </div>
        )}
        {workflowAction && (
          <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/75 p-4">
            <section
              role="dialog"
              aria-modal="true"
              aria-labelledby="workflow-dialog-title"
              className="w-full max-w-lg rounded-2xl border border-slate-700 bg-[#101b2b] p-6 shadow-2xl"
            >
              <p className="text-xs font-bold tracking-[0.2em] text-cyan-300">
                FRAMEFLOW / WORKFLOW
              </p>
              <h2
                id="workflow-dialog-title"
                className="mt-2 text-xl font-semibold text-white"
              >
                {workflowAction.type === "assign"
                  ? "Asignar artista"
                  : workflowAction.type === "send_qc"
                    ? "Enviar a control de calidad"
                    : workflowAction.type === "complete"
                      ? "Completar tarea"
                      : "Devolver para corrección"}
              </h2>
              {workflowAction.type === "assign" ? (
                <label className="mt-5 block text-xs font-semibold uppercase tracking-wide text-slate-400">
                  Artista del equipo
                  <select
                    autoFocus
                    value={assignedArtistId}
                    onChange={(event) =>
                      setAssignedArtistId(event.target.value)
                    }
                    className="mt-2 w-full rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm text-white outline-none focus:border-cyan-300"
                  >
                    <option value="">Selecciona un artista…</option>
                    {members
                      .filter(
                        (member) =>
                          member.role === "artist" &&
                          member.department ===
                            workflowAction.ticket.department,
                      )
                      .map((member) => (
                        <option key={member.uid} value={member.uid}>
                          {member.display_name ?? member.email ?? member.uid}
                        </option>
                      ))}
                  </select>
                </label>
              ) : (
                <>
                  <p className="mt-2 text-sm text-slate-400">
                    {workflowAction.type === "send_qc"
                      ? "Añade contexto para que el supervisor pueda revisar el entregable."
                      : workflowAction.type === "complete"
                        ? "Puedes dejar una observación final antes de archivar el trabajo."
                        : "Describe claramente los cambios que el artista debe realizar."}
                  </p>
                  <label className="mt-5 block text-xs font-semibold uppercase tracking-wide text-slate-400">
                    {workflowAction.type === "send_qc"
                      ? "Nota del artista"
                      : "Feedback del supervisor"}
                    <textarea
                      autoFocus
                      value={workflowNote}
                      onChange={(event) => setWorkflowNote(event.target.value)}
                      maxLength={1000}
                      rows={4}
                      placeholder={
                        workflowAction.type === "return_for_rework"
                          ? "Ej. Corregir los bordes del micrófono junto al cabello."
                          : "Comentario opcional…"
                      }
                      className="mt-2 w-full rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm text-white outline-none placeholder:text-slate-500 focus:border-cyan-300"
                    />
                  </label>
                </>
              )}
              <div className="mt-6 flex justify-end gap-3">
                <button
                  onClick={() => setWorkflowAction(null)}
                  disabled={processingId === workflowAction.ticket.id}
                  className="action-button reject"
                >
                  Cancelar
                </button>
                <button
                  onClick={() => void confirmWorkflowAction()}
                  disabled={processingId === workflowAction.ticket.id}
                  className="action-button approve"
                >
                  {processingId === workflowAction.ticket.id
                    ? "Guardando…"
                    : workflowAction.type === "assign"
                      ? "Asignar tarea"
                      : workflowAction.type === "send_qc"
                        ? "Enviar a QC"
                        : workflowAction.type === "complete"
                          ? "Completar"
                          : "Devolver tarea"}
                </button>
              </div>
            </section>
          </div>
        )}
      </section>
    </main>
  );
}
