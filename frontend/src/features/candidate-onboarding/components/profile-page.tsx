"use client";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/context/AuthContext";
import { onboardingApi, type ResumeVersion } from "../api";

export default function ProfilePage() {
  const { user } = useAuth(); const cache = useQueryClient();
  const [file, setFile] = useState<File | null>(null); const requestId = useRef("");
  const [downloadError, setDownloadError] = useState("");
  const status = useQuery({ queryKey: ["onboarding", user?.id], queryFn: onboardingApi.status, retry: false });
  const versions = useQuery({ queryKey: ["resume-versions", user?.id], queryFn: onboardingApi.versions, retry: false });
  const upload = useMutation({ mutationFn: async () => {
    if (!file || !status.data) throw new Error("Choose a resume and wait for your profile to load");
    return onboardingApi.upload(file, status.data.revision, requestId.current);
  }, onSuccess: () => { setFile(null); requestId.current = ""; void cache.invalidateQueries({ queryKey: ["onboarding"] }); void cache.invalidateQueries({ queryKey: ["resume-versions"] }); } });
  async function download(version: ResumeVersion) {
    try { setDownloadError(""); const blob = await onboardingApi.download(version.id); const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = `resume-v${version.version}.${version.extension}`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { setDownloadError(error instanceof Error ? error.message : "Download failed"); }
  }
  const profile = status.data?.profile;
  return <div className="space-y-6">
    <div><h1 className="text-3xl font-semibold text-text-primary">Your profile</h1><p className="mt-2 text-text-muted">Your resume stays private. Replacing it updates your profile while preserving earlier applications.</p></div>
    {status.isPending && <p role="status">Loading profile...</p>}
    {status.error && <p role="alert" className="text-error">{status.error.message}</p>}
    <section className="rounded-2xl border border-border bg-surface p-6 space-y-4">
      <h2 className="text-lg font-semibold">{status.data?.current ? "Replace resume" : "Upload resume"}</h2>
      <label className="block text-sm font-medium" htmlFor="resume-upload">PDF or DOCX, up to 8 MB. Text-based documents only.</label>
      <input id="resume-upload" type="file" accept=".pdf,.docx" className="block w-full text-sm" onChange={e => { setFile(e.target.files?.[0] || null); requestId.current = crypto.randomUUID(); upload.reset(); }} />
      <button disabled={!file || !status.data || upload.isPending} onClick={() => upload.mutate()} className="rounded-lg bg-brand px-5 py-2.5 font-medium text-white disabled:opacity-50">{upload.isPending ? "Parsing and saving..." : "Save resume"}</button>
      {upload.error && <p role="alert" className="text-error">{upload.error.message}</p>}
      {upload.isSuccess && <p role="status" className="text-success">Resume saved. Your profile is ready.</p>}
      {status.data?.current?.parse_source === "local_fallback" && <p className="text-sm text-text-muted">Basic extraction was used because AI parsing was unavailable. Only detected facts are shown.</p>}
    </section>
    {profile && <section className="rounded-2xl border border-border bg-surface p-6 space-y-4"><h2 className="text-lg font-semibold">Parsed profile</h2>
      <div className="flex flex-wrap gap-2">{profile.skills.map(skill => <span key={skill} className="rounded-full bg-brand-light px-3 py-1 text-sm text-brand">{skill}</span>)}</div>
      {profile.experience.map((exp, i) => <p key={i}>{exp.role} <span className="text-text-muted">at {exp.company}</span></p>)}
      {profile.education.map((edu, i) => <p key={i}>{edu.degree}, {edu.institution}</p>)}
      {profile.projects.map((project, i) => <p key={i}><strong>{project.name}</strong>: {project.description}</p>)}
    </section>}
    <section className="rounded-2xl border border-border bg-surface p-6"><h2 className="text-lg font-semibold mb-3">Resume history</h2>
      {versions.error && <p role="alert" className="text-error">{versions.error.message}</p>}
      {!versions.data?.length && <p className="text-sm text-text-muted">Uploaded profile resumes will appear here.</p>}
      <ul className="divide-y divide-border">{versions.data?.map(version => <li key={version.id} className="flex flex-wrap items-center justify-between gap-3 py-3"><div className="min-w-0"><p className="break-all">{version.filename} <span className="text-text-muted">v{version.version}</span></p><p className="text-xs text-text-muted">{new Date(version.created_at).toLocaleString()}</p></div><button onClick={() => void download(version)} className="text-sm text-brand underline">Download</button></li>)}</ul>
      {downloadError && <p role="alert" className="text-error">{downloadError}</p>}
    </section>
  </div>;
}
