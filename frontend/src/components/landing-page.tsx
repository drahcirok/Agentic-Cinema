"use client";

import {
  ArrowRight,
  Bell,
  CheckCircle2,
  Clapperboard,
  Film,
  Layers3,
  Menu,
  ShieldCheck,
  Sparkles,
  Users,
  X,
  Zap,
} from "lucide-react";
import { useState } from "react";

type LandingPageProps = {
  onSignIn: () => Promise<void>;
};

const workflow = [
  ["01", "Turn notes into tasks", "Gemini interprets the note, suggests the responsible department, and sets its priority."],
  ["02", "Approve and assign", "The supervisor adjusts, rejects, or assigns the work to the right artist."],
  ["03", "Deliver with context", "The artist attaches notes, links, or private evidence for review."],
  ["04", "Close the loop", "QC approves or returns the task, and every decision is recorded in the history."],
];

const roles = [
  {
    icon: Clapperboard,
    role: "Producer",
    eyebrow: "Global overview",
    description: "Creates productions, organizes the team, and monitors each department's progress.",
    bullets: ["Project metrics", "Member management", "Complete visibility"],
  },
  {
    icon: ShieldCheck,
    role: "Supervisor",
    eyebrow: "Creative control",
    description: "Validates AI-assisted notes, assigns artists, and performs quality control.",
    bullets: ["Human decisions", "Assignment by department", "Review and feedback"],
  },
  {
    icon: Sparkles,
    role: "Artist",
    eyebrow: "Focused execution",
    description: "Receives only the work assigned to them and submits progress without operational noise.",
    bullets: ["Personal inbox", "Protected evidence", "Real-time statuses"],
  },
];

function Brand() {
  return (
    <a href="#inicio" className="group flex items-center gap-3" aria-label="FrameFlow, home">
      <span className="grid h-9 w-9 place-items-center rounded-xl border border-cyan-300/30 bg-cyan-300/10 text-cyan-200 transition group-hover:rotate-6 group-hover:bg-cyan-300/20">
        <Film size={18} />
      </span>
      <span className="text-sm font-bold tracking-[0.22em] text-white">
        FRAME<span className="text-cyan-300">FLOW</span>
      </span>
    </a>
  );
}

export default function LandingPage({ onSignIn }: LandingPageProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [signingIn, setSigningIn] = useState(false);
  const [signInError, setSignInError] = useState<string | null>(null);

  async function handleSignIn() {
    if (signingIn) return;
    setSigningIn(true);
    setSignInError(null);
    try {
      await onSignIn();
    } catch {
      setSignInError("Unable to sign in. Please try again.");
      setSigningIn(false);
    }
  }

  const signInLabel = signingIn ? "Opening Google…" : "Sign in";

  return (
    <main id="inicio" className="relative min-h-screen overflow-hidden bg-[#07101c] text-slate-100">
      <div className="landing-grid pointer-events-none absolute inset-0" />
      <div className="landing-orb landing-orb-one pointer-events-none absolute" />
      <div className="landing-orb landing-orb-two pointer-events-none absolute" />

      <nav className="relative z-50 border-b border-white/8 bg-[#07101c]/75 backdrop-blur-xl">
        <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-5 sm:px-8 lg:px-12">
          <Brand />
          <div className="hidden items-center gap-8 md:flex">
            <a href="#flujo" className="text-sm text-slate-400 transition hover:text-white">How it works</a>
            <a href="#roles" className="text-sm text-slate-400 transition hover:text-white">Roles</a>
            <a href="#seguridad" className="text-sm text-slate-400 transition hover:text-white">Security</a>
            <button onClick={() => void handleSignIn()} disabled={signingIn} className="group flex items-center gap-2 rounded-xl border border-cyan-300/40 bg-cyan-300/10 px-4 py-2.5 text-sm font-bold text-cyan-200 transition hover:bg-cyan-300 hover:text-cyan-950 disabled:cursor-wait disabled:opacity-60">
              {signInLabel}
              {!signingIn && <ArrowRight size={16} className="transition group-hover:translate-x-1" />}
            </button>
          </div>
          <button onClick={() => setMenuOpen((current) => !current)} className="grid h-10 w-10 place-items-center rounded-lg border border-slate-700 text-slate-200 md:hidden" aria-label={menuOpen ? "Close menu" : "Open menu"} aria-expanded={menuOpen}>
            {menuOpen ? <X size={19} /> : <Menu size={19} />}
          </button>
        </div>
        {menuOpen && (
          <div className="border-t border-white/8 bg-[#0b1625] px-5 py-5 md:hidden">
            <div className="mx-auto flex max-w-7xl flex-col gap-4">
              <a href="#flujo" onClick={() => setMenuOpen(false)} className="text-sm text-slate-300">How it works</a>
              <a href="#roles" onClick={() => setMenuOpen(false)} className="text-sm text-slate-300">Roles</a>
              <a href="#seguridad" onClick={() => setMenuOpen(false)} className="text-sm text-slate-300">Security</a>
              <button onClick={() => void handleSignIn()} disabled={signingIn} className="mt-2 rounded-xl bg-cyan-300 px-4 py-3 text-sm font-bold text-cyan-950 disabled:opacity-60">{signInLabel}</button>
            </div>
          </div>
        )}
      </nav>

      <section className="relative z-10 mx-auto grid min-h-[calc(100vh-5rem)] max-w-7xl items-center gap-16 px-5 py-16 sm:px-8 lg:grid-cols-[0.88fr_1.12fr] lg:px-12 lg:py-24">
        <div className="landing-rise">
          <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-cyan-300/20 bg-cyan-300/8 px-3 py-1.5 text-xs font-semibold text-cyan-200">
            <Sparkles size={14} /> Gemini-assisted post-production
          </div>
          <h1 className="max-w-3xl text-5xl font-semibold leading-[0.98] tracking-[-0.045em] text-white sm:text-6xl lg:text-7xl">
            From the director&apos;s note to a delivery{" "}
            <span className="landing-gradient-text">under control.</span>
          </h1>
          <p className="mt-7 max-w-xl text-base leading-8 text-slate-400 sm:text-lg">
            FrameFlow turns creative feedback into a clear workflow for producers,
            supervisors, and artists. Fewer lost messages. More visible decisions.
          </p>
          <div className="mt-9 flex flex-col gap-3 sm:flex-row">
            <button onClick={() => void handleSignIn()} disabled={signingIn} className="group flex min-h-12 items-center justify-center gap-2 rounded-xl bg-cyan-300 px-6 py-3 text-sm font-extrabold text-cyan-950 shadow-[0_0_40px_rgba(34,211,238,0.18)] transition hover:-translate-y-0.5 hover:bg-cyan-200 disabled:cursor-wait disabled:opacity-60">
              {signingIn ? "Opening Google…" : "Enter FrameFlow"}
              {!signingIn && <ArrowRight size={17} className="transition group-hover:translate-x-1" />}
            </button>
            <a href="#flujo" className="flex min-h-12 items-center justify-center rounded-xl border border-slate-700 px-6 py-3 text-sm font-semibold text-slate-300 transition hover:border-slate-500 hover:bg-white/5 hover:text-white">Explore the workflow</a>
          </div>
          {signInError && <p role="alert" className="mt-4 text-sm text-rose-300">{signInError}</p>}
          <div className="mt-10 flex flex-wrap gap-x-6 gap-y-3 text-xs text-slate-500">
            {["Google sign-in", "Data separated by production", "Private evidence"].map((item) => (
              <span key={item} className="flex items-center gap-2"><CheckCircle2 size={15} className="text-cyan-300" /> {item}</span>
            ))}
          </div>
        </div>

        <div className="landing-rise landing-delay relative mx-auto w-full max-w-2xl" aria-hidden="true">
          <div className="absolute -inset-8 rounded-[3rem] bg-cyan-300/5 blur-3xl" />
          <div className="landing-console relative overflow-hidden rounded-3xl border border-slate-600/60 bg-[#0d1929]/95 p-3 shadow-[0_35px_100px_rgba(0,0,0,0.55)] sm:p-5">
            <div className="mb-4 flex items-center justify-between border-b border-slate-700/70 pb-4">
              <div className="flex gap-2"><span className="h-2.5 w-2.5 rounded-full bg-rose-400/70" /><span className="h-2.5 w-2.5 rounded-full bg-amber-300/70" /><span className="h-2.5 w-2.5 rounded-full bg-emerald-400/70" /></div>
              <span className="font-mono text-[10px] tracking-[0.18em] text-slate-500">AURORA / LIVE WORKSPACE</span>
            </div>
            <div className="grid gap-3 sm:grid-cols-[125px_1fr]">
              <div className="hidden rounded-2xl border border-slate-700/70 bg-[#101d2f] p-3 sm:block">
                <div className="mb-5 h-7 rounded-lg bg-cyan-300/15" />
                {["Overview", "Decisions", "Tasks", "Team", "History"].map((item, index) => (
                  <div key={item} className={"mb-2 rounded-md px-2 py-2 text-[9px] " + (index === 1 ? "bg-cyan-300 text-cyan-950" : "text-slate-500")}>{item}</div>
                ))}
              </div>
              <div className="min-w-0">
                <div className="mb-4 flex items-center justify-between gap-4 rounded-2xl border border-slate-700/70 bg-[#101d2f] p-4">
                  <div><p className="text-[9px] font-bold tracking-widest text-cyan-300">DECISION ROOM</p><p className="mt-1 text-sm font-semibold text-white">Aurora Short Film</p></div>
                  <div className="rounded-xl border border-cyan-300/20 bg-cyan-300/10 px-3 py-2 text-center"><p className="text-[8px] uppercase text-cyan-200">To review</p><p className="text-xl font-bold text-white">3</p></div>
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  {[
                    ["To review", "AUR-SC02-014", "Clean up dialogue and room tone", "High"],
                    ["In progress", "AUR-SC05-031", "Remove equipment reflection", "Medium"],
                    ["Ready for QC", "AUR-SC08-006", "Final color balance", "High"],
                  ].map(([column, shot, note, priority], index) => (
                    <div key={column} className="min-w-0 rounded-2xl border border-slate-700/70 bg-[#101d2f] p-3">
                      <div className="mb-3 flex items-center justify-between gap-2"><span className="text-[9px] font-semibold text-slate-300">{column}</span><span className={"h-1.5 w-1.5 rounded-full " + (index === 1 ? "landing-pulse bg-amber-300" : "bg-cyan-300")} /></div>
                      <div className="rounded-xl border border-slate-700 bg-[#16243a] p-3"><p className="font-mono text-[8px] text-cyan-300">{shot}</p><p className="mt-2 text-[10px] leading-4 text-slate-300">{note}</p><span className="mt-3 inline-block rounded-full bg-amber-400/15 px-2 py-1 text-[7px] text-amber-200">{priority}</span></div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="landing-scan pointer-events-none absolute inset-x-0 h-px bg-gradient-to-r from-transparent via-cyan-300/60 to-transparent" />
          </div>
          <div className="landing-float absolute -bottom-7 -left-3 flex items-center gap-3 rounded-2xl border border-emerald-300/20 bg-[#0d1d28]/95 px-4 py-3 shadow-2xl backdrop-blur sm:-left-8">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-300/10 text-emerald-300"><CheckCircle2 size={18} /></span>
            <div><p className="text-[10px] text-slate-500">Latest update</p><p className="text-xs font-semibold text-white">QC approved</p></div>
          </div>
          <div className="landing-float landing-delay-two absolute -right-2 -top-8 hidden items-center gap-3 rounded-2xl border border-violet-300/20 bg-[#15172b]/95 px-4 py-3 shadow-2xl backdrop-blur sm:flex">
            <Sparkles size={17} className="text-violet-300" /><p className="text-xs font-semibold text-white">Gemini classified the note</p>
          </div>
        </div>
      </section>

      <section className="relative z-10 border-y border-white/8 bg-white/[0.018]">
        <div className="mx-auto grid max-w-7xl grid-cols-2 divide-x divide-white/8 px-5 sm:px-8 md:grid-cols-4 lg:px-12">
          {[["3", "coordinated roles"], ["4", "creative departments"], ["1", "reliable history"], ["100%", "per production"]].map(([value, label]) => (
            <div key={label} className="px-4 py-8 text-center sm:py-10"><p className="text-2xl font-semibold text-white sm:text-3xl">{value}</p><p className="mt-1 text-xs text-slate-500">{label}</p></div>
          ))}
        </div>
      </section>

      <section id="flujo" className="relative z-10 mx-auto max-w-7xl px-5 py-24 sm:px-8 lg:px-12 lg:py-32">
        <div className="max-w-2xl">
          <p className="text-xs font-bold tracking-[0.22em] text-cyan-300">ONE WORKFLOW, ZERO AMBIGUITY</p>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-white sm:text-5xl">Every decision has a clear origin and destination.</h2>
          <p className="mt-5 text-base leading-7 text-slate-400">FrameFlow supports the work from the first observation through final approval, without replacing human judgment.</p>
        </div>
        <div className="mt-14 grid gap-px overflow-hidden rounded-3xl border border-slate-700/70 bg-slate-700/70 md:grid-cols-2 lg:grid-cols-4">
          {workflow.map(([number, title, description]) => (
            <article key={number} className="landing-feature-card group relative min-h-64 bg-[#0d1929] p-7 transition hover:bg-[#112036]">
              <span className="font-mono text-xs text-cyan-300">{number}</span><h3 className="mt-10 text-lg font-semibold text-white">{title}</h3><p className="mt-3 text-sm leading-6 text-slate-400">{description}</p>
              <ArrowRight size={18} className="absolute bottom-7 left-7 text-slate-600 transition group-hover:translate-x-1 group-hover:text-cyan-300" />
            </article>
          ))}
        </div>
      </section>

      <section id="roles" className="relative z-10 border-y border-white/8 bg-[#0a1422] py-24 lg:py-32">
        <div className="mx-auto max-w-7xl px-5 sm:px-8 lg:px-12">
          <div className="mx-auto max-w-2xl text-center"><p className="text-xs font-bold tracking-[0.22em] text-cyan-300">A SPACE FOR EVERY ROLE</p><h2 className="mt-4 text-3xl font-semibold tracking-tight text-white sm:text-5xl">Everyone sees what they need. No one works in the dark.</h2></div>
          <div className="mt-14 grid gap-5 lg:grid-cols-3">
            {roles.map(({ icon: Icon, role, eyebrow, description, bullets }) => (
              <article key={role} className="landing-role-card rounded-3xl border border-slate-700/70 bg-[#101c2d] p-7 transition hover:-translate-y-1 hover:border-cyan-300/30">
                <div className="flex items-start justify-between"><span className="grid h-12 w-12 place-items-center rounded-2xl bg-cyan-300/10 text-cyan-300"><Icon size={22} /></span><span className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">{eyebrow}</span></div>
                <h3 className="mt-8 text-2xl font-semibold text-white">{role}</h3><p className="mt-3 min-h-20 text-sm leading-6 text-slate-400">{description}</p>
                <ul className="mt-6 space-y-3 border-t border-slate-700/70 pt-6">{bullets.map((bullet) => <li key={bullet} className="flex items-center gap-3 text-sm text-slate-300"><CheckCircle2 size={15} className="shrink-0 text-cyan-300" />{bullet}</li>)}</ul>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="seguridad" className="relative z-10 mx-auto grid max-w-7xl items-center gap-14 px-5 py-24 sm:px-8 lg:grid-cols-2 lg:px-12 lg:py-32">
        <div>
          <p className="text-xs font-bold tracking-[0.22em] text-cyan-300">PRIVATE BY DESIGN</p>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-white sm:text-5xl">Your productions stay separate. Your evidence stays private.</h2>
          <p className="mt-6 max-w-xl text-base leading-8 text-slate-400">Each project keeps its own members, tasks, and history. Role-based permissions and Google sign-in keep the work within the right team.</p>
          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            <div className="rounded-2xl border border-slate-700/70 bg-[#101c2d] p-5"><ShieldCheck className="text-cyan-300" size={21} /><p className="mt-4 text-sm font-semibold text-white">Access by production</p><p className="mt-2 text-xs leading-5 text-slate-500">Tickets, teams, and histories kept separate.</p></div>
            <div className="rounded-2xl border border-slate-700/70 bg-[#101c2d] p-5"><Bell className="text-cyan-300" size={21} /><p className="mt-4 text-sm font-semibold text-white">Context-aware alerts</p><p className="mt-2 text-xs leading-5 text-slate-500">Assignments and reviews stay visible.</p></div>
          </div>
        </div>
        <div className="relative overflow-hidden rounded-3xl border border-slate-700/70 bg-gradient-to-br from-[#101e31] to-[#0b1523] p-8 sm:p-10">
          <div className="absolute right-0 top-0 h-48 w-48 rounded-full bg-cyan-300/10 blur-3xl" />
          <div className="relative">
            <div className="flex items-center gap-3"><Layers3 size={22} className="text-cyan-300" /><p className="font-semibold text-white">Connected architecture</p></div>
            <div className="mt-8 space-y-3">
              {[["Gemini + Vertex AI", "Multimodal classification"], ["Cloud Run", "API and business rules"], ["Firestore + Storage", "Private data and evidence"], ["Firebase Auth", "Identity and access"]].map(([name, detail], index) => (
                <div key={name} className="flex items-center gap-4 rounded-2xl border border-white/8 bg-white/[0.025] p-4"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-cyan-300/10 font-mono text-xs text-cyan-300">0{index + 1}</span><div className="min-w-0"><p className="text-sm font-semibold text-white">{name}</p><p className="mt-1 text-xs text-slate-500">{detail}</p></div><Zap size={15} className="ml-auto shrink-0 text-slate-600" /></div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="relative z-10 px-5 pb-24 sm:px-8 lg:px-12">
        <div className="mx-auto max-w-7xl overflow-hidden rounded-[2rem] border border-cyan-300/20 bg-gradient-to-br from-cyan-300/12 via-[#101d2f] to-violet-400/10 p-8 text-center sm:p-14 lg:p-20">
          <Users className="mx-auto text-cyan-300" size={28} />
          <h2 className="mx-auto mt-6 max-w-3xl text-3xl font-semibold tracking-tight text-white sm:text-5xl">Let creativity flow. Keep decisions under control.</h2>
          <p className="mx-auto mt-5 max-w-xl text-sm leading-7 text-slate-400 sm:text-base">Sign in with Google, create your first production, and take a note through final approval.</p>
          <button onClick={() => void handleSignIn()} disabled={signingIn} className="group mx-auto mt-8 flex min-h-12 items-center justify-center gap-2 rounded-xl bg-cyan-300 px-7 py-3 text-sm font-extrabold text-cyan-950 transition hover:bg-cyan-200 disabled:opacity-60">{signingIn ? "Opening Google…" : "Get started with Google"}<ArrowRight size={17} className="transition group-hover:translate-x-1" /></button>
        </div>
      </section>

      <footer className="relative z-10 border-t border-white/8">
        <div className="mx-auto flex max-w-7xl flex-col gap-5 px-5 py-8 sm:flex-row sm:items-center sm:justify-between sm:px-8 lg:px-12"><Brand /><p className="text-xs text-slate-600">Smart control for post-production teams.</p></div>
      </footer>
    </main>
  );
}
