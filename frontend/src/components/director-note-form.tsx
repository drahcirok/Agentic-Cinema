"use client";

import { FormEvent, useRef, useState } from "react";
import { useAuth } from "@/components/auth-provider";

type Ticket = {
  id: string;
  shot_id: string;
  director_note: string;
  department: "vfx" | "color" | "sound" | "editorial";
  priority: "low" | "medium" | "high" | "critical";
  status: "pending_review" | "approved" | "rejected";
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

const ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/jpg", "image/png", "image/webp"];
const ALLOWED_VIDEO_TYPES = ["video/mp4"];
const MAX_IMAGE_MB = 10;
const MAX_VIDEO_MB = 50;

export default function DirectorNoteForm({ onCreated }: { onCreated: (ticket: Ticket) => void }) {
  const { getAuthHeaders } = useAuth();
  const [shotId, setShotId] = useState("");
  const [directorNote, setDirectorNote] = useState("");

  // Frame (image) state
  const [frame, setFrame] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const frameInputRef = useRef<HTMLInputElement>(null);

  // Video state
  const [video, setVideo] = useState<File | null>(null);
  const videoInputRef = useRef<HTMLInputElement>(null);

  const [submitting, setSubmitting] = useState(false);
  // variant drives the status message colour as a static class name so
  // Tailwind v4's scanner can detect all three strings unambiguously.
  //   "ok"      → cyan/slate  (ticket created)
  //   "info"    → amber       (no post-production needed)
  //   "error"   → rose        (network or API error)
  const [message, setMessage] = useState<{ text: string; variant: "ok" | "info" | "error" } | null>(null);

  // ------------------------------------------------------------------
  // Frame handlers
  // ------------------------------------------------------------------

  function handleFrameChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    if (!file) return;

    if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
      setMessage({ text: `Tipo no permitido: ${file.type}. Usa .jpg, .png o .webp.`, variant: "error" });
      return;
    }
    if (file.size > MAX_IMAGE_MB * 1024 * 1024) {
      setMessage({ text: `El fotograma supera los ${MAX_IMAGE_MB} MiB.`, variant: "error" });
      return;
    }

    // Clear video when the user picks a frame.
    removeVideo();

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
    if (frameInputRef.current) frameInputRef.current.value = "";
  }

  // ------------------------------------------------------------------
  // Video handlers
  // ------------------------------------------------------------------

  function handleVideoChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    if (!file) return;

    if (!ALLOWED_VIDEO_TYPES.includes(file.type)) {
      setMessage({ text: `Tipo no permitido: ${file.type}. Usa .mp4.`, variant: "error" });
      return;
    }
    if (file.size > MAX_VIDEO_MB * 1024 * 1024) {
      setMessage({ text: `El video supera los ${MAX_VIDEO_MB} MiB.`, variant: "error" });
      return;
    }

    // Clear frame when the user picks a video.
    removeFrame();

    setMessage(null);
    setVideo(file);
  }

  function removeVideo() {
    setVideo(null);
    if (videoInputRef.current) videoInputRef.current.value = "";
  }

  // ------------------------------------------------------------------
  // Submit
  // ------------------------------------------------------------------

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setMessage(null);

    try {
      const body = new FormData();
      body.append("shot_id", shotId);
      body.append("director_note", directorNote);
      if (frame) body.append("frame", frame);
      if (video) body.append("video", video);

      const response = await fetch(`${apiBaseUrl}/ingestion/director-notes`, {
        method: "POST",
        body,
        headers: await getAuthHeaders(),
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
        removeVideo();
        const mediaLabel = video
          ? "el video"
          : frame
          ? "el fotograma"
          : null;
        setMessage({
          text: mediaLabel
            ? `Gemini analizó la nota y ${mediaLabel}. Ticket pendiente de revisión.`
            : "Gemini creó un ticket pendiente de revisión.",
          variant: "ok",
        });
      } else {
        // HTTP 200: requires_postproduction=false — no ticket created.
        const reason: string = data.rejection_reason ?? data.ai_rationale ?? "";
        setShotId("");
        setDirectorNote("");
        removeFrame();
        removeVideo();
        setMessage({
          text: `No se creó ticket: esta nota no requiere postproducción.${reason ? ` ${reason}` : ""}`,
          variant: "info",
        });
      }
    } catch (error) {
      setMessage({
        text: error instanceof Error ? error.message : "No se pudo procesar la nota.",
        variant: "error",
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

      {/* Media pickers row — frame and video are mutually exclusive */}
      <div className="mt-3 flex flex-wrap items-start gap-6">

        {/* ---- Frame picker ---- */}
        <div className="flex flex-col gap-1">
          <span className="text-xs font-semibold text-slate-400">
            FOTOGRAMA{" "}
            <span className="font-normal text-slate-500">
              (opcional · .jpg .png .webp · máx. {MAX_IMAGE_MB} MiB)
            </span>
          </span>
          <div className="flex items-center gap-2">
            <label
              className={
                video
                  ? "cursor-not-allowed rounded-lg border border-dashed border-slate-700 bg-[#162337] px-3 py-1.5 text-xs text-slate-600"
                  : "cursor-pointer rounded-lg border border-dashed border-slate-600 bg-[#162337] px-3 py-1.5 text-xs text-slate-300 hover:border-cyan-400 hover:text-cyan-300"
              }
            >
              {frame ? "Cambiar imagen" : "Seleccionar imagen"}
              <input
                ref={frameInputRef}
                type="file"
                accept=".jpg,.jpeg,.png,.webp"
                className="sr-only"
                onChange={handleFrameChange}
                disabled={!!video}
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

        {/* ---- Video picker ---- */}
        <div className="flex flex-col gap-1">
          <span className="text-xs font-semibold text-slate-400">
            VIDEO{" "}
            <span className="font-normal text-slate-500">
              (opcional · .mp4 · máx. {MAX_VIDEO_MB} MiB)
            </span>
          </span>
          <div className="flex items-center gap-2">
            <label
              className={
                frame
                  ? "cursor-not-allowed rounded-lg border border-dashed border-slate-700 bg-[#162337] px-3 py-1.5 text-xs text-slate-600"
                  : "cursor-pointer rounded-lg border border-dashed border-slate-600 bg-[#162337] px-3 py-1.5 text-xs text-slate-300 hover:border-cyan-400 hover:text-cyan-300"
              }
            >
              {video ? "Cambiar video" : "Seleccionar video"}
              <input
                ref={videoInputRef}
                type="file"
                accept=".mp4,video/mp4"
                className="sr-only"
                onChange={handleVideoChange}
                disabled={!!frame}
              />
            </label>
            {video && (
              <button
                type="button"
                onClick={removeVideo}
                className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-2.5 py-1.5 text-xs text-rose-300 hover:bg-rose-500/20"
              >
                Quitar
              </button>
            )}
          </div>
          {video && (
            <p className="mt-1 text-xs text-slate-500">
              {video.name} · {(video.size / (1024 * 1024)).toFixed(1)} MB
            </p>
          )}
        </div>

        {/* Thumbnail preview for frames */}
        {previewUrl && (
          <div className="relative self-start">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={previewUrl}
              alt="Previsualización del fotograma"
              className="h-20 w-auto rounded-lg border border-slate-600 object-cover"
            />
          </div>
        )}
      </div>

      {/* Quota warnings */}
      {frame && (
        <p className="mt-2 text-xs text-amber-400/80">
          ⚠ Enviar un fotograma consume cuota adicional de Gemini.
        </p>
      )}
      {video && (
        <p className="mt-2 text-xs text-amber-400/80">
          ⚠ Enviar un video sube el archivo a Cloud Storage y consume cuota adicional de Gemini.
        </p>
      )}

      {/* Status message — three visually distinct variants */}
      {message && (
        <p
          data-testid="ingestion-message"
          data-variant={message.variant}
          className={
            message.variant === "ok"
              ? "mt-3 text-xs text-cyan-300"
              : message.variant === "info"
              ? "mt-3 text-xs text-amber-300"
              : "mt-3 text-xs text-rose-300"
          }
        >
          {message.text}
        </p>
      )}
    </form>
  );
}
