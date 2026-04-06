import { NavLink, Routes, Route } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import SpeechCorpus from "./pages/SpeechCorpus";
import TestSuites from "./pages/TestSuites";
import RunMonitor from "./pages/RunMonitor";
import Results from "./pages/Results";
import Settings from "./pages/Settings";

const navItems = [
  { to: "/", label: "Dashboard", icon: "\u{1F4CA}" },
  { to: "/corpus", label: "Speech Corpus", icon: "\u{1F399}" },
  { to: "/tests", label: "Test Suites", icon: "\u{1F9EA}" },
  { to: "/settings", label: "Settings", icon: "\u{2699}" },
];

export default function App() {
  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="w-64 bg-slate-800 text-white flex flex-col shrink-0">
        <div className="px-6 py-5 border-b border-slate-700">
          <h1 className="text-lg font-bold tracking-tight">Audio LLM Test</h1>
          <p className="text-xs text-slate-400 mt-0.5">Quality Evaluation Platform</p>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
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
            </NavLink>
          ))}
        </nav>
        <div className="px-6 py-4 border-t border-slate-700 text-xs text-slate-500">
          v1.0.0
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/corpus" element={<SpeechCorpus />} />
          <Route path="/tests" element={<TestSuites />} />
          <Route path="/runs/:id" element={<RunMonitor />} />
          <Route path="/results/:id" element={<Results />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
