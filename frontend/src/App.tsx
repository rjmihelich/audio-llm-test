import { useState } from "react";
import { NavLink, Routes, Route } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { listRuns } from "./api/client";
import Dashboard from "./pages/Dashboard";
import SpeechCorpus from "./pages/SpeechCorpus";
import TestSuites from "./pages/TestSuites";
import RunMonitor from "./pages/RunMonitor";
import Results from "./pages/Results";
import RunsList from "./pages/RunsList";
import TelephonySuites from "./pages/TelephonySuites";
import TelephonyRuns from "./pages/TelephonyRuns";
import Settings from "./pages/Settings";
import AudioBrowser from "./pages/AudioBrowser";
import Prompts from "./pages/Prompts";
import PipelineStudio from "./pipeline-studio/PipelineStudio";

const navItems = [
  { to: "/", label: "Dashboard", icon: "\u{1F4CA}" },
  { to: "/corpus", label: "Speech Corpus", icon: "\u{1F399}" },
  { to: "/browser", label: "Audio Browser", icon: "\u{1F50A}" },
  { to: "/tests", label: "LLM Test Suites", icon: "\u{1F9EA}" },
  { to: "/runs", label: "LLM Results", icon: "\u{1F3AF}" },
  { to: "/telephony", label: "Telephony Suites", icon: "\u{1F4DE}" },
  { to: "/telephony-runs", label: "Telephony Results", icon: "\u{1F4F6}" },
  { to: "/prompts", label: "Prompt Library", icon: "\u{1F4AC}" },
  { to: "/pipeline-studio", label: "Pipeline Studio", icon: "\u{1F527}" },
  { to: "/settings", label: "Settings", icon: "\u{2699}" },
];

export default function App() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const { data: runs } = useQuery({
    queryKey: ["runs"],
    queryFn: listRuns,
    refetchInterval: 5000,
  });
  const activeRunCount = runs?.filter((r) => r.status === "running").length ?? 0;

  const renderNavItems = (onItemClick?: () => void) =>
    navItems.map((item) => (
      <NavLink
        key={item.to}
        to={item.to}
        end={item.to === "/"}
        onClick={onItemClick}
        className={({ isActive }) =>
          `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
            isActive
              ? "bg-slate-700 text-white"
              : "text-slate-300 hover:bg-slate-700/50 hover:text-white"
          }`
        }
      >
        <span className="text-base">{item.icon}</span>
        {item.label}
        {item.to === "/runs" && activeRunCount > 0 && (
          <span className="ml-auto inline-flex items-center justify-center w-5 h-5 text-[10px] font-bold text-white bg-red-500 rounded-full">
            {activeRunCount}
          </span>
        )}
      </NavLink>
    ));

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Desktop sidebar */}
      <aside className="hidden md:flex w-56 bg-slate-800 text-white flex-col shrink-0">
        <div className="px-5 py-4 border-b border-slate-700">
          <h1 className="text-base font-bold tracking-tight">Voice Testing</h1>
          <p className="text-[11px] text-slate-400 mt-0.5">Audio Quality & LLM Evaluation</p>
        </div>
        <nav className="flex-1 px-3 py-3 space-y-0.5 overflow-y-auto">
          {renderNavItems()}
        </nav>
        <div className="px-5 py-3 border-t border-slate-700 text-xs text-slate-500">
          v1.0.0
        </div>
      </aside>

      {/* Mobile top bar */}
      <div className="fixed top-0 left-0 right-0 z-50 bg-slate-800 text-white shadow-lg md:hidden">
        <div className="flex items-center justify-between px-4 h-14">
          <h1 className="text-lg font-bold tracking-tight">Voice Testing</h1>
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-2 rounded-lg hover:bg-slate-700 transition-colors"
            aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
          >
            {mobileMenuOpen ? (
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Mobile menu overlay */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 z-[60] bg-slate-800 text-white pt-14 flex flex-col md:hidden">
          <div className="absolute top-0 left-0 right-0 h-14 flex items-center justify-between px-4">
            <h1 className="text-lg font-bold tracking-tight">Voice Testing</h1>
            <button
              onClick={() => setMobileMenuOpen(false)}
              className="p-2 rounded-lg hover:bg-slate-700 transition-colors"
              aria-label="Close menu"
            >
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <nav className="flex-1 px-3 py-4 space-y-1 overflow-auto">
            {renderNavItems(() => setMobileMenuOpen(false))}
          </nav>
          <div className="px-6 py-4 border-t border-slate-700 text-xs text-slate-500">
            v1.0.0
          </div>
        </div>
      )}

      {/* Main content */}
      <main className="flex-1 overflow-auto pt-14 md:pt-0">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/corpus" element={<SpeechCorpus />} />
          <Route path="/browser" element={<AudioBrowser />} />
          <Route path="/tests" element={<TestSuites />} />
          <Route path="/runs" element={<RunsList />} />
          <Route path="/telephony" element={<TelephonySuites />} />
          <Route path="/telephony-runs" element={<TelephonyRuns />} />
          <Route path="/runs/:id" element={<RunMonitor />} />
          <Route path="/results/:id" element={<Results />} />
          <Route path="/prompts" element={<Prompts />} />
          <Route path="/pipeline-studio" element={<PipelineStudio />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
