"use client";

import {
  ArrowLeft,
  Bell,
  History,
  LayoutDashboard,
  ListChecks,
  RefreshCw,
  Sparkles,
  UsersRound,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import DirectorNoteForm from "@/components/director-note-form";
import EditTicketDialog from "@/components/edit-ticket-dialog";
import LandingPage from "@/components/landing-page";
import MemberSearch from "@/components/member-search";
import ProfileMenu from "@/components/profile-menu";
import UserAvatar from "@/components/user-avatar";
import type { UserProfile } from "@/lib/profile-types";

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
type View = "decisions" | "production" | "history" | "team" | "dashboard";
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
  username?: string | null;
  photo_url?: string | null;
  has_custom_avatar?: boolean;
  profile_updated_at?: string | null;
  invited_by_uid?: string | null;
  invited_by?: UserProfile | null;
  membership_status?: "pending" | "accepted" | "declined";
};
type AppNotification = {
  id: string;
  type: "invitation" | "task_assigned" | "qc_ready" | "qc_returned" | "qc_completed";
  title: string;
  message: string;
  production_id?: string | null;
  ticket_id?: string | null;
  created_at: string;
  read_at?: string | null;
};
type TicketActivity = {
  id: string;
  ticket_id: string;
  actor_uid: string;
  actor_name?: string | null;
  action: string;
  detail?: string | null;
  created_at: string;
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
  delivery_link?: string | null;
  evidence_gcs_uri?: string | null;
  evidence_name?: string | null;
  evidence_content_type?: string | null;
  supervisor_feedback?: string | null;
  production_id?: string | null;
  assigned_to_uid?: string | null;
  assigned_to_name?: string | null;
};

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";
const activeProductionStorageKey = "frameflow:active-production";
const departmentLabel: Record<Department, string> = {
  vfx: "VFX",
  color: "Color",
  sound: "Sound",
  editorial: "Editorial",
};
const priorityLabel: Record<Priority, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};
const roleLabel: Record<ProductionMember["role"], string> = {
  producer: "Producer",
  supervisor: "Supervisor",
  artist: "Artist",
};
const statusLabel: Record<TicketStatus, string> = {
  pending_review: "Pending review",
  assigned: "Assigned",
  approved: "Assigned",
  in_progress: "In progress",
  ready_for_qc: "Ready for QC",
  completed: "Completed",
  rejected: "Rejected",
};

function memberDisplayName(member: ProductionMember): string {
  return member.display_name ?? member.username ?? member.uid;
}

function memberAvatarProfile(member: ProductionMember) {
  return {
    uid: member.uid,
    display_name: memberDisplayName(member),
    photo_url: member.photo_url,
    has_custom_avatar: Boolean(member.has_custom_avatar),
    updated_at: member.profile_updated_at ?? undefined,
  };
}

async function fetchTickets(
  headers: Record<string, string>,
  productionId?: string,
): Promise<Ticket[]> {
  const response = await fetch(`${apiBaseUrl}/tickets`, {
    headers: productionId
      ? { ...headers, "X-Production-Id": productionId }
      : headers,
  });
  if (!response.ok) throw new Error("Could not load the tickets.");
  return response.json();
}

async function fetchProductions(
  headers: Record<string, string>,
): Promise<Production[]> {
  const response = await fetch(`${apiBaseUrl}/productions`, { headers });
  if (!response.ok) throw new Error("Could not load your productions.");
  return response.json();
}

async function fetchInvitations(
  headers: Record<string, string>,
): Promise<ProductionMember[]> {
  const response = await fetch(`${apiBaseUrl}/productions/invitations`, {
    headers,
  });
  if (!response.ok) throw new Error("Could not load your invitations.");
  return response.json();
}

async function fetchNotifications(
  headers: Record<string, string>,
): Promise<AppNotification[]> {
  const response = await fetch(`${apiBaseUrl}/notifications`, { headers });
  if (!response.ok) throw new Error("Could not load your notifications.");
  return response.json();
}

async function fetchTicketActivity(
  headers: Record<string, string>,
  productionId: string,
  ticketId: string,
): Promise<TicketActivity[]> {
  const response = await fetch(`${apiBaseUrl}/tickets/${ticketId}/activity`, {
    headers: { ...headers, "X-Production-Id": productionId },
  });
  if (!response.ok) throw new Error("Could not load the task activity.");
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
    throw new Error("Could not load the production team.");
  return response.json();
}

async function fetchCurrentProfile(
  headers: Record<string, string>,
): Promise<UserProfile> {
  const response = await fetch(`${apiBaseUrl}/profiles/me`, { headers });
  if (!response.ok) throw new Error("Could not load your profile.");
  return response.json();
}

function TicketCard({
  ticket,
  children,
  onViewActivity,
  onRemoveEvidence,
  onRemoveDeliveryLink,
}: {
  ticket: Ticket;
  children?: React.ReactNode;
  onViewActivity?: (ticket: Ticket) => void;
  onRemoveEvidence?: (ticket: Ticket) => void;
  onRemoveDeliveryLink?: (ticket: Ticket) => void;
}) {
  return (
    <article className="workspace-ticket min-w-0 rounded-2xl border border-slate-700 bg-[#162337]/95 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="font-mono text-xs text-cyan-300">
          {ticket.shot_id}
        </span>
        <span className={`priority priority-${ticket.priority}`}>
          {priorityLabel[ticket.priority]}
        </span>
      </div>
      <p className="break-words text-sm leading-6 text-slate-200">{ticket.director_note}</p>
      <p className="mt-2 text-xs font-medium uppercase tracking-wide text-slate-400">
        {departmentLabel[ticket.department]} · {statusLabel[ticket.status]}
      </p>
      {ticket.artist_note && (
        <div className="mt-3 rounded-lg border border-cyan-400/20 bg-cyan-400/5 px-3 py-2 text-xs text-slate-300">
          <span className="font-semibold text-cyan-300">
            Artist note:{" "}
          </span>
          {ticket.artist_note}
        </div>
      )}
      {(ticket.delivery_link || ticket.evidence_gcs_uri) && (
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {ticket.delivery_link && (
            <>
              <a
                href={ticket.delivery_link}
                target="_blank"
                rel="noreferrer"
                className="rounded-md border border-cyan-400/30 px-2 py-1 font-semibold text-cyan-300 hover:bg-cyan-400/10"
              >
                Open delivery link
              </a>
              {onRemoveDeliveryLink && (
                <button
                  onClick={() => onRemoveDeliveryLink(ticket)}
                  className="rounded-md border border-rose-400/30 px-2 py-1 font-semibold text-rose-200 hover:bg-rose-400/10"
                >
                  Remove link
                </button>
              )}
            </>
          )}
          {ticket.evidence_gcs_uri && (
            <EvidenceButton ticket={ticket} />
          )}
          {ticket.evidence_gcs_uri && onRemoveEvidence && (
            <button
              onClick={() => onRemoveEvidence(ticket)}
              className="rounded-md border border-rose-400/30 px-2 py-1 font-semibold text-rose-200 hover:bg-rose-400/10"
            >
              Remove evidence
            </button>
          )}
        </div>
      )}
      {ticket.supervisor_feedback && (
        <div className="mt-3 rounded-lg border border-amber-400/20 bg-amber-400/5 px-3 py-2 text-xs text-slate-300">
          <span className="font-semibold text-amber-300">
            Supervisor feedback:{" "}
          </span>
          {ticket.supervisor_feedback}
        </div>
      )}
      {onViewActivity && (
        <button
          onClick={() => onViewActivity(ticket)}
          className="mt-3 text-xs font-semibold text-cyan-300 hover:underline"
        >
          View activity
        </button>
      )}
      {children && (
        <div className="mt-4 flex flex-wrap justify-end gap-2 border-t border-slate-700 pt-3">
          {children}
        </div>
      )}
    </article>
  );
}

function EvidenceButton({ ticket }: { ticket: Ticket }) {
  const { getAuthHeaders } = useAuth();
  const [opening, setOpening] = useState(false);

  async function openEvidence() {
    if (opening || !ticket.evidence_gcs_uri) return;
    setOpening(true);
    try {
      const response = await fetch(`${apiBaseUrl}/tickets/${ticket.id}/evidence`, {
        headers: ticket.production_id
          ? { ...(await getAuthHeaders()), "X-Production-Id": ticket.production_id }
          : await getAuthHeaders(),
      });
      if (!response.ok) throw new Error("Could not open the evidence.");
      const url = URL.createObjectURL(await response.blob());
      window.open(url, "_blank", "noopener,noreferrer");
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } finally {
      setOpening(false);
    }
  }

  return (
    <button onClick={() => void openEvidence()} className="rounded-md border border-violet-400/30 px-2 py-1 font-semibold text-violet-200 hover:bg-violet-400/10">
      {opening ? "Opening…" : `View evidence${ticket.evidence_name ? `: ${ticket.evidence_name}` : ""}`}
    </button>
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
    <section className="workspace-panel min-w-0 rounded-3xl border border-slate-700/70 bg-[#101b2b]/90 p-4 shadow-2xl shadow-black/10 backdrop-blur">
      <div className="mb-5 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-semibold text-white">{title}</h2>
          <p className="mt-1 text-xs text-slate-500">{description}</p>
        </div>
        <span className="rounded-full bg-slate-800 px-2.5 py-1 text-xs font-semibold text-slate-300">
          {tickets.length}
        </span>
      </div>
      <div className="max-h-[42rem] space-y-3 overflow-y-auto pr-1">
        {loading && [0, 1].map((item) => (
          <div key={item} className="workspace-skeleton h-32 rounded-2xl border border-slate-700/60" />
        ))}
        {!loading && tickets.length === 0 && (
          <p className="rounded-xl border border-dashed border-slate-700 p-5 text-sm text-slate-500">
            No tickets in this column.
          </p>
        )}
        {tickets.map(children)}
      </div>
    </section>
  );
}

function NotificationBell({
  notifications,
  open,
  onToggle,
  onRead,
  onReadAll,
}: {
  notifications: AppNotification[];
  open: boolean;
  onToggle: () => void;
  onRead: (notification: AppNotification) => void;
  onReadAll: () => void;
}) {
  const unread = notifications.filter((item) => !item.read_at).length;
  return (
    <div className="relative z-40" onKeyDown={(event) => { if (event.key === "Escape" && open) onToggle(); }}>
      <button
        onClick={onToggle}
        aria-label="View notifications"
        aria-haspopup="dialog"
        aria-expanded={open}
        className="group relative grid h-11 w-11 place-items-center rounded-full border border-slate-700/70 bg-slate-950/45 text-slate-300 shadow-lg backdrop-blur transition hover:-translate-y-0.5 hover:border-cyan-300/40 hover:text-cyan-200"
      >
        <Bell className="h-4 w-4 transition group-hover:rotate-12" />
        {unread > 0 && (
          <span className="absolute -right-2 -top-2 grid min-h-5 min-w-5 place-items-center rounded-full bg-cyan-300 px-1 text-[10px] font-bold text-cyan-950">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <>
        <button type="button" aria-label="Close notifications" className="fixed inset-0 z-[-1] cursor-default" onClick={onToggle} />
        <section role="dialog" aria-label="Notifications" className="absolute right-0 z-40 mt-2 w-[min(20rem,calc(100vw-2rem))] overflow-hidden rounded-xl border border-slate-700 bg-[#101b2b] shadow-2xl landing-rise">
          <div className="flex items-center justify-between border-b border-slate-700 px-4 py-3">
            <p className="text-sm font-semibold text-white">Notifications</p>
            {unread > 0 && (
              <button onClick={onReadAll} className="text-xs font-semibold text-cyan-300 hover:underline">
                Mark all as read
              </button>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto">
            {notifications.length === 0 ? (
              <p className="p-4 text-sm text-slate-500">You have no notifications.</p>
            ) : notifications.map((notification) => (
              <button
                key={notification.id}
                onClick={() => onRead(notification)}
                className={`w-full border-b border-slate-800 px-4 py-3 text-left hover:bg-slate-800/60 ${notification.read_at ? "opacity-60" : "bg-cyan-400/5"}`}
              >
                <p className="text-sm font-semibold text-slate-100">{notification.title}</p>
                <p className="mt-1 text-xs leading-5 text-slate-400">{notification.message}</p>
              </button>
            ))}
          </div>
        </section>
        </>
      )}
    </div>
  );
}

function Workspace() {
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
  const [deliveryLink, setDeliveryLink] = useState("");
  const [evidenceFile, setEvidenceFile] = useState<File | null>(null);
  const [evidenceToRemove, setEvidenceToRemove] = useState<Ticket | null>(null);
  const [deliveryLinkToRemove, setDeliveryLinkToRemove] = useState<Ticket | null>(null);
  const [production, setProduction] = useState<Production | null>(null);
  const [productions, setProductions] = useState<Production[]>([]);
  const [invitations, setInvitations] = useState<ProductionMember[]>([]);
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [newProductionName, setNewProductionName] = useState("");
  const [renamingProductionId, setRenamingProductionId] = useState<
    string | null
  >(null);
  const [renameName, setRenameName] = useState("");
  const [members, setMembers] = useState<ProductionMember[]>([]);
  const [currentProfile, setCurrentProfile] = useState<UserProfile | null>(null);
  const [assignedArtistId, setAssignedArtistId] = useState("");
  const [selectedMember, setSelectedMember] = useState<UserProfile | null>(null);
  const [memberRole, setMemberRole] = useState<"supervisor" | "artist">(
    "artist",
  );
  const [memberDepartment, setMemberDepartment] = useState<Department>("vfx");
  const [editingMemberUid, setEditingMemberUid] = useState<string | null>(null);
  const [memberToRemove, setMemberToRemove] = useState<ProductionMember | null>(
    null,
  );
  const [activityTicket, setActivityTicket] = useState<Ticket | null>(null);
  const [ticketActivity, setTicketActivity] = useState<TicketActivity[]>([]);
  const [activityLoading, setActivityLoading] = useState(false);
  const [historySearch, setHistorySearch] = useState("");
  const [historyDepartment, setHistoryDepartment] = useState<"all" | Department>("all");
  const [historyArtist, setHistoryArtist] = useState("all");
  const activeProductionId = production?.id;

  useEffect(() => {
    if (!user) return;
    let active = true;
    void (async () => {
      try {
        const profile = await fetchCurrentProfile(await getAuthHeaders());
        if (active) setCurrentProfile(profile);
      } catch {
        // The workspace remains usable with the verified Firebase identity.
      }
    })();
    return () => {
      active = false;
    };
  }, [getAuthHeaders, user]);

  const loadTickets = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setTickets(await fetchTickets(await getAuthHeaders(), production?.id));
    } catch {
      setError("Could not connect to the backend. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [getAuthHeaders, production]);

  const refreshNotifications = useCallback(async () => {
    if (!user) return;
    try {
      setNotifications(await fetchNotifications(await getAuthHeaders()));
    } catch {
      // Notifications should never prevent normal work if a transient request fails.
    }
  }, [getAuthHeaders, user]);

  useEffect(() => {
    let current = true;
    async function loadInitialTickets() {
      if (!user) return;
      try {
        const headers = await getAuthHeaders();
        const [availableProductions, pendingInvitations, userNotifications] = await Promise.all([
          fetchProductions(headers),
          fetchInvitations(headers),
          fetchNotifications(headers),
        ]);
        const rememberedId = window.localStorage.getItem(activeProductionStorageKey);
        const rememberedProduction = availableProductions.find(
          (item) => item.id === rememberedId,
        );
        const [rememberedTickets, rememberedMembers] = rememberedProduction
          ? await Promise.all([
              fetchTickets(headers, rememberedProduction.id),
              fetchMembers(headers, rememberedProduction.id),
            ])
          : [[], []];
        if (current) {
          setTickets(rememberedTickets);
          setProduction(rememberedProduction ?? null);
          setProductions(availableProductions);
          setInvitations(pendingInvitations);
          setNotifications(userNotifications);
          setMembers(rememberedMembers);
          if (rememberedProduction) {
            const ownMembership = rememberedMembers.find(
              (member) => member.uid === user.uid,
            );
            if (ownMembership?.department)
              setDepartmentFilter(ownMembership.department);
            setView(ownMembership?.role === "artist" ? "production" : "decisions");
          } else {
            window.localStorage.removeItem(activeProductionStorageKey);
          }
        }
      } catch {
        if (current)
          setError("Could not connect to the backend. Please try again.");
      } finally {
        if (current) setLoading(false);
      }
    }
    void loadInitialTickets();
    return () => {
      current = false;
    };
  }, [user, getAuthHeaders]);

  useEffect(() => {
    if (!user) return;
    const interval = window.setInterval(() => void refreshNotifications(), 30_000);
    return () => window.clearInterval(interval);
  }, [user, refreshNotifications]);

  useEffect(() => {
    if (!user) return;
    let current = true;
    async function refreshWorkspace() {
      try {
        const headers = await getAuthHeaders();
        const [availableProductions, pendingInvitations] = await Promise.all([
          fetchProductions(headers),
          fetchInvitations(headers),
        ]);
        if (!current) return;
        setProductions(availableProductions);
        setInvitations(pendingInvitations);
        if (!activeProductionId) return;
        const activeProduction = availableProductions.find(
          (item) => item.id === activeProductionId,
        );
        if (!activeProduction) {
          window.localStorage.removeItem(activeProductionStorageKey);
          setProduction(null);
          setTickets([]);
          setMembers([]);
          return;
        }
        const [freshTickets, freshMembers] = await Promise.all([
          fetchTickets(headers, activeProduction.id),
          fetchMembers(headers, activeProduction.id),
        ]);
        if (current) {
          setProduction(activeProduction);
          setTickets(freshTickets);
          setMembers(freshMembers);
        }
      } catch {
        // The next poll retries; current data remains usable during a transient failure.
      }
    }
    const interval = window.setInterval(() => void refreshWorkspace(), 10_000);
    return () => {
      current = false;
      window.clearInterval(interval);
    };
  }, [user, getAuthHeaders, activeProductionId]);

  async function markNotificationRead(notification: AppNotification) {
    if (notification.read_at) return;
    try {
      const response = await fetch(`${apiBaseUrl}/notifications/${notification.id}/read`, {
        method: "PATCH",
        headers: await getAuthHeaders(),
      });
      const updated = await response.json();
      if (response.ok) setNotifications((current) => current.map((item) => item.id === notification.id ? updated as AppNotification : item));
    } catch {
      // The inbox remains readable even when marking an item fails.
    }
  }

  async function markAllNotificationsRead() {
    try {
      const response = await fetch(`${apiBaseUrl}/notifications/read-all`, { method: "PATCH", headers: await getAuthHeaders() });
      if (response.ok) setNotifications((current) => current.map((item) => ({ ...item, read_at: new Date().toISOString() })));
    } catch {
      // Retry on the next interaction or polling interval.
    }
  }

  async function openNotification(notification: AppNotification) {
    await markNotificationRead(notification);
    if (!notification.production_id) return;
    const target = productions.find(
      (item) => item.id === notification.production_id,
    );
    if (target) {
      setNotificationsOpen(false);
      await openProduction(target);
    }
  }

  async function openTicketActivity(ticket: Ticket) {
    if (!production) return;
    setActivityTicket(ticket);
    setActivityLoading(true);
    setTicketActivity([]);
    try {
      setTicketActivity(
        await fetchTicketActivity(await getAuthHeaders(), production.id, ticket.id),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load the activity.");
    } finally {
      setActivityLoading(false);
    }
  }

  async function updateTicket(
    ticketId: string,
    endpoint: string,
    body: object,
  ): Promise<boolean> {
    setProcessingId(ticketId);
    setError(null);
    try {
      if (!production) throw new Error("There is no active production.");
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
        throw new Error(data.detail ?? "Could not update the ticket.");
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
          : "Could not update the ticket.",
      );
    } finally {
      setProcessingId(null);
    }
    return false;
  }

  async function addMember(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!production || !selectedMember) {
      setError("Select a person from the results before continuing.");
      return;
    }
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
            uid: selectedMember.uid,
            role: memberRole,
            department: memberRole === "artist" ? memberDepartment : null,
          }),
        },
      );
      const created = await response.json();
      if (!response.ok)
        throw new Error(created.detail ?? "Could not add the member.");
      setMembers((current) => [
        ...current.filter((member) => member.uid !== created.uid),
        created as ProductionMember,
      ]);
      setSelectedMember(null);
      setMemberRole("artist");
      setMemberDepartment("vfx");
      setEditingMemberUid(null);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not manage the member.",
      );
    }
  }

  function editMember(member: ProductionMember) {
    setEditingMemberUid(member.uid);
    setSelectedMember({
      uid: member.uid,
      username: member.username ?? member.uid.slice(0, 12),
      display_name: member.display_name ?? "FrameFlow member",
      photo_url: member.photo_url,
      has_custom_avatar: Boolean(member.has_custom_avatar),
      created_at: "",
      updated_at: member.profile_updated_at ?? "",
    });
    setMemberRole(member.role === "supervisor" ? "supervisor" : "artist");
    setMemberDepartment(member.department ?? "vfx");
  }

  async function refreshTeam() {
    if (!production) return;
    try {
      setMembers(await fetchMembers(await getAuthHeaders(), production.id));
    } catch {
      setError("Could not refresh the team.");
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
        throw new Error(detail.detail ?? "Could not remove the member.");
      }
      setMembers((current) =>
        current.filter((item) => item.uid !== member.uid),
      );
      await loadTickets();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not remove the member.",
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
      window.localStorage.setItem(activeProductionStorageKey, selected.id);
      setTickets(result);
      setMembers(team);
      const ownMembership = team.find((member) => member.uid === user.uid);
      if (ownMembership?.department)
        setDepartmentFilter(ownMembership.department);
      setView(ownMembership?.role === "artist" ? "production" : "decisions");
    } catch {
      setError("Could not switch productions. Please try again.");
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
        throw new Error(created.detail ?? "Could not create the production.");
      const next = created as Production;
      setProductions((current) => [next, ...current]);
      setNewProductionName("");
      await openProduction(next);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not create the production.",
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
          result.detail ?? "Could not respond to the invitation.",
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
          : "Could not respond to the invitation.",
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
          updated.detail ?? "Could not rename the production.",
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
          : "Could not rename the production.",
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
    setDeliveryLink(type === "send_qc" ? (ticket.delivery_link ?? "") : "");
    setEvidenceFile(null);
    setAssignedArtistId("");
  }
  async function uploadEvidence(ticketId: string, file: File): Promise<boolean> {
    if (!production) return false;
    const form = new FormData();
    form.append("evidence", file);
    const response = await fetch(`${apiBaseUrl}/tickets/${ticketId}/evidence`, {
      method: "POST",
      headers: { ...(await getAuthHeaders()), "X-Production-Id": production.id },
      body: form,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail ?? "Could not upload the evidence.");
    setTickets((current) => current.map((item) => item.id === ticketId ? (data as Ticket) : item));
    return true;
  }
  async function removeEvidence(ticket: Ticket) {
    if (!production) return;
    setProcessingId(ticket.id);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/tickets/${ticket.id}/evidence`, {
        method: "DELETE",
        headers: { ...(await getAuthHeaders()), "X-Production-Id": production.id },
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? "Could not remove the evidence.");
      setTickets((current) => current.map((item) => item.id === ticket.id ? (data as Ticket) : item));
      setEvidenceToRemove(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not remove the evidence.");
    } finally {
      setProcessingId(null);
    }
  }
  async function removeDeliveryLink(ticket: Ticket) {
    if (!production) return;
    setProcessingId(ticket.id);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/tickets/${ticket.id}/delivery-link`, {
        method: "DELETE",
        headers: { ...(await getAuthHeaders()), "X-Production-Id": production.id },
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? "Could not remove the link.");
      setTickets((current) => current.map((item) => item.id === ticket.id ? (data as Ticket) : item));
      setDeliveryLinkToRemove(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not remove the link.");
    } finally {
      setProcessingId(null);
    }
  }
  async function confirmWorkflowAction() {
    if (!workflowAction) return;
    const { ticket, type } = workflowAction;
    if (type === "return_for_rework" && !workflowNote.trim()) {
      setError(
        "Explain what the artist must correct before returning the task.",
      );
      return;
    }
    if (type === "assign" && !assignedArtistId) {
      setError("Select an artist to assign this task.");
      return;
    }
    const artist = members.find((member) => member.uid === assignedArtistId);
    try {
    if (type === "send_qc" && evidenceFile) await uploadEvidence(ticket.id, evidenceFile);
    const ok =
      type === "assign"
        ? await updateTicket(ticket.id, "review", {
            decision: "approve",
            assigned_to_uid: assignedArtistId,
            assigned_to_name:
              artist ? memberDisplayName(artist) : "Artist",
          })
        : type === "send_qc"
          ? await updateTicket(ticket.id, "work", {
              status: "ready_for_qc",
              artist_note: workflowNote.trim() || null,
              delivery_link: deliveryLink.trim() || null,
            })
          : await updateTicket(ticket.id, "quality-review", {
              decision: type === "complete" ? "approve" : "return_for_rework",
              supervisor_feedback: workflowNote.trim() || null,
            });
    if (ok) setWorkflowAction(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save the delivery.");
    }
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
  const activeWork = useMemo(
    () =>
      tickets.filter((ticket) =>
        ["assigned", "approved", "in_progress", "ready_for_qc"].includes(
          ticket.status,
        ),
      ),
    [tickets],
  );
  const historyTickets = useMemo(
    () =>
      tickets.filter((ticket) => {
        if (!["completed", "rejected"].includes(ticket.status)) return false;
        if (historyDepartment !== "all" && ticket.department !== historyDepartment)
          return false;
        if (historyArtist !== "all" && ticket.assigned_to_uid !== historyArtist)
          return false;
        const query = historySearch.trim().toLowerCase();
        return !query || `${ticket.shot_id} ${ticket.director_note} ${ticket.assigned_to_name ?? ""}`.toLowerCase().includes(query);
      }),
    [tickets, historyDepartment, historyArtist, historySearch],
  );
  const filteredCompleted = useMemo(
    () => historyTickets.filter((ticket) => ticket.status === "completed"),
    [historyTickets],
  );
  const filteredRejected = useMemo(
    () => historyTickets.filter((ticket) => ticket.status === "rejected"),
    [historyTickets],
  );
  const departmentMetrics = useMemo(
    () =>
      (Object.keys(departmentLabel) as Department[]).map((department) => {
        const departmentTickets = tickets.filter(
          (ticket) => ticket.department === department,
        );
        return {
          department,
          total: departmentTickets.length,
          active: departmentTickets.filter((ticket) =>
            ["assigned", "approved", "in_progress", "ready_for_qc"].includes(
              ticket.status,
            ),
          ).length,
          completed: departmentTickets.filter(
            (ticket) => ticket.status === "completed",
          ).length,
        };
      }),
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
        Checking your session…
      </main>
    );
  if (!configured)
    return (
      <main className="grid min-h-screen place-items-center bg-[#09111d] p-6 text-center text-slate-300">
        Firebase Authentication is not configured for this environment yet.
      </main>
    );
  if (!user)
    return <LandingPage onSignIn={signIn} />;

  const profile: UserProfile = currentProfile ?? {
    uid: user.uid,
    username:
      user.email
        ?.split("@", 1)[0]
        .toLowerCase()
        .replace(/[^a-z0-9._-]/g, "-") || `user-${user.uid.slice(-6).toLowerCase()}`,
    display_name: user.displayName ?? user.email?.split("@", 1)[0] ?? "FrameFlow user",
    photo_url: user.photoURL,
    has_custom_avatar: false,
    created_at: "",
    updated_at: "",
  };
  const workspaceCopy: Record<View, { eyebrow: string; title: string; description: string }> = {
    dashboard: {
      eyebrow: "PRODUCTION / LIVE PULSE",
      title: "Production overview",
      description: "Team progress, workloads, and bottlenecks at a glance.",
    },
    decisions: {
      eyebrow: "FRAMEFLOW / CREATIVE CONTROL",
      title: "Decision room",
      description: "From Gemini analysis to a clear, assignable human decision.",
    },
    production: {
      eyebrow: "PRODUCTION / EXECUTION",
      title: canWork ? "My workspace" : "Production area",
      description: canWork
        ? "Your tasks, deliveries, and reviews without operational noise."
        : "Track creative work from assignment through quality control.",
    },
    team: {
      eyebrow: "PRODUCTION / PEOPLE",
      title: "Production team",
      description: "Invite verified identities and define how each person participates.",
    },
    history: {
      eyebrow: "PRODUCTION / TRACEABILITY",
      title: "Delivery history",
      description: "Every completion, rejection, and decision keeps its context.",
    },
  };

  if (!production)
    return (
      <main className="workspace-shell relative min-h-screen overflow-x-clip bg-[#09111d] px-5 py-8 text-slate-100 sm:px-8 lg:px-12">
        <div className="workspace-grid pointer-events-none absolute inset-0" />
        <div className="workspace-orb workspace-orb-one pointer-events-none absolute" />
        <div className="workspace-orb workspace-orb-two pointer-events-none absolute" />
        <section className="relative mx-auto max-w-6xl">
          <header className="mb-8 flex flex-wrap items-end justify-between gap-5 border-b border-slate-700/70 pb-7">
            <div>
              <p className="mb-3 text-xs font-bold tracking-[0.22em] text-cyan-300">
                FRAMEFLOW / PRODUCTIONS
              </p>
              <h1 className="text-4xl font-semibold tracking-tight text-white">
                Your productions
              </h1>
              <p className="mt-3 max-w-xl text-slate-400">
                Choose a production, respond to your invitations, or create a new
                post-production room.
              </p>
              <p className="mt-3 text-xs text-slate-500">
                Your identity:{" "}
                <span className="font-semibold text-cyan-300">@{profile.username}</span>
                <span className="ml-2">· copy your UID from your profile</span>
              </p>
            </div>
            <div className="flex items-center gap-3">
              <NotificationBell
                notifications={notifications}
                open={notificationsOpen}
                onToggle={() => setNotificationsOpen((current) => !current)}
                onRead={(notification) => void openNotification(notification)}
                onReadAll={() => void markAllNotificationsRead()}
              />
              <ProfileMenu profile={profile} apiBaseUrl={apiBaseUrl} getAuthHeaders={getAuthHeaders} onProfileChange={setCurrentProfile} onSignOut={signOut} />
            </div>
          </header>
          {error && (
            <div className="mb-6 rounded-lg border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
              {error}
            </div>
          )}
          <section className="workspace-panel mb-8 rounded-2xl border border-cyan-400/20 bg-[#101b2b]/90 p-5 backdrop-blur">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="font-semibold text-white">Create production</h2>
                <p className="mt-1 text-sm text-slate-400">
                  You will be the producer and can invite your team.
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
                placeholder="E.g. Nebula · Post-production"
                className="min-w-0 flex-1 rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm text-white outline-none focus:border-cyan-300"
              />
              <button className="rounded-lg bg-cyan-300 px-4 py-2 text-sm font-bold text-cyan-950">
                Create production
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
                  Pending invitations ({invitations.length})
                </h2>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                {invitations.map((invitation) => (
                  <article
                    key={invitation.production_id}
                    className="workspace-card overflow-hidden rounded-2xl border border-amber-400/30 bg-amber-400/5"
                  >
                    <div className="border-b border-amber-300/10 bg-gradient-to-r from-amber-300/10 via-transparent to-cyan-300/5 p-5">
                      <p className="text-[10px] font-bold tracking-[.2em] text-amber-300">PRODUCTION INVITATION</p>
                      <p className="mt-2 text-lg font-semibold text-white">
                        {invitation.production_name ?? "Shared production"}
                      </p>
                      <p className="mt-1 text-sm text-slate-400">
                        You have been invited as <span className="font-semibold text-slate-200">{roleLabel[invitation.role]}</span>
                        {invitation.department
                          ? ` · ${departmentLabel[invitation.department]}`
                          : ""}
                      </p>
                    </div>
                    <div className="p-5">
                      {invitation.invited_by ? (
                        <div className="flex items-center gap-3 rounded-xl border border-white/5 bg-black/15 p-3">
                          <UserAvatar profile={invitation.invited_by} apiBaseUrl={apiBaseUrl} getAuthHeaders={getAuthHeaders} size="lg" />
                          <div className="min-w-0">
                            <p className="text-[10px] font-bold tracking-[.14em] text-slate-500">INVITED BY</p>
                            <p className="mt-1 truncate text-sm font-semibold text-white">{invitation.invited_by.display_name}</p>
                            <p className="truncate text-xs text-cyan-300">@{invitation.invited_by.username}</p>
                          </div>
                        </div>
                      ) : (
                        <p className="rounded-xl border border-white/5 bg-black/15 p-3 text-xs text-slate-400">Invitation sent by this production&apos;s producer.</p>
                      )}
                    <div className="mt-4 flex gap-2">
                      <button
                        onClick={() =>
                          void respondToInvitation(invitation, "accepted")
                        }
                        className="action-button approve"
                      >
                        Accept
                      </button>
                      <button
                        onClick={() =>
                          void respondToInvitation(invitation, "declined")
                        }
                        className="action-button reject"
                      >
                        Decline
                      </button>
                    </div>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          )}
          <section>
            <h2 className="mb-3 font-semibold text-white">
              Available productions
            </h2>
            {loading ? (
              <p className="text-sm text-slate-400">Loading productions…</p>
            ) : productions.length === 0 ? (
              <p className="rounded-xl border border-dashed border-slate-700 p-6 text-sm text-slate-500">
                You do not belong to any production yet. Create one or wait for
                an invitation.
              </p>
            ) : (
              <div className="grid gap-4 md:grid-cols-2">
                {productions.map((item) => (
                  <article
                    key={item.id}
                    className="workspace-card group rounded-2xl border border-slate-700 bg-[#101b2b]/90 p-5 backdrop-blur"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <button
                        onClick={() => void openProduction(item)}
                        className="min-w-0 flex-1 text-left"
                      >
                        <p className="font-semibold text-white transition group-hover:text-cyan-300">
                          {item.name}
                        </p>
                        <p className="mt-1 text-sm capitalize text-slate-400">
                          Your role: {item.current_user_role ? roleLabel[item.current_user_role] : "Member"}
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
                          Rename
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
                  Rename production
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
                    Cancel
                  </button>
                  <button className="action-button approve">Save</button>
                </div>
              </form>
            </div>
          )}
        </section>
      </main>
    );

  return (
    <main className="workspace-shell relative min-h-screen overflow-x-clip bg-[#09111d] px-4 py-5 text-slate-100 sm:px-8 sm:py-8 lg:px-12">
      <div className="workspace-grid pointer-events-none absolute inset-0" />
      <div className="workspace-orb workspace-orb-one pointer-events-none absolute" />
      <div className="workspace-orb workspace-orb-two pointer-events-none absolute" />
      <section className="relative mx-auto max-w-7xl">
        <header className="mb-7 flex flex-col justify-between gap-6 border-b border-slate-700/70 pb-7 md:flex-row md:items-end">
          <div key={`header:${view}`} className="workspace-view">
            <p className="mb-3 text-xs font-bold tracking-[0.22em] text-cyan-300">
              {workspaceCopy[view].eyebrow}
            </p>
            <h1 className="text-4xl font-semibold tracking-tight text-white sm:text-5xl">
              {workspaceCopy[view].title}
            </h1>
            <p className="mt-3 max-w-xl text-slate-400">
              {workspaceCopy[view].description}
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-3 sm:gap-4">
            <NotificationBell
              notifications={notifications}
              open={notificationsOpen}
              onToggle={() => setNotificationsOpen((current) => !current)}
              onRead={(notification) => void openNotification(notification)}
              onReadAll={() => void markAllNotificationsRead()}
            />
            <ProfileMenu profile={profile} apiBaseUrl={apiBaseUrl} getAuthHeaders={getAuthHeaders} onProfileChange={setCurrentProfile} onSignOut={signOut} />
            <div className="workspace-metric rounded-2xl border border-cyan-400/20 bg-cyan-400/10 px-5 py-3 backdrop-blur">
              <p className="text-xs font-medium uppercase tracking-wider text-cyan-200">
                Pending review
              </p>
              <p className="mt-1 text-3xl font-semibold text-white">
                {pending.length}
              </p>
            </div>
          </div>
        </header>
        <div className="grid gap-6 lg:grid-cols-[238px_minmax(0,1fr)]">
          <aside className="workspace-sidebar h-fit rounded-3xl border border-slate-700/70 bg-[#101b2b]/88 p-3 backdrop-blur-xl lg:sticky lg:top-6">
            <button
              onClick={() => {
                window.localStorage.removeItem(activeProductionStorageKey);
                setProduction(null);
              }}
              className="workspace-nav-button mb-3 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-semibold text-cyan-300"
            >
              <ArrowLeft className="h-4 w-4" /> <span>Productions</span>
            </button>
            <label className="mb-4 block border-b border-slate-700 pb-4 text-xs text-slate-500">
              Active production
              <select
                aria-label="Active production"
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
            <nav className="space-y-1" aria-label="FrameFlow views">
              {production.current_user_role === "producer" && (
                <button
                  onClick={() => setView("dashboard")}
                  className={
                    view === "dashboard"
                      ? "workspace-nav-button active w-full"
                      : "workspace-nav-button w-full"
                  }
                >
                  <LayoutDashboard className="h-4 w-4" /> Overview
                </button>
              )}
              {canSupervise && (
                <button
                  onClick={() => setView("decisions")}
                  className={
                    view === "decisions"
                      ? "workspace-nav-button active w-full"
                      : "workspace-nav-button w-full"
                  }
                >
                  <Sparkles className="h-4 w-4" /> Decision room
                </button>
              )}
              <button
                onClick={() => setView("production")}
                className={
                  view === "production"
                    ? "workspace-nav-button active w-full"
                    : "workspace-nav-button w-full"
                }
              >
                <ListChecks className="h-4 w-4" /> {canWork ? "My tasks" : "Tasks"}
              </button>
              {production.current_user_role === "producer" && (
                <button
                  onClick={() => {
                    setView("team");
                    void refreshTeam();
                  }}
                  className={
                    view === "team"
                      ? "workspace-nav-button active w-full"
                      : "workspace-nav-button w-full"
                  }
                >
                  <UsersRound className="h-4 w-4" /> Manage team
                </button>
              )}
              <button
                onClick={() => setView("history")}
                className={
                  view === "history"
                    ? "workspace-nav-button active w-full"
                    : "workspace-nav-button w-full"
                }
              >
                <History className="h-4 w-4" /> History
              </button>
            </nav>
          </aside>
          <div key={`${production.id}:${view}`} className="workspace-view min-w-0">
            {error && (
              <div role="alert" className="mb-6 flex items-center justify-between gap-4 rounded-lg border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
                <span className="min-w-0 break-words">{error}</span>
                <div className="flex shrink-0 items-center gap-3">
                <button
                  className="underline underline-offset-4"
                  onClick={() => void loadTickets()}
                >
                  Retry
                </button>
                  <button aria-label="Close error message" onClick={() => setError(null)} className="text-lg leading-none hover:text-white">×</button>
                </div>
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
                    title="Pending review"
                    description="Notes that require a supervisor decision"
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
                          Reject
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
                          Approve and assign
                        </button>
                      </TicketCard>
                    )}
                  </TicketColumn>
                  <TicketColumn
                    title="Quality control"
                    description="Work submitted by artists for final review"
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
                          Return
                        </button>
                        <button
                          disabled={processingId === ticket.id}
                          onClick={() => openWorkflowAction(ticket, "complete")}
                          className="action-button approve"
                        >
                          Complete
                        </button>
                      </TicketCard>
                    )}
                  </TicketColumn>
                </section>
              </>
            )}
            {view === "dashboard" && production.current_user_role === "producer" && (
              <section className="space-y-6">
                <div>
                  <p className="text-xs font-bold tracking-[0.2em] text-cyan-300">
                    PRODUCTION / OVERVIEW
                  </p>
                  <h2 className="mt-2 text-2xl font-semibold text-white">
                    Status of {production.name}
                  </h2>
                  <p className="mt-1 text-sm text-slate-400">
                    Current workload and team progress in real time.
                  </p>
                </div>
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  {[
                    ["Total", tickets.length, "All tasks"],
                    ["Pending review", pending.length, "Require a decision"],
                    ["In progress", activeWork.length, "Assigned, in progress, or in QC"],
                    ["Completed", completed.length, "Approved by QC"],
                  ].map(([label, value, description]) => (
                    <article key={label as string} className="workspace-card rounded-2xl border border-slate-700 bg-[#101b2b]/90 p-5">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</p>
                      <p className="mt-2 text-3xl font-semibold text-white">{value}</p>
                      <p className="mt-1 text-xs text-slate-500">{description}</p>
                    </article>
                  ))}
                </div>
                <section className="workspace-panel rounded-3xl border border-slate-700/70 bg-[#101b2b]/90 p-5">
                  <h3 className="font-semibold text-white">Progress by department</h3>
                  <div className="mt-5 space-y-5">
                    {departmentMetrics.map((metric) => {
                      const completion = metric.total ? Math.round((metric.completed / metric.total) * 100) : 0;
                      return (
                        <div key={metric.department}>
                          <div className="flex justify-between gap-4 text-sm">
                            <p className="font-medium text-slate-200">{departmentLabel[metric.department]}</p>
                            <p className="text-slate-400">{metric.completed}/{metric.total} completed · {metric.active} active</p>
                          </div>
                          <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-800">
                            <div className="h-full rounded-full bg-cyan-300 transition-all" style={{ width: `${completion}%` }} />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </section>
                <section className="workspace-panel rounded-3xl border border-slate-700/70 bg-[#101b2b]/90 p-5">
                  <h3 className="font-semibold text-white">Artist workload</h3>
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    {activeMembers.filter((member) => member.role === "artist").length === 0 ? (
                      <p className="text-sm text-slate-500">There are no active artists in this production yet.</p>
                    ) : activeMembers.filter((member) => member.role === "artist").map((member) => {
                      const assigned = activeWork.filter((ticket) => ticket.assigned_to_uid === member.uid).length;
                      return <article key={member.uid} className="workspace-card flex items-center gap-3 rounded-xl border border-slate-700 bg-[#162337] px-4 py-3"><UserAvatar profile={memberAvatarProfile(member)} apiBaseUrl={apiBaseUrl} getAuthHeaders={getAuthHeaders} /><div><p className="font-medium text-slate-100">{memberDisplayName(member)}</p><p className="mt-1 text-xs text-slate-400">{member.department ? departmentLabel[member.department] : "No department"} · {assigned} active tasks</p></div></article>;
                    })}
                  </div>
                </section>
              </section>
            )}
            {view === "production" && (
              <>
                <div className="workspace-panel mb-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-700/70 bg-[#101b2b]/90 p-4">
                  <div>
                    <h2 className="font-semibold text-white">
                      {canWork ? "My assigned tasks" : "Production area"}
                    </h2>
                    <p className="mt-1 text-xs text-slate-500">
                      {canWork
                        ? "You can only advance tasks assigned to your account."
                        : "Assign and track work by department."}
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
                      <option value="sound">Sound</option>
                      <option value="color">Color</option>
                      <option value="editorial">Editorial</option>
                    </select>
                  )}
                </div>
                <section className="grid gap-6 lg:grid-cols-3">
                  <TicketColumn
                    title="Assigned"
                    description={`${departmentLabel[departmentFilter]} · ready to start`}
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
                            Start work
                          </button>
                        )}
                      </TicketCard>
                    )}
                  </TicketColumn>
                  <TicketColumn
                    title="In progress"
                    description="The artist works and then submits to QC"
                    tickets={inProgress}
                    loading={loading}
                  >
                    {(ticket) => (
                      <TicketCard
                        key={ticket.id}
                        ticket={ticket}
                        onRemoveEvidence={canWork ? setEvidenceToRemove : undefined}
                        onRemoveDeliveryLink={canWork ? setDeliveryLinkToRemove : undefined}
                      >
                        {canWork && (
                          <button
                            disabled={processingId === ticket.id}
                            onClick={() =>
                              openWorkflowAction(ticket, "send_qc")
                            }
                            className="action-button approve"
                          >
                            Submit to QC
                          </button>
                        )}
                      </TicketCard>
                    )}
                  </TicketColumn>
                  <TicketColumn
                    title="Ready for QC"
                    description="Waiting for supervisor review"
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
                      PRODUCTION / ADMINISTRATION
                    </p>
                    <h2 className="mt-2 text-2xl font-semibold text-white">
                      Manage team
                    </h2>
                    <p className="mt-1 text-sm text-slate-400">
                      Invite people, review responses, and update their
                      responsibilities.
                    </p>
                  </div>
                  <button
                    onClick={() => void refreshTeam()}
                    className="action-button reject flex items-center gap-2"
                  >
                    <RefreshCw className="h-3.5 w-3.5" /> Refresh
                  </button>
                </div>
                <section className="workspace-panel rounded-3xl border border-slate-700/70 bg-[#101b2b]/90 p-5 sm:p-6">
                  <h3 className="font-semibold text-white">
                    {editingMemberUid ? "Edit member" : "Invite member"}
                  </h3>
                  <p className="mt-1 text-xs text-slate-500">
                    The invitee will receive a notification and must accept it
                    before accessing this production.
                  </p>
                  <form
                    onSubmit={addMember}
                    className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(10rem,.55fr)_minmax(10rem,.55fr)_auto]"
                  >
                    <MemberSearch
                      selected={selectedMember}
                      onSelectedChange={setSelectedMember}
                      apiBaseUrl={apiBaseUrl}
                      getAuthHeaders={getAuthHeaders}
                      productionId={production.id}
                      excludedUids={members.filter((member) => member.uid !== editingMemberUid && member.membership_status !== "declined").map((member) => member.uid)}
                      disabled={Boolean(editingMemberUid)}
                    />
                    <select
                      value={memberRole}
                      onChange={(event) =>
                        setMemberRole(
                          event.target.value as "supervisor" | "artist",
                        )
                      }
                      className="workspace-input text-sm"
                    >
                      <option value="artist">Artist</option>
                      <option value="supervisor">Supervisor</option>
                    </select>
                    <select
                      value={memberDepartment}
                      disabled={memberRole === "supervisor"}
                      onChange={(event) =>
                        setMemberDepartment(event.target.value as Department)
                      }
                      className="workspace-input text-sm disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <option value="vfx">VFX</option>
                      <option value="sound">Sound</option>
                      <option value="color">Color</option>
                      <option value="editorial">Editorial</option>
                    </select>
                    <div className="flex gap-2 lg:justify-end">
                      <button disabled={!selectedMember} className="flex-1 rounded-xl bg-cyan-300 px-4 py-2 text-sm font-bold text-cyan-950 transition hover:-translate-y-0.5 hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-40 lg:flex-none">
                        {editingMemberUid
                          ? "Save changes"
                          : "Send invitation"}
                      </button>
                      {editingMemberUid && (
                        <button
                          type="button"
                          onClick={() => {
                            setEditingMemberUid(null);
                            setSelectedMember(null);
                            setMemberRole("artist");
                            setMemberDepartment("vfx");
                          }}
                          className="action-button reject"
                        >
                          Cancel
                        </button>
                      )}
                    </div>
                  </form>
                </section>
                <section className="workspace-panel rounded-3xl border border-amber-400/25 bg-amber-400/5 p-5">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <h3 className="font-semibold text-white">
                        Pending invitations
                      </h3>
                      <p className="mt-1 text-xs text-slate-400">
                        They do not have access to tickets yet.
                      </p>
                    </div>
                    <span className="rounded-full bg-amber-400/15 px-2.5 py-1 text-xs font-semibold text-amber-300">
                      {pendingMembers.length}
                    </span>
                  </div>
                  <div className="mt-4 space-y-2">
                    {pendingMembers.length === 0 ? (
                      <p className="text-sm text-slate-500">
                        There are no pending invitations.
                      </p>
                    ) : (
                      pendingMembers.map((member) => (
                        <div
                          key={member.uid}
                          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-400/20 px-3 py-3 text-sm"
                        >
                          <div className="flex min-w-0 items-center gap-3">
                            <UserAvatar profile={memberAvatarProfile(member)} apiBaseUrl={apiBaseUrl} getAuthHeaders={getAuthHeaders} />
                            <div className="min-w-0">
                            <p className="truncate text-slate-200">{memberDisplayName(member)}</p>
                            {member.username && <p className="truncate text-[11px] text-cyan-300">@{member.username}</p>}
                            <p className="mt-1 text-xs capitalize text-slate-400">
                              {roleLabel[member.role]}
                              {member.department
                                ? ` · ${departmentLabel[member.department]}`
                                : ""}{" "}
                              · awaiting response
                            </p>
                            </div>
                          </div>
                          <div className="flex gap-2">
                            <button
                              onClick={() => editMember(member)}
                              className="action-button reject"
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => setMemberToRemove(member)}
                              className="action-button reject"
                            >
                              Cancel invitation
                            </button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </section>
                <section className="workspace-panel rounded-3xl border border-slate-700/70 bg-[#101b2b]/90 p-5">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <h3 className="font-semibold text-white">
                        Active members
                      </h3>
                      <p className="mt-1 text-xs text-slate-400">
                        They have accepted and can work according to their role.
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
                        className="workspace-card rounded-2xl border border-slate-700 bg-[#162337] p-4"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex min-w-0 items-center gap-3">
                            <UserAvatar profile={memberAvatarProfile(member)} apiBaseUrl={apiBaseUrl} getAuthHeaders={getAuthHeaders} />
                            <div className="min-w-0">
                            <p className="truncate font-medium text-slate-100">{memberDisplayName(member)}</p>
                            {member.username && <p className="truncate text-[11px] text-cyan-300">@{member.username}</p>}
                            <p className="mt-1 text-xs capitalize text-slate-400">
                              {roleLabel[member.role]}
                              {member.department
                                ? ` · ${departmentLabel[member.department]}`
                                : ""}
                            </p>
                            </div>
                          </div>
                          {member.role !== "producer" && (
                            <div className="flex gap-3">
                              <button
                                onClick={() => editMember(member)}
                                className="text-xs text-cyan-300 hover:underline"
                              >
                                Manage role
                              </button>
                              <button
                                onClick={() => setMemberToRemove(member)}
                                className="text-xs text-rose-300 hover:underline"
                              >
                                Remove
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
              <section>
                <div className="mb-6">
                  <p className="text-xs font-bold tracking-[0.2em] text-cyan-300">PRODUCTION / TRACEABILITY</p>
                  <h2 className="mt-2 text-2xl font-semibold text-white">Delivery history</h2>
                  <p className="mt-1 text-sm text-slate-400">Find past decisions and open their complete timeline.</p>
                </div>
                <div className="workspace-panel mb-6 grid gap-3 rounded-2xl border border-slate-700 bg-[#101b2b]/90 p-4 md:grid-cols-3">
                  <input
                    value={historySearch}
                    onChange={(event) => setHistorySearch(event.target.value)}
                    placeholder="Search shot, note, or artist…"
                    className="rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm text-white outline-none placeholder:text-slate-500 focus:border-cyan-300"
                  />
                  <select value={historyDepartment} onChange={(event) => setHistoryDepartment(event.target.value as "all" | Department)} className="rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm text-slate-200">
                    <option value="all">All departments</option>
                    {(Object.keys(departmentLabel) as Department[]).map((department) => <option key={department} value={department}>{departmentLabel[department]}</option>)}
                  </select>
                  <select value={historyArtist} onChange={(event) => setHistoryArtist(event.target.value)} className="rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm text-slate-200">
                    <option value="all">Entire team</option>
                    {activeMembers.filter((member) => member.role === "artist").map((member) => <option key={member.uid} value={member.uid}>{memberDisplayName(member)}</option>)}
                  </select>
                </div>
                <div className="grid gap-6 lg:grid-cols-2">
                  <TicketColumn
                    title={`Completed (${filteredCompleted.length})`}
                    description="Deliverables approved by quality control"
                    tickets={filteredCompleted}
                    loading={loading}
                  >
                    {(ticket) => <TicketCard key={ticket.id} ticket={ticket} onViewActivity={(item) => void openTicketActivity(item)} />}
                  </TicketColumn>
                  <TicketColumn
                    title={`Rejected (${filteredRejected.length})`}
                    description="Notes that did not advance to production"
                    tickets={filteredRejected}
                    loading={loading}
                  >
                    {(ticket) => <TicketCard key={ticket.id} ticket={ticket} onViewActivity={(item) => void openTicketActivity(item)} />}
                  </TicketColumn>
                </div>
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
                FRAMEFLOW / TEAM
              </p>
              <h2
                id="remove-member-title"
                className="mt-2 text-xl font-semibold text-white"
              >
                Remove member
              </h2>
              <p className="mt-3 text-sm leading-6 text-slate-300">
                You are about to remove{" "}
                <span className="font-semibold text-white">
                  {memberDisplayName(memberToRemove)}
                </span>
                . Their active tasks will return to <strong>Pending review</strong>{" "}
                so a supervisor can reassign them.
              </p>
              <div className="mt-6 flex justify-end gap-3">
                <button
                  onClick={() => setMemberToRemove(null)}
                  className="action-button reject"
                >
                  Cancel
                </button>
                <button
                  onClick={() => {
                    void removeMember(memberToRemove);
                    setMemberToRemove(null);
                  }}
                  className="rounded-lg bg-rose-400 px-4 py-2 text-sm font-bold text-rose-950 hover:bg-rose-300"
                >
                  Remove member
                </button>
              </div>
            </section>
          </div>
        )}
        {evidenceToRemove && (
          <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/75 p-4">
            <section
              role="dialog"
              aria-modal="true"
              aria-labelledby="remove-evidence-title"
              className="w-full max-w-md rounded-2xl border border-rose-400/30 bg-[#101b2b] p-6 shadow-2xl"
            >
              <p className="text-xs font-bold tracking-[0.2em] text-rose-300">FRAMEFLOW / DELIVERY</p>
              <h2 id="remove-evidence-title" className="mt-2 text-xl font-semibold text-white">Remove evidence</h2>
              <p className="mt-3 text-sm leading-6 text-slate-300">
                <span className="font-semibold text-white">{evidenceToRemove.evidence_name ?? "This evidence"}</span> will be removed from this task and from private storage. You can attach another file before submitting it to QC.
              </p>
              <div className="mt-6 flex justify-end gap-3">
                <button onClick={() => setEvidenceToRemove(null)} disabled={processingId === evidenceToRemove.id} className="action-button reject">Cancel</button>
                <button onClick={() => void removeEvidence(evidenceToRemove)} disabled={processingId === evidenceToRemove.id} className="rounded-lg bg-rose-400 px-4 py-2 text-sm font-bold text-rose-950 hover:bg-rose-300">
                  {processingId === evidenceToRemove.id ? "Removing…" : "Remove evidence"}
                </button>
              </div>
            </section>
          </div>
        )}
        {deliveryLinkToRemove && (
          <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/75 p-4">
            <section
              role="dialog"
              aria-modal="true"
              aria-labelledby="remove-delivery-link-title"
              className="w-full max-w-md rounded-2xl border border-rose-400/30 bg-[#101b2b] p-6 shadow-2xl"
            >
              <p className="text-xs font-bold tracking-[0.2em] text-rose-300">FRAMEFLOW / DELIVERY</p>
              <h2 id="remove-delivery-link-title" className="mt-2 text-xl font-semibold text-white">Remove delivery link</h2>
              <p className="mt-3 break-words text-sm leading-6 text-slate-300">
                This link will no longer be associated with the task. You can add another before submitting it to QC.
              </p>
              <div className="mt-6 flex justify-end gap-3">
                <button onClick={() => setDeliveryLinkToRemove(null)} disabled={processingId === deliveryLinkToRemove.id} className="action-button reject">Cancel</button>
                <button onClick={() => void removeDeliveryLink(deliveryLinkToRemove)} disabled={processingId === deliveryLinkToRemove.id} className="rounded-lg bg-rose-400 px-4 py-2 text-sm font-bold text-rose-950 hover:bg-rose-300">
                  {processingId === deliveryLinkToRemove.id ? "Removing…" : "Remove link"}
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
                  ? "Assign artist"
                  : workflowAction.type === "send_qc"
                    ? "Submit to quality control"
                    : workflowAction.type === "complete"
                      ? "Complete task"
                      : "Return for corrections"}
              </h2>
              {workflowAction.type === "assign" ? (
                <label className="mt-5 block text-xs font-semibold uppercase tracking-wide text-slate-400">
                  Team artist
                  <select
                    autoFocus
                    value={assignedArtistId}
                    onChange={(event) =>
                      setAssignedArtistId(event.target.value)
                    }
                    className="mt-2 w-full rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm text-white outline-none focus:border-cyan-300"
                  >
                    <option value="">Select an artist…</option>
                    {members
                      .filter(
                        (member) =>
                          member.role === "artist" &&
                          member.department ===
                            workflowAction.ticket.department,
                      )
                      .map((member) => (
                        <option key={member.uid} value={member.uid}>
                          {memberDisplayName(member)}
                        </option>
                      ))}
                  </select>
                </label>
              ) : (
                <>
                  <p className="mt-2 text-sm text-slate-400">
                    {workflowAction.type === "send_qc"
                      ? "Add context so the supervisor can review the deliverable."
                      : workflowAction.type === "complete"
                        ? "You can leave a final note before archiving the work."
                        : "Clearly describe the changes the artist must make."}
                  </p>
                  <label className="mt-5 block text-xs font-semibold uppercase tracking-wide text-slate-400">
                    {workflowAction.type === "send_qc"
                      ? "Artist note"
                      : "Supervisor feedback"}
                    <textarea
                      autoFocus
                      value={workflowNote}
                      onChange={(event) => setWorkflowNote(event.target.value)}
                      maxLength={1000}
                      rows={4}
                      placeholder={
                        workflowAction.type === "return_for_rework"
                          ? "E.g. Fix the microphone edges near the hair."
                          : "Optional comment…"
                      }
                      className="mt-2 w-full rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm text-white outline-none placeholder:text-slate-500 focus:border-cyan-300"
                    />
                  </label>
                  {workflowAction.type === "send_qc" && (
                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      <label className="block text-xs font-semibold uppercase tracking-wide text-slate-400">
                        Delivery link <span className="normal-case text-slate-500">(optional)</span>
                        <input
                          type="url"
                          value={deliveryLink}
                          onChange={(event) => setDeliveryLink(event.target.value)}
                          maxLength={2048}
                          placeholder="https://drive.google.com/..."
                          className="mt-2 w-full rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm text-white outline-none placeholder:text-slate-500 focus:border-cyan-300"
                        />
                      </label>
                      <label className="block text-xs font-semibold uppercase tracking-wide text-slate-400">
                        Visual evidence <span className="normal-case text-slate-500">(optional, max. 5 MB{workflowAction.ticket.evidence_gcs_uri ? "; replaces the current file" : ""})</span>
                        <input
                          type="file"
                          accept="image/jpeg,image/png,image/webp,application/pdf"
                          onChange={(event) => setEvidenceFile(event.target.files?.[0] ?? null)}
                          className="mt-2 block w-full text-xs text-slate-300 file:mr-3 file:rounded-md file:border-0 file:bg-slate-700 file:px-3 file:py-2 file:text-xs file:font-semibold file:text-white hover:file:bg-slate-600"
                        />
                      </label>
                    </div>
                  )}
                </>
              )}
              <div className="mt-6 flex justify-end gap-3">
                <button
                  onClick={() => setWorkflowAction(null)}
                  disabled={processingId === workflowAction.ticket.id}
                  className="action-button reject"
                >
                  Cancel
                </button>
                <button
                  onClick={() => void confirmWorkflowAction()}
                  disabled={processingId === workflowAction.ticket.id}
                  className="action-button approve"
                >
                  {processingId === workflowAction.ticket.id
                    ? "Saving…"
                    : workflowAction.type === "assign"
                      ? "Assign task"
                      : workflowAction.type === "send_qc"
                        ? "Submit to QC"
                        : workflowAction.type === "complete"
                          ? "Complete"
                          : "Return task"}
                </button>
              </div>
            </section>
          </div>
        )}
        {activityTicket && (
          <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/75 p-4">
            <section
              role="dialog"
              aria-modal="true"
              aria-labelledby="activity-dialog-title"
              className="w-full max-w-lg rounded-2xl border border-slate-700 bg-[#101b2b] p-6 shadow-2xl"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-bold tracking-[0.2em] text-cyan-300">FRAMEFLOW / HISTORY</p>
                  <h2 id="activity-dialog-title" className="mt-2 text-xl font-semibold text-white">
                    Activity · {activityTicket.shot_id}
                  </h2>
                </div>
                <button onClick={() => setActivityTicket(null)} className="text-sm text-slate-400 hover:text-white">Close</button>
              </div>
              <div className="mt-5 max-h-[55vh] space-y-4 overflow-y-auto pr-2">
                {activityLoading ? (
                  <p className="text-sm text-slate-400">Loading activity…</p>
                ) : ticketActivity.length === 0 ? (
                  <p className="rounded-lg border border-dashed border-slate-700 p-4 text-sm text-slate-500">This task was created before detailed activity tracking was available.</p>
                ) : ticketActivity.map((item) => (
                  <article key={item.id} className="border-l-2 border-cyan-400/50 pl-4">
                    <p className="text-sm font-semibold text-white">{item.action}</p>
                    <p className="mt-1 text-xs text-slate-400">
                      {item.actor_name ?? item.actor_uid} · {new Date(item.created_at).toLocaleString("en-US")}
                    </p>
                    {item.detail && <p className="mt-2 text-sm leading-6 text-slate-300">{item.detail}</p>}
                  </article>
                ))}
              </div>
            </section>
          </div>
        )}
      </section>
    </main>
  );
}

export default function Home() {
  const { user } = useAuth();
  return <Workspace key={user?.uid ?? "anonymous"} />;
}
