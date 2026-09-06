"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Bot, Users, Play, Loader2, Link as LinkIcon, Copy, CheckCircle2 } from "lucide-react";

export default function TestLauncherPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultLink, setResultLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const [formData, setFormData] = useState({
    interview_id: `test-${Math.floor(Math.random() * 10000)}`,
    candidate_id: "cand-demo",
    job_title: "Senior Software Engineer",
    company: "Acme Corp",
    duration_minutes: 60,
    agent_alex: true,
    agent_jordan: true,
  });

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResultLink(null);

    const agent_ids = [];
    if (formData.agent_alex) agent_ids.push("alex");
    if (formData.agent_jordan) agent_ids.push("jordan");

    if (agent_ids.length === 0) {
      setError("Please select at least one agent.");
      setLoading(false);
      return;
    }

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${apiUrl}/api/v1/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          interview_id: formData.interview_id,
          candidate_id: formData.candidate_id,
          agent_ids,
          duration_minutes: formData.duration_minutes,
          job_title: formData.job_title,
          company: formData.company,
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || errData.message || "Failed to create session");
      }

      const data = await res.json();
      const link = `${window.location.origin}/interview/${data.interview_id}/prep`;
      setResultLink(link);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (resultLink) {
      navigator.clipboard.writeText(resultLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleJoin = () => {
    if (resultLink) {
      window.location.href = resultLink;
    }
  };

  return (
    <div className="min-h-screen bg-gray-950 text-white p-8 flex items-center justify-center font-sans">
      <div className="max-w-xl w-full bg-gray-900 border border-white/10 rounded-2xl p-8 shadow-2xl">
        <div className="flex items-center gap-3 mb-6 pb-6 border-b border-white/10">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-brand to-blue-600 flex items-center justify-center">
            <Bot className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold">Interview Test Launcher</h1>
            <p className="text-sm text-white/50">Create a session instantly without the platform</p>
          </div>
        </div>

        <form onSubmit={handleCreate} className="space-y-5">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-white/70">Interview ID</label>
              <input
                type="text"
                value={formData.interview_id}
                onChange={(e) => setFormData({ ...formData, interview_id: e.target.value })}
                className="w-full bg-gray-950 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:border-brand focus:outline-none transition-colors"
                required
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-white/70">Candidate ID</label>
              <input
                type="text"
                value={formData.candidate_id}
                onChange={(e) => setFormData({ ...formData, candidate_id: e.target.value })}
                className="w-full bg-gray-950 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:border-brand focus:outline-none transition-colors"
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-white/70">Job Title</label>
              <input
                type="text"
                value={formData.job_title}
                onChange={(e) => setFormData({ ...formData, job_title: e.target.value })}
                className="w-full bg-gray-950 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:border-brand focus:outline-none transition-colors"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-white/70">Company</label>
              <input
                type="text"
                value={formData.company}
                onChange={(e) => setFormData({ ...formData, company: e.target.value })}
                className="w-full bg-gray-950 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:border-brand focus:outline-none transition-colors"
              />
            </div>
          </div>

          <div className="space-y-2 pt-2">
            <label className="text-xs font-semibold text-white/70 flex items-center gap-2">
              <Users className="h-3.5 w-3.5" /> Select Agents
            </label>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 cursor-pointer bg-gray-950 border border-white/10 px-4 py-3 rounded-xl flex-1 hover:border-brand/50 transition-colors">
                <input
                  type="checkbox"
                  checked={formData.agent_alex}
                  onChange={(e) => setFormData({ ...formData, agent_alex: e.target.checked })}
                  className="accent-brand h-4 w-4"
                />
                <span className="text-sm font-medium">Alex (Technical)</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer bg-gray-950 border border-white/10 px-4 py-3 rounded-xl flex-1 hover:border-brand/50 transition-colors">
                <input
                  type="checkbox"
                  checked={formData.agent_jordan}
                  onChange={(e) => setFormData({ ...formData, agent_jordan: e.target.checked })}
                  className="accent-brand h-4 w-4"
                />
                <span className="text-sm font-medium">Jordan (Product)</span>
              </label>
            </div>
          </div>

          {error && (
            <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-xl">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-brand hover:bg-brand/90 text-white font-semibold py-3 px-4 rounded-xl flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Create Interview Session
          </button>
        </form>

        {resultLink && (
          <div className="mt-6 pt-6 border-t border-white/10 animate-in fade-in slide-in-from-bottom-4 duration-300">
            <h3 className="text-sm font-semibold text-emerald-400 mb-3 flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" /> Session Created Successfully!
            </h3>
            
            <div className="bg-gray-950 border border-white/10 rounded-xl p-4 flex flex-col gap-3">
              <p className="text-xs text-white/50">Candidate Lobby Link:</p>
              <div className="flex gap-2">
                <input 
                  readOnly 
                  value={resultLink} 
                  className="flex-1 bg-gray-900 border border-white/5 rounded-lg px-3 py-2 text-xs text-white/70 focus:outline-none"
                />
                <button 
                  onClick={handleCopy}
                  className="bg-white/5 hover:bg-white/10 p-2 rounded-lg transition-colors text-white/70"
                  title="Copy link"
                >
                  {copied ? <CheckCircle2 className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
                </button>
              </div>
              <button 
                onClick={handleJoin}
                className="mt-2 w-full bg-white/10 hover:bg-white/15 text-white text-sm font-medium py-2.5 rounded-lg flex items-center justify-center gap-2 transition-colors"
              >
                <LinkIcon className="h-4 w-4" /> Go to Candidate Prep Room
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
