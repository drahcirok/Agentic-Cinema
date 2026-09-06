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
  ["01", "Convierte notas en tareas", "Gemini interpreta la nota, propone el área responsable y define su prioridad."],
  ["02", "Aprueba y asigna", "El supervisor corrige, rechaza o asigna el trabajo al artista adecuado."],
  ["03", "Entrega con contexto", "El artista adjunta notas, enlaces o evidencia privada para revisión."],
  ["04", "Cierra el ciclo", "QC aprueba o devuelve la tarea y cada decisión queda en el historial."],
];

const roles = [
  {
    icon: Clapperboard,
    role: "Productor",
    eyebrow: "Visión global",
    description: "Crea producciones, organiza el equipo y monitorea el avance de cada departamento.",
    bullets: ["Métricas del proyecto", "Gestión de miembros", "Visibilidad completa"],
  },
  {
    icon: ShieldCheck,
    role: "Supervisor",
    eyebrow: "Control creativo",
    description: "Valida las notas asistidas por IA, asigna artistas y realiza el control de calidad.",
    bullets: ["Decisiones humanas", "Asignación por área", "Revisión y feedback"],
  },
  {
    icon: Sparkles,
    role: "Artista",
    eyebrow: "Ejecución enfocada",
    description: "Recibe únicamente el trabajo que le corresponde y entrega avances sin ruido operativo.",
    bullets: ["Bandeja personal", "Evidencia protegida", "Estados en tiempo real"],
  },
];

function Brand() {
  return (
    <a href="#inicio" className="group flex items-center gap-3" aria-label="FrameFlow, inicio">
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
      setSignInError("No se pudo iniciar sesión. Inténtalo nuevamente.");
      setSigningIn(false);
    }
  }

  const signInLabel = signingIn ? "Abriendo Google…" : "Iniciar sesión";

  return (
    <main id="inicio" className="relative min-h-screen overflow-hidden bg-[#07101c] text-slate-100">
      <div className="landing-grid pointer-events-none absolute inset-0" />
      <div className="landing-orb landing-orb-one pointer-events-none absolute" />
      <div className="landing-orb landing-orb-two pointer-events-none absolute" />

      <nav className="relative z-50 border-b border-white/8 bg-[#07101c]/75 backdrop-blur-xl">
        <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-5 sm:px-8 lg:px-12">
          <Brand />
          <div className="hidden items-center gap-8 md:flex">
            <a href="#flujo" className="text-sm text-slate-400 transition hover:text-white">Cómo funciona</a>
            <a href="#roles" className="text-sm text-slate-400 transition hover:text-white">Roles</a>
            <a href="#seguridad" className="text-sm text-slate-400 transition hover:text-white">Seguridad</a>
            <button onClick={() => void handleSignIn()} disabled={signingIn} className="group flex items-center gap-2 rounded-xl border border-cyan-300/40 bg-cyan-300/10 px-4 py-2.5 text-sm font-bold text-cyan-200 transition hover:bg-cyan-300 hover:text-cyan-950 disabled:cursor-wait disabled:opacity-60">
              {signInLabel}
              {!signingIn && <ArrowRight size={16} className="transition group-hover:translate-x-1" />}
            </button>
          </div>
          <button onClick={() => setMenuOpen((current) => !current)} className="grid h-10 w-10 place-items-center rounded-lg border border-slate-700 text-slate-200 md:hidden" aria-label={menuOpen ? "Cerrar menú" : "Abrir menú"} aria-expanded={menuOpen}>
            {menuOpen ? <X size={19} /> : <Menu size={19} />}
          </button>
        </div>
        {menuOpen && (
          <div className="border-t border-white/8 bg-[#0b1625] px-5 py-5 md:hidden">
            <div className="mx-auto flex max-w-7xl flex-col gap-4">
              <a href="#flujo" onClick={() => setMenuOpen(false)} className="text-sm text-slate-300">Cómo funciona</a>
              <a href="#roles" onClick={() => setMenuOpen(false)} className="text-sm text-slate-300">Roles</a>
              <a href="#seguridad" onClick={() => setMenuOpen(false)} className="text-sm text-slate-300">Seguridad</a>
              <button onClick={() => void handleSignIn()} disabled={signingIn} className="mt-2 rounded-xl bg-cyan-300 px-4 py-3 text-sm font-bold text-cyan-950 disabled:opacity-60">{signInLabel}</button>
            </div>
          </div>
        )}
      </nav>

      <section className="relative z-10 mx-auto grid min-h-[calc(100vh-5rem)] max-w-7xl items-center gap-16 px-5 py-16 sm:px-8 lg:grid-cols-[0.88fr_1.12fr] lg:px-12 lg:py-24">
        <div className="landing-rise">
          <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-cyan-300/20 bg-cyan-300/8 px-3 py-1.5 text-xs font-semibold text-cyan-200">
            <Sparkles size={14} /> Postproducción asistida por Gemini
          </div>
          <h1 className="max-w-3xl text-5xl font-semibold leading-[0.98] tracking-[-0.045em] text-white sm:text-6xl lg:text-7xl">
            De la nota del director a una entrega{" "}
            <span className="landing-gradient-text">bajo control.</span>
          </h1>
          <p className="mt-7 max-w-xl text-base leading-8 text-slate-400 sm:text-lg">
            FrameFlow convierte observaciones creativas en un flujo claro para productores,
            supervisores y artistas. Menos mensajes perdidos. Más decisiones visibles.
          </p>
          <div className="mt-9 flex flex-col gap-3 sm:flex-row">
            <button onClick={() => void handleSignIn()} disabled={signingIn} className="group flex min-h-12 items-center justify-center gap-2 rounded-xl bg-cyan-300 px-6 py-3 text-sm font-extrabold text-cyan-950 shadow-[0_0_40px_rgba(34,211,238,0.18)] transition hover:-translate-y-0.5 hover:bg-cyan-200 disabled:cursor-wait disabled:opacity-60">
              {signingIn ? "Abriendo Google…" : "Entrar a FrameFlow"}
              {!signingIn && <ArrowRight size={17} className="transition group-hover:translate-x-1" />}
            </button>
            <a href="#flujo" className="flex min-h-12 items-center justify-center rounded-xl border border-slate-700 px-6 py-3 text-sm font-semibold text-slate-300 transition hover:border-slate-500 hover:bg-white/5 hover:text-white">Explorar el flujo</a>
          </div>
          {signInError && <p role="alert" className="mt-4 text-sm text-rose-300">{signInError}</p>}
          <div className="mt-10 flex flex-wrap gap-x-6 gap-y-3 text-xs text-slate-500">
            {["Acceso con Google", "Datos por producción", "Evidencia privada"].map((item) => (
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
                {["Resumen", "Decisiones", "Tareas", "Equipo", "Historial"].map((item, index) => (
                  <div key={item} className={"mb-2 rounded-md px-2 py-2 text-[9px] " + (index === 1 ? "bg-cyan-300 text-cyan-950" : "text-slate-500")}>{item}</div>
                ))}
              </div>
              <div className="min-w-0">
                <div className="mb-4 flex items-center justify-between gap-4 rounded-2xl border border-slate-700/70 bg-[#101d2f] p-4">
                  <div><p className="text-[9px] font-bold tracking-widest text-cyan-300">SALA DE DECISIONES</p><p className="mt-1 text-sm font-semibold text-white">Cortometraje Aurora</p></div>
                  <div className="rounded-xl border border-cyan-300/20 bg-cyan-300/10 px-3 py-2 text-center"><p className="text-[8px] uppercase text-cyan-200">Por revisar</p><p className="text-xl font-bold text-white">3</p></div>
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  {[
                    ["Por revisar", "AUR-SC02-014", "Limpiar diálogo y ruido de sala", "Alta"],
                    ["En proceso", "AUR-SC05-031", "Eliminar reflejo del equipo", "Media"],
                    ["Lista para QC", "AUR-SC08-006", "Balance final de color", "Alta"],
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
            <div><p className="text-[10px] text-slate-500">Última actualización</p><p className="text-xs font-semibold text-white">QC aprobado</p></div>
          </div>
          <div className="landing-float landing-delay-two absolute -right-2 -top-8 hidden items-center gap-3 rounded-2xl border border-violet-300/20 bg-[#15172b]/95 px-4 py-3 shadow-2xl backdrop-blur sm:flex">
            <Sparkles size={17} className="text-violet-300" /><p className="text-xs font-semibold text-white">Gemini clasificó la nota</p>
          </div>
        </div>
      </section>

      <section className="relative z-10 border-y border-white/8 bg-white/[0.018]">
        <div className="mx-auto grid max-w-7xl grid-cols-2 divide-x divide-white/8 px-5 sm:px-8 md:grid-cols-4 lg:px-12">
          {[["3", "roles coordinados"], ["4", "áreas creativas"], ["1", "historial confiable"], ["100%", "por producción"]].map(([value, label]) => (
            <div key={label} className="px-4 py-8 text-center sm:py-10"><p className="text-2xl font-semibold text-white sm:text-3xl">{value}</p><p className="mt-1 text-xs text-slate-500">{label}</p></div>
          ))}
        </div>
      </section>

      <section id="flujo" className="relative z-10 mx-auto max-w-7xl px-5 py-24 sm:px-8 lg:px-12 lg:py-32">
        <div className="max-w-2xl">
          <p className="text-xs font-bold tracking-[0.22em] text-cyan-300">UN FLUJO, CERO AMBIGÜEDAD</p>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-white sm:text-5xl">Cada decisión sabe de dónde viene y hacia dónde va.</h2>
          <p className="mt-5 text-base leading-7 text-slate-400">FrameFlow acompaña el trabajo desde la primera observación hasta la aprobación final, sin sustituir el criterio humano.</p>
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
          <div className="mx-auto max-w-2xl text-center"><p className="text-xs font-bold tracking-[0.22em] text-cyan-300">UN ESPACIO PARA CADA ROL</p><h2 className="mt-4 text-3xl font-semibold tracking-tight text-white sm:text-5xl">Todos ven lo necesario. Nadie trabaja a ciegas.</h2></div>
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
          <p className="text-xs font-bold tracking-[0.22em] text-cyan-300">PRIVADO POR DISEÑO</p>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-white sm:text-5xl">Tus producciones no se mezclan. Tu evidencia no es pública.</h2>
          <p className="mt-6 max-w-xl text-base leading-8 text-slate-400">Cada proyecto conserva sus miembros, tareas e historial. Los permisos por rol y el acceso con Google mantienen el trabajo dentro del equipo correcto.</p>
          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            <div className="rounded-2xl border border-slate-700/70 bg-[#101c2d] p-5"><ShieldCheck className="text-cyan-300" size={21} /><p className="mt-4 text-sm font-semibold text-white">Acceso por producción</p><p className="mt-2 text-xs leading-5 text-slate-500">Tickets, equipo e historial aislados.</p></div>
            <div className="rounded-2xl border border-slate-700/70 bg-[#101c2d] p-5"><Bell className="text-cyan-300" size={21} /><p className="mt-4 text-sm font-semibold text-white">Alertas con contexto</p><p className="mt-2 text-xs leading-5 text-slate-500">Asignaciones y revisiones visibles.</p></div>
          </div>
        </div>
        <div className="relative overflow-hidden rounded-3xl border border-slate-700/70 bg-gradient-to-br from-[#101e31] to-[#0b1523] p-8 sm:p-10">
          <div className="absolute right-0 top-0 h-48 w-48 rounded-full bg-cyan-300/10 blur-3xl" />
          <div className="relative">
            <div className="flex items-center gap-3"><Layers3 size={22} className="text-cyan-300" /><p className="font-semibold text-white">Arquitectura conectada</p></div>
            <div className="mt-8 space-y-3">
              {[["Gemini + Vertex AI", "Clasificación multimodal"], ["Cloud Run", "API y reglas de negocio"], ["Firestore + Storage", "Datos y evidencia privada"], ["Firebase Auth", "Identidad y acceso"]].map(([name, detail], index) => (
                <div key={name} className="flex items-center gap-4 rounded-2xl border border-white/8 bg-white/[0.025] p-4"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-cyan-300/10 font-mono text-xs text-cyan-300">0{index + 1}</span><div className="min-w-0"><p className="text-sm font-semibold text-white">{name}</p><p className="mt-1 text-xs text-slate-500">{detail}</p></div><Zap size={15} className="ml-auto shrink-0 text-slate-600" /></div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="relative z-10 px-5 pb-24 sm:px-8 lg:px-12">
        <div className="mx-auto max-w-7xl overflow-hidden rounded-[2rem] border border-cyan-300/20 bg-gradient-to-br from-cyan-300/12 via-[#101d2f] to-violet-400/10 p-8 text-center sm:p-14 lg:p-20">
          <Users className="mx-auto text-cyan-300" size={28} />
          <h2 className="mx-auto mt-6 max-w-3xl text-3xl font-semibold tracking-tight text-white sm:text-5xl">Haz que la creatividad fluya. Mantén las decisiones bajo control.</h2>
          <p className="mx-auto mt-5 max-w-xl text-sm leading-7 text-slate-400 sm:text-base">Entra con Google, crea tu primera producción y lleva una nota hasta su aprobación final.</p>
          <button onClick={() => void handleSignIn()} disabled={signingIn} className="group mx-auto mt-8 flex min-h-12 items-center justify-center gap-2 rounded-xl bg-cyan-300 px-7 py-3 text-sm font-extrabold text-cyan-950 transition hover:bg-cyan-200 disabled:opacity-60">{signingIn ? "Abriendo Google…" : "Comenzar con Google"}<ArrowRight size={17} className="transition group-hover:translate-x-1" /></button>
        </div>
      </section>

      <footer className="relative z-10 border-t border-white/8">
        <div className="mx-auto flex max-w-7xl flex-col gap-5 px-5 py-8 sm:flex-row sm:items-center sm:justify-between sm:px-8 lg:px-12"><Brand /><p className="text-xs text-slate-600">Control inteligente para equipos de postproducción.</p></div>
      </footer>
    </main>
  );
}
