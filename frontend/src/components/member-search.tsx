"use client";

import { Check, LoaderCircle, Search, UserPlus, X } from "lucide-react";
import { useEffect, useState } from "react";

import UserAvatar from "@/components/user-avatar";
import type { UserProfile } from "@/lib/profile-types";

export default function MemberSearch({
  selected,
  onSelectedChange,
  apiBaseUrl,
  getAuthHeaders,
  productionId,
  excludedUids,
  disabled = false,
}: {
  selected: UserProfile | null;
  onSelectedChange: (profile: UserProfile | null) => void;
  apiBaseUrl: string;
  getAuthHeaders: () => Promise<Record<string, string>>;
  productionId: string;
  excludedUids: string[];
  disabled?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<UserProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const excludedKey = excludedUids.join("|");

  useEffect(() => {
    if (selected || disabled || query.trim().length < 2) return;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => {
      void (async () => {
        setLoading(true);
        setSearchError(null);
        try {
          const response = await fetch(
            `${apiBaseUrl}/profiles/search?q=${encodeURIComponent(query.trim())}&production_id=${encodeURIComponent(productionId)}`,
            { headers: await getAuthHeaders(), signal: controller.signal },
          );
          if (!response.ok) throw new Error("Unable to search for users.");
          const body = (await response.json()) as UserProfile[];
          const excluded = new Set(excludedKey.split("|").filter(Boolean));
          setResults(body.filter((profile) => !excluded.has(profile.uid)));
          setSearched(true);
        } catch (cause) {
          if ((cause as Error).name !== "AbortError") {
            setResults([]);
            setSearchError("We couldn't search the directory. Please try again.");
          }
        } finally {
          setLoading(false);
        }
      })();
    }, 320);
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [apiBaseUrl, disabled, excludedKey, getAuthHeaders, productionId, query, selected]);

  if (selected) {
    return (
      <div className="group flex items-center gap-3 rounded-2xl border border-cyan-300/25 bg-cyan-400/[.07] p-3 shadow-[inset_0_1px_rgba(255,255,255,.03)]">
        <UserAvatar profile={selected} apiBaseUrl={apiBaseUrl} getAuthHeaders={getAuthHeaders} size="lg" />
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold text-white">{selected.display_name}</p>
          <p className="truncate text-xs text-cyan-300">@{selected.username}</p>
          <p className="mt-1 truncate font-mono text-[9px] text-slate-500">{selected.uid}</p>
        </div>
        {disabled ? (
          <span className="flex items-center gap-1 rounded-full bg-emerald-400/10 px-2 py-1 text-[10px] font-semibold text-emerald-300"><Check className="h-3 w-3" /> Identity verified</span>
        ) : (
          <button type="button" onClick={() => { onSelectedChange(null); setQuery(""); }} className="rounded-full p-2 text-slate-500 transition hover:bg-white/5 hover:text-white" aria-label="Change user"><X className="h-4 w-4" /></button>
        )}
      </div>
    );
  }

  return (
    <div className="relative">
      <div className="workspace-input flex items-center gap-3 focus-within:border-cyan-300/70 focus-within:shadow-[0_0_0_3px_rgba(34,211,238,.06)]">
        {loading ? <LoaderCircle className="h-4 w-4 animate-spin text-cyan-300" /> : <Search className="h-4 w-4 text-slate-500" />}
        <input role="combobox" aria-label="Search for a team member" aria-autocomplete="list" aria-expanded={results.length > 0 || Boolean(searchError) || searched} aria-controls="member-search-results" value={query} onChange={(event) => { setQuery(event.target.value); setResults([]); setSearched(false); setSearchError(null); }} placeholder="Search by @username or paste their UID" className="min-w-0 flex-1 bg-transparent text-sm text-white outline-none placeholder:text-slate-500" autoComplete="off" />
      </div>
      {query.trim().length > 0 && query.trim().length < 2 && <p className="mt-2 text-[11px] text-slate-500">Enter at least 2 characters.</p>}
      {(results.length > 0 || searchError || (searched && !loading)) && (
        <div id="member-search-results" role="listbox" className="absolute left-0 right-0 top-[calc(100%+.5rem)] z-30 overflow-hidden rounded-2xl border border-slate-700/80 bg-[#0d1828]/98 p-2 shadow-[0_22px_60px_rgba(0,0,0,.5)] backdrop-blur-xl landing-rise">
          {searchError ? (
            <div className="px-4 py-5 text-center">
              <p className="text-sm text-rose-200">{searchError}</p>
              <p className="mt-1 text-[11px] text-slate-500">Check your connection or edit your search.</p>
            </div>
          ) : results.length === 0 ? (
            <div className="px-4 py-5 text-center">
              <UserPlus className="mx-auto h-5 w-5 text-slate-600" />
              <p className="mt-2 text-sm text-slate-400">We couldn&apos;t find that person.</p>
              <p className="mt-1 text-[11px] text-slate-600">They must have signed in to FrameFlow at least once.</p>
            </div>
          ) : results.map((profile) => (
            <button key={profile.uid} type="button" role="option" aria-selected="false" onClick={() => onSelectedChange(profile)} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition hover:bg-cyan-400/10">
              <UserAvatar profile={profile} apiBaseUrl={apiBaseUrl} getAuthHeaders={getAuthHeaders} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold text-white">{profile.display_name}</span>
                <span className="block truncate text-xs text-cyan-300">@{profile.username}</span>
              </span>
              <span className="rounded-full border border-slate-700 px-2 py-1 text-[9px] text-slate-500">Select</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
