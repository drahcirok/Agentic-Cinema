"use client";

import { useEffect, useMemo, useState } from "react";

import type { UserProfile } from "@/lib/profile-types";

type AvatarProfile = Pick<
  UserProfile,
  "uid" | "display_name" | "photo_url" | "has_custom_avatar"
> & { updated_at?: string };

export default function UserAvatar({
  profile,
  apiBaseUrl,
  getAuthHeaders,
  size = "md",
  className = "",
}: {
  profile: AvatarProfile;
  apiBaseUrl: string;
  getAuthHeaders: () => Promise<Record<string, string>>;
  size?: "sm" | "md" | "lg" | "xl";
  className?: string;
}) {
  const avatarKey = `${profile.uid}:${profile.updated_at ?? "current"}:${profile.has_custom_avatar}`;
  const [customSource, setCustomSource] = useState<{ key: string; url: string } | null>(null);
  const [failedSource, setFailedSource] = useState<string | null>(null);
  const initials = useMemo(
    () =>
      profile.display_name
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0]?.toUpperCase())
        .join("") || "FF",
    [profile.display_name],
  );

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    if (!profile.has_custom_avatar) return;
    void (async () => {
      try {
        const response = await fetch(
          `${apiBaseUrl}/profiles/${encodeURIComponent(profile.uid)}/avatar?v=${encodeURIComponent(profile.updated_at ?? "current")}`,
          { headers: await getAuthHeaders(), cache: "no-store" },
        );
        if (!response.ok) throw new Error("Avatar unavailable");
        objectUrl = URL.createObjectURL(await response.blob());
        if (active) setCustomSource({ key: avatarKey, url: objectUrl });
      } catch {
        // Keep the Google photo or initials as the graceful fallback.
      }
    })();
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [apiBaseUrl, avatarKey, getAuthHeaders, profile.has_custom_avatar, profile.uid, profile.updated_at]);

  const resolvedCustomSource = customSource?.key === avatarKey ? customSource.url : null;
  const source = resolvedCustomSource ?? profile.photo_url ?? null;
  const visibleSource = source && failedSource !== `${avatarKey}:${source}` ? source : null;
  const sizeClass = {
    sm: "h-8 w-8 text-[10px]",
    md: "h-10 w-10 text-xs",
    lg: "h-14 w-14 text-sm",
    xl: "h-24 w-24 text-xl",
  }[size];

  return (
    <span
      className={`relative grid shrink-0 place-items-center overflow-hidden rounded-full border border-cyan-300/25 bg-gradient-to-br from-cyan-300/25 via-slate-800 to-violet-400/20 font-bold tracking-wide text-cyan-100 shadow-[0_0_24px_rgba(34,211,238,.12)] ${sizeClass} ${className}`}
      aria-label={`Photo of ${profile.display_name}`}
    >
      {visibleSource ? (
        // Firebase and the protected avatar endpoint are both runtime URLs.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={visibleSource}
          alt=""
          className="h-full w-full object-cover"
          onError={() => setFailedSource(`${avatarKey}:${visibleSource}`)}
        />
      ) : (
        <span aria-hidden="true">{initials}</span>
      )}
    </span>
  );
}
