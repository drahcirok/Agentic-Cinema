"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/components/auth-provider";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Department = "vfx" | "color" | "sound" | "editorial";
type Priority = "low" | "medium" | "high" | "critical";
type TicketStatus = "pending_review" | "approved" | "rejected";

export type Ticket = {
  id: string;
  shot_id: string;
  director_note: string;
  department: Department;
  priority: Priority;
  status: TicketStatus;
  ai_rationale?: string | null;
  supervisor_note?: string | null;
};

const DEPT_OPTIONS: { value: Department; label: string }[] = [
  { value: "vfx",       label: "VFX" },
  { value: "color",     label: "Color" },
  { value: "sound",     label: "Sonido" },
  { value: "editorial", label: "Edición" },
];

const PRIORITY_OPTIONS: { value: Priority; label: string }[] = [
  { value: "low",      label: "Baja" },
  { value: "medium",   label: "Media" },
  { value: "high",     label: "Alta" },
  { value: "critical", label: "Crítica" },
];

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface EditTicketDialogProps {
  ticket: Ticket;
  /** Called with the server-returned updated ticket after a successful PATCH. */
  onUpdated: (updated: Ticket) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function EditTicketDialog({
  ticket,
  onUpdated,
}: EditTicketDialogProps) {
  const { getAuthHeaders } = useAuth();
  const [open, setOpen] = useState(false);

  // Editable fields — initialised from current ticket values each time the
  // dialog opens (reset happens in handleOpenChange).
  const [department, setDepartment] = useState<Department>(ticket.department);
  const [priority, setPriority]     = useState<Priority>(ticket.priority);
  const [supervisorNote, setSupervisorNote] = useState(
    ticket.supervisor_note ?? ""
  );

  const [saving,  setSaving]  = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved,   setSaved]   = useState(false);

  // Reset local state every time the dialog opens so stale values never show.
  function handleOpenChange(next: boolean) {
    if (next) {
      setDepartment(ticket.department);
      setPriority(ticket.priority);
      setSupervisorNote(ticket.supervisor_note ?? "");
      setSaveError(null);
      setSaved(false);
    }
    setOpen(next);
  }

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    setSaved(false);

    try {
      const res = await fetch(`${apiBaseUrl}/tickets/${ticket.id}/review`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...(await getAuthHeaders()) },
        body: JSON.stringify({
          decision: "edit",
          department,
          priority,
          supervisor_note: supervisorNote.trim() || null,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(
          (body as { detail?: string }).detail ?? `Error ${res.status}`
        );
      }

      const updated: Ticket = await res.json();
      onUpdated(updated);
      setSaved(true);

      // Auto-close after a short confirmation beat so the user sees it saved.
      setTimeout(() => setOpen(false), 900);
    } catch (err) {
      setSaveError(
        err instanceof Error ? err.message : "No se pudo guardar. Inténtalo de nuevo."
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger
        className="action-button edit"
        disabled={saving}
      >
        Editar
      </DialogTrigger>

      <DialogContent
        className="max-w-lg bg-[#101b2b] text-slate-100 ring-slate-700/70"
      >
        <DialogHeader>
          <DialogTitle className="text-white">
            Editar ticket
          </DialogTitle>
          <DialogDescription className="text-slate-400">
            Los cambios mantienen el ticket en{" "}
            <span className="text-cyan-300">Por revisar</span>.
          </DialogDescription>
        </DialogHeader>

        {/* Read-only context */}
        <div className="space-y-2 rounded-lg border border-slate-700 bg-[#0d1825] px-4 py-3">
          <p className="font-mono text-xs text-cyan-300">{ticket.shot_id}</p>
          <p className="text-sm leading-relaxed text-slate-300">
            {ticket.director_note}
          </p>
          {ticket.ai_rationale && (
            <p className="mt-1 border-t border-slate-700 pt-2 text-xs text-slate-500">
              <span className="font-semibold text-slate-400">IA: </span>
              {ticket.ai_rationale}
            </p>
          )}
        </div>

        {/* Editable fields */}
        <div className="grid grid-cols-2 gap-4">
          {/* Department */}
          <div className="space-y-1.5">
            <Label
              htmlFor={`edit-dept-${ticket.id}`}
              className="text-xs font-semibold uppercase tracking-wide text-slate-400"
            >
              Departamento
            </Label>
            <Select
              value={department}
              onValueChange={(v) => setDepartment(v as Department)}
            >
              <SelectTrigger
                id={`edit-dept-${ticket.id}`}
                className="w-full border-slate-600 bg-[#162337] text-slate-100"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DEPT_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Priority */}
          <div className="space-y-1.5">
            <Label
              htmlFor={`edit-prio-${ticket.id}`}
              className="text-xs font-semibold uppercase tracking-wide text-slate-400"
            >
              Prioridad
            </Label>
            <Select
              value={priority}
              onValueChange={(v) => setPriority(v as Priority)}
            >
              <SelectTrigger
                id={`edit-prio-${ticket.id}`}
                className="w-full border-slate-600 bg-[#162337] text-slate-100"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PRIORITY_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Supervisor note */}
        <div className="space-y-1.5">
          <Label
            htmlFor={`edit-note-${ticket.id}`}
            className="text-xs font-semibold uppercase tracking-wide text-slate-400"
          >
            Nota del supervisor
          </Label>
          <Textarea
            id={`edit-note-${ticket.id}`}
            value={supervisorNote}
            onChange={(e) => setSupervisorNote(e.target.value)}
            placeholder="Añade contexto o instrucciones para el equipo…"
            maxLength={1000}
            rows={3}
            className="border-slate-600 bg-[#162337] text-slate-100 placeholder:text-slate-500"
          />
        </div>

        {/* Feedback messages */}
        {saveError && (
          <p className="text-xs text-rose-400">{saveError}</p>
        )}
        {saved && !saveError && (
          <p className="text-xs text-cyan-300">
            ✓ Cambios guardados. El ticket sigue en revisión.
          </p>
        )}

        <DialogFooter>
          <button
            type="button"
            onClick={() => setOpen(false)}
            disabled={saving}
            className="action-button reject"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="action-button approve"
          >
            {saving ? "Guardando…" : "Guardar cambios"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
