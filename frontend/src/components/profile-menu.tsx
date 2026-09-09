"use client";

import {
  Camera,
  Check,
  Copy,
  LoaderCircle,
  LogOut,
  Settings2,
  Sparkles,
  UserRound,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

import type { UserProfile } from "@/lib/profile-types";
import UserAvatar from "@/components/user-avatar";

export default function ProfileMenu({
  profile,
  apiBaseUrl,
  getAuthHeaders,
  onProfileChange,
  onSignOut,
}: {
  profile: UserProfile;
  apiBaseUrl: string;
  getAuthHeaders: () => Promise<Record<string, string>>;
  onProfileChange: (profile: UserProfile) => void;
  onSignOut: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [displayName, setDisplayName] = useState(profile.display_name);
  const [username, setUsername] = useState(profile.username);
  const [avatar, setAvatar] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open && !editing) return;
    const handleKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (editing) {
        setEditing(false);
        setAvatar(null);
        setError(null);
      } else {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [editing, open]);

  function closeEditor() {
    setEditing(false);
    setAvatar(null);
    setError(null);
  }

  async function saveProfile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/profiles/me`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...(await getAuthHeaders()),
        },
        body: JSON.stringify({ display_name: displayName, username }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "Unable to save your profile.");
      let updated = body as UserProfile;
      onProfileChange(updated);
      if (avatar) {
        const form = new FormData();
        form.append("avatar", avatar);
        const avatarResponse = await fetch(`${apiBaseUrl}/profiles/me/avatar`, {
          method: "POST",
          headers: await getAuthHeaders(),
          body: form,
        });
        const avatarBody = await avatarResponse.json();
        if (!avatarResponse.ok)
          throw new Error(avatarBody.detail ?? "Unable to upload the photo.");
        updated = avatarBody as UserProfile;
      }
      onProfileChange(updated);
      setAvatar(null);
      setEditing(false);
      setOpen(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to save your profile.");
    } finally {
      setBusy(false);
    }
  }

  async function resetAvatar() {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/profiles/me/avatar`, {
        method: "DELETE",
        headers: await getAuthHeaders(),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "Unable to restore the photo.");
      onProfileChange(body as UserProfile);
      setAvatar(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to restore the photo.");
    } finally {
      setBusy(false);
    }
  }

  async function copyUid() {
    await navigator.clipboard.writeText(profile.uid);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  return (
    <div className="relative z-40">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="group flex items-center gap-3 rounded-full border border-slate-700/70 bg-slate-950/45 p-1.5 pr-3 text-left shadow-lg backdrop-blur transition hover:-translate-y-0.5 hover:border-cyan-300/35 hover:bg-slate-900/80"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <UserAvatar profile={profile} apiBaseUrl={apiBaseUrl} getAuthHeaders={getAuthHeaders} />
        <span className="hidden max-w-32 sm:block">
          <span className="block truncate text-xs font-semibold text-white">{profile.display_name}</span>
          <span className="block truncate text-[10px] text-cyan-300">@{profile.username}</span>
        </span>
        <Settings2 className="h-3.5 w-3.5 text-slate-500 transition group-hover:rotate-45 group-hover:text-cyan-300" />
      </button>

      {open && (
        <>
          <button type="button" aria-label="Close profile menu" className="fixed inset-0 z-[-1] cursor-default" onClick={() => setOpen(false)} />
          <div role="menu" aria-label="Profile options" className="absolute right-0 mt-3 w-72 overflow-hidden rounded-2xl border border-slate-700/80 bg-[#0d1828]/95 p-2 shadow-[0_24px_80px_rgba(0,0,0,.45)] backdrop-blur-xl landing-rise">
            <div className="rounded-xl bg-gradient-to-br from-cyan-400/10 to-violet-400/5 p-4">
              <div className="flex items-center gap-3">
                <UserAvatar profile={profile} apiBaseUrl={apiBaseUrl} getAuthHeaders={getAuthHeaders} size="lg" />
                <div className="min-w-0">
                  <p className="truncate font-semibold text-white">{profile.display_name}</p>
                  <p className="truncate text-xs text-cyan-300">@{profile.username}</p>
                </div>
              </div>
              <button type="button" role="menuitem" onClick={() => void copyUid()} className="mt-3 flex w-full items-center justify-between rounded-lg border border-white/5 bg-black/15 px-3 py-2 text-[10px] text-slate-400 transition hover:border-cyan-300/20 hover:text-slate-200">
                <span className="truncate font-mono">UID · {profile.uid}</span>
                {copied ? <Check className="ml-2 h-3.5 w-3.5 text-emerald-300" /> : <Copy className="ml-2 h-3.5 w-3.5" />}
              </button>
            </div>
            <button type="button" role="menuitem" onClick={() => { setDisplayName(profile.display_name); setUsername(profile.username); setEditing(true); setOpen(false); }} className="mt-2 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-slate-200 transition hover:bg-cyan-400/10 hover:text-cyan-200">
              <UserRound className="h-4 w-4" /> My profile
            </button>
            <button type="button" role="menuitem" onClick={() => void onSignOut()} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-slate-400 transition hover:bg-rose-400/10 hover:text-rose-200">
              <LogOut className="h-4 w-4" /> Sign out
            </button>
          </div>
        </>
      )}

      {editing && (
        <div className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-[#050a12]/85 p-4 py-6 backdrop-blur-sm">
          <form role="dialog" aria-modal="true" aria-labelledby="profile-dialog-title" onSubmit={saveProfile} className="workspace-modal max-h-[calc(100dvh-3rem)] w-full max-w-lg overflow-y-auto rounded-3xl border border-cyan-300/20 bg-[#0d1828] shadow-[0_30px_100px_rgba(0,0,0,.65)]">
            <div className="relative border-b border-white/5 bg-gradient-to-br from-cyan-400/10 via-transparent to-violet-400/10 px-6 py-6 sm:px-8">
              <button type="button" onClick={closeEditor} className="absolute right-5 top-5 rounded-full p-2 text-slate-500 transition hover:bg-white/5 hover:text-white" aria-label="Close profile">
                <X className="h-4 w-4" />
              </button>
              <div className="flex items-center gap-4">
                <div className="relative">
                  <UserAvatar profile={profile} apiBaseUrl={apiBaseUrl} getAuthHeaders={getAuthHeaders} size="xl" />
                  <span className="absolute bottom-0 right-0 grid h-8 w-8 place-items-center rounded-full border-2 border-[#0d1828] bg-cyan-300 text-cyan-950"><Camera className="h-4 w-4" /></span>
                </div>
                <div>
                  <p className="flex items-center gap-2 text-[10px] font-bold tracking-[.22em] text-cyan-300"><Sparkles className="h-3.5 w-3.5" /> FRAMEFLOW IDENTITY</p>
                  <h2 id="profile-dialog-title" className="mt-2 text-2xl font-semibold text-white">Your profile</h2>
                  <p className="mt-1 text-sm text-slate-400">This is how your team will recognize you.</p>
                </div>
              </div>
            </div>
            <div className="space-y-5 px-6 py-6 sm:px-8">
              <label className="block text-xs font-semibold uppercase tracking-[.12em] text-slate-400">
                Display name
                <input required minLength={2} maxLength={80} value={displayName} onChange={(event) => setDisplayName(event.target.value)} className="workspace-input mt-2 w-full" placeholder="Your name" />
              </label>
              <label className="block text-xs font-semibold uppercase tracking-[.12em] text-slate-400">
                Username
                <div className="workspace-input mt-2 flex items-center gap-1 focus-within:border-cyan-300/70">
                  <span className="text-cyan-300">@</span>
                  <input required minLength={3} maxLength={30} value={username} onChange={(event) => setUsername(event.target.value.toLowerCase().replace(/[^a-z0-9._-]/g, ""))} className="min-w-0 flex-1 bg-transparent text-white outline-none" placeholder="username" />
                </div>
                <span className="mt-2 block text-[11px] font-normal normal-case tracking-normal text-slate-500">Unique on FrameFlow · letters, numbers, periods, hyphens, or underscores</span>
              </label>
              <label className="block text-xs font-semibold uppercase tracking-[.12em] text-slate-400">
                New photo <span className="font-normal normal-case text-slate-500">(optional · JPG, PNG, or WEBP · max. 2 MB)</span>
                <input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setAvatar(event.target.files?.[0] ?? null)} className="mt-2 block w-full text-xs text-slate-400 file:mr-3 file:rounded-lg file:border-0 file:bg-cyan-300/10 file:px-3 file:py-2 file:font-semibold file:text-cyan-200 hover:file:bg-cyan-300/20" />
              </label>
              {error && <p role="alert" className="rounded-xl border border-rose-400/20 bg-rose-400/10 px-3 py-2 text-sm text-rose-100">{error}</p>}
              <div className="flex flex-wrap justify-between gap-3 border-t border-white/5 pt-5">
                <button type="button" onClick={() => void resetAvatar()} disabled={busy || !profile.has_custom_avatar} className="text-xs text-slate-500 transition hover:text-cyan-200 disabled:cursor-not-allowed disabled:opacity-40">Use Google photo</button>
                <div className="flex gap-2">
                  <button type="button" onClick={closeEditor} disabled={busy} className="action-button reject">Cancel</button>
                  <button disabled={busy} className="flex min-h-10 items-center gap-2 rounded-xl bg-cyan-300 px-4 py-2 text-sm font-bold text-cyan-950 transition hover:-translate-y-0.5 hover:bg-cyan-200 disabled:opacity-50">
                    {busy && <LoaderCircle className="h-4 w-4 animate-spin" />} Save profile
                  </button>
                </div>
              </div>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
