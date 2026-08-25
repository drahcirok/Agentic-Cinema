"use client";

import { FormEvent, useRef, useState } from "react";

type Ticket = {
  id: string;
  shot_id: string;
  director_note: string;
  department: "vfx" | "color" | "sound" | "editorial";
  priority: "low" | "medium" | "high" | "critical";
  status: "pending_review" | "approved" | "rejected";
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

const ALLOWED_TYPES = ["image/jpeg", "image/jpg", "image/png", "image/webp"];
const MAX_SIZE_MB = 10;

export default function DirectorNoteForm({ onCreated }: { onCreated: (ticket: Ticket) => void }) {
  const [shotId, setShotId] = useState("");
  const [directorNote, setDirectorNote] = useState("");
  const [frame, setFrame] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleFrameChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    if (!file) return;

    if (!ALLOWED_TYPES.includes(file.type)) {
      setMessage({ text: `Tipo no permitido: ${file.type}. Usa .jpg, .png o .webp.`, ok: false });
      return;
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      setMessage({ text: `El fotograma supera los ${MAX_SIZE_MB} MiB.`, ok: false });
      return;
    }

    // Revoke the previous object URL before creating a new one to avoid
    // leaking blob memory when the user replaces the image without clicking "Quitar".
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(file);
    });
    setMessage(null);
    setFrame(file);
  }

  function removeFrame() {
    setFrame(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setMessage(null);

    try {
      const body = new FormData();
      body.append("shot_id", shotId);
      body.append("director_note", directorNote);
      if (frame) body.append("frame", frame);

      const response = await fetch(`${apiBaseUrl}/ingestion/director-notes`, {
        method: "POST",
        body,
        // No Content-Type header — the browser sets it with the multipart boundary.
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail ?? "No se pudo procesar la nota.");
      }

      if (response.status === 201) {
        // Post-production required — ticket was created, add to Kanban.
        onCreated(data as Ticket);
        setShotId("");
        setDirectorNote("");
        removeFrame();
        setMessage({
          text: frame
            ? "Gemini analizó la nota y el fotograma. Ticket pendiente de revisión."
            : "Gemini creó un ticket pendiente de revisión.",
          ok: true,
        });
      } else {
        // HTTP 200: requires_postproduction=false — no ticket created.
        const reason: string = data.rejection_reason ?? data.ai_rationale ?? "";
        setShotId("");
        setDirectorNote("");
        removeFrame();
        setMessage({
          text: `No se creó ticket: esta nota no requiere postproducción.${reason ? ` ${reason}` : ""}`,
          ok: false,
        });
      }
    } catch (error) {
      setMessage({
        text: error instanceof Error ? error.message : "No se pudo procesar la nota.",
        ok: false,
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="mb-7 rounded-2xl border border-slate-700/70 bg-[#101b2b] p-4">
      {/* Main row */}
      <div className="grid gap-3 md:grid-cols-[160px_1fr_auto] md:items-end">
        <label className="grid gap-1 text-xs font-semibold text-slate-400">
          TOMA
          <input
            required
            value={shotId}
            onChange={(e) => setShotId(e.target.value)}
            placeholder="SC03-SH014"
            className="rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm text-white outline-none focus:border-cyan-300"
          />
        </label>
        <label className="grid gap-1 text-xs font-semibold text-slate-400">
          NOTA DEL DIRECTOR
          <input
            required
            value={directorNote}
            onChange={(e) => setDirectorNote(e.target.value)}
            placeholder="Ej. Eliminar el micrófono del encuadre."
            className="rounded-lg border border-slate-600 bg-[#162337] px-3 py-2 text-sm text-white outline-none focus:border-cyan-300"
          />
        </label>
        <button
          disabled={submitting}
          className="rounded-lg bg-cyan-300 px-4 py-2 text-sm font-bold text-cyan-950 disabled:opacity-50"
        >
          {submitting ? "Analizando…" : "Analizar con Gemini"}
        </button>
      </div>

      {/* Image picker row */}
      <div className="mt-3 flex flex-wrap items-start gap-4">
        <div className="flex flex-col gap-1">
          <span className="text-xs font-semibold text-slate-400">
            FOTOGRAMA{" "}
            <span className="font-normal text-slate-500">(opcional — .jpg, .png, .webp · máx. {MAX_SIZE_MB} MiB)</span>
          </span>
          <div className="flex items-center gap-2">
            <label className="cursor-pointer rounded-lg border border-dashed border-slate-600 bg-[#162337] px-3 py-1.5 text-xs text-slate-300 hover:border-cyan-400 hover:text-cyan-300">
              {frame ? "Cambiar imagen" : "Seleccionar imagen"}
              <input
                ref={fileInputRef}
                type="file"
                accept=".jpg,.jpeg,.png,.webp"
                className="sr-only"
                onChange={handleFrameChange}
              />
            </label>
            {frame && (
              <button
                type="button"
                onClick={removeFrame}
                className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-2.5 py-1.5 text-xs text-rose-300 hover:bg-rose-500/20"
              >
                Quitar
              </button>
            )}
          </div>
          {frame && (
            <p className="mt-1 text-xs text-slate-500">
              {frame.name} · {(frame.size / 1024).toFixed(0)} KB
            </p>
          )}
        </div>

        {/* Thumbnail preview */}
        {previewUrl && (
          <div className="relative">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={previewUrl}
              alt="Previsualización del fotograma"
              className="h-20 w-auto rounded-lg border border-slate-600 object-cover"
            />
          </div>
        )}

        {/* Quota notice shown only when a frame is attached */}
        {frame && (
          <p className="self-end text-xs text-amber-400/80">
            ⚠ Enviar un fotograma consume cuota adicional de Gemini.
          </p>
        )}
      </div>

      {/* Status message — amber for informational non-errors (no ticket needed) */}
      {message && (
        <p
          className={`mt-3 text-xs ${
            message.ok
              ? "text-slate-300"
              : message.text.startsWith("No se creó ticket:")
              ? "text-amber-300"
              : "text-rose-300"
          }`}
        >
          {message.text}
        </p>
      )}
    </form>
  );
}
