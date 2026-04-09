import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listPrompts,
  createPrompt,
  updatePrompt,
  deletePrompt,
  type PromptResponse,
} from "../api/client";

const DEFAULT_PROMPT = "You are a helpful in-car voice assistant.";

function PromptModal({
  initial,
  onClose,
}: {
  initial?: PromptResponse;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState(initial?.name ?? "");
  const [content, setContent] = useState(initial?.content ?? DEFAULT_PROMPT);
  const [description, setDescription] = useState(initial?.description ?? "");
  const [error, setError] = useState<string | null>(null);

  const createMut = useMutation({
    mutationFn: createPrompt,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["prompts"] }); onClose(); },
    onError: (e: Error) => setError(e.message),
  });
  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof updatePrompt>[1] }) =>
      updatePrompt(id, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["prompts"] }); onClose(); },
    onError: (e: Error) => setError(e.message),
  });

  const saving = createMut.isPending || updateMut.isPending;

  function handleSave() {
    setError(null);
    if (!name.trim()) { setError("Name is required"); return; }
    if (!content.trim()) { setError("Prompt content is required"); return; }
    if (initial) {
      updateMut.mutate({ id: initial.id, body: { name, content, description } });
    } else {
      createMut.mutate({ name, content, description });
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl mx-4 flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2 className="text-base font-semibold text-slate-800">
            {initial ? "Edit Prompt" : "New Prompt"}
          </h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">&times;</button>
        </div>
        <div className="px-6 py-4 space-y-4 flex-1 overflow-y-auto">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Name</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500"
              placeholder="e.g. Car Navigation Assistant"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Description <span className="text-slate-400 font-normal">(optional)</span></label>
            <input
              type="text"
              value={description}
              onChange={e => setDescription(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500"
              placeholder="Short description of what this prompt is for"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">System Prompt</label>
            <textarea
              value={content}
              onChange={e => setContent(e.target.value)}
              rows={10}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-slate-500 resize-y"
              placeholder="You are a helpful in-car voice assistant..."
            />
            <p className="text-xs text-slate-400 mt-1">{content.length} characters</p>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
        <div className="flex justify-end gap-3 px-6 py-4 border-t bg-slate-50 rounded-b-xl">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-lg border border-slate-300 text-slate-600 hover:bg-slate-100"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 text-sm rounded-lg bg-slate-800 text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {saving ? "Saving…" : (initial ? "Save Changes" : "Create Prompt")}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Prompts() {
  const qc = useQueryClient();
  const { data: prompts = [], isLoading } = useQuery({
    queryKey: ["prompts"],
    queryFn: listPrompts,
  });

  const [modal, setModal] = useState<"new" | PromptResponse | null>(null);
  const [copyId, setCopyId] = useState<string | null>(null);

  const deleteMut = useMutation({
    mutationFn: deletePrompt,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["prompts"] }),
  });

  function handleCopy(p: PromptResponse) {
    navigator.clipboard.writeText(p.content);
    setCopyId(p.id);
    setTimeout(() => setCopyId(null), 1500);
  }

  function handleDelete(p: PromptResponse) {
    if (confirm(`Delete prompt "${p.name}"? This cannot be undone.`)) {
      deleteMut.mutate(p.id);
    }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Prompt Library</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Manage reusable system prompts for LLM backends. Assign them when creating test suites or in Pipeline Studio.
          </p>
        </div>
        <button
          onClick={() => setModal("new")}
          className="px-4 py-2 bg-slate-800 text-white text-sm rounded-lg hover:bg-slate-700"
        >
          + New Prompt
        </button>
      </div>

      {isLoading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : prompts.length === 0 ? (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-10 text-center">
          <p className="text-slate-500 text-sm">No prompts yet.</p>
          <button
            onClick={() => setModal("new")}
            className="mt-3 px-4 py-2 bg-slate-800 text-white text-sm rounded-lg hover:bg-slate-700"
          >
            Create your first prompt
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {prompts.map(p => (
            <div key={p.id} className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-slate-800 text-sm truncate">{p.name}</h3>
                    {p.description && (
                      <span className="text-xs text-slate-400 truncate">{p.description}</span>
                    )}
                  </div>
                  <pre className="mt-2 text-xs text-slate-600 bg-slate-50 rounded-lg px-3 py-2 whitespace-pre-wrap font-mono max-h-32 overflow-y-auto border border-slate-100">
                    {p.content}
                  </pre>
                  <p className="text-[11px] text-slate-400 mt-1.5">
                    {p.content.length} chars · Updated {new Date(p.updated_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => handleCopy(p)}
                    title="Copy to clipboard"
                    className="px-2 py-1.5 text-xs rounded-lg text-slate-500 hover:bg-slate-100"
                  >
                    {copyId === p.id ? "Copied!" : "Copy"}
                  </button>
                  <button
                    onClick={() => setModal(p)}
                    className="px-2 py-1.5 text-xs rounded-lg text-slate-600 hover:bg-slate-100"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDelete(p)}
                    className="px-2 py-1.5 text-xs rounded-lg text-red-500 hover:bg-red-50"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {modal !== null && (
        <PromptModal
          initial={modal === "new" ? undefined : modal}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}
