"use client";

import { useState } from "react";
import { Save, Plus, Trash2, Upload, UserPlus } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Avatar } from "@/components/ui/avatar";

// ─── General ──────────────────────────────────────────────────────────────────

function GeneralSettings() {
  const [company, setCompany] = useState("Intra AI Corp");
  const [notifEmail, setNotifEmail] = useState(true);
  const [notifReport, setNotifReport] = useState(true);
  const [notifApp, setNotifApp] = useState(false);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Company Profile</CardTitle>
          <CardDescription>Basic information about your organization.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text-primary mb-1.5">
              Company Name
            </label>
            <Input
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              className="max-w-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-text-primary mb-1.5">
              Company Logo
            </label>
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-brand text-white text-lg font-bold">
                H
              </div>
              <Button variant="secondary" size="sm">
                <Upload className="h-4 w-4" />
                Upload Logo
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Notification Preferences</CardTitle>
          <CardDescription>Control which events trigger email notifications.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {[
            { id: "email", label: "New application submitted", value: notifEmail, set: setNotifEmail },
            { id: "report", label: "Interview report ready", value: notifReport, set: setNotifReport },
            { id: "app", label: "Candidate reschedules interview", value: notifApp, set: setNotifApp },
          ].map((item) => (
            <div key={item.id} className="flex items-center justify-between">
              <span className="text-sm text-text-primary">{item.label}</span>
              <button
                onClick={() => item.set((v) => !v)}
                className={[
                  "flex h-5 w-9 items-center rounded-full border-2 p-0.5 transition-all duration-200",
                  item.value ? "border-brand bg-brand" : "border-border bg-border",
                ].join(" ")}
              >
                <span
                  className={[
                    "h-3.5 w-3.5 rounded-full bg-white shadow transition-transform duration-200",
                    item.value ? "translate-x-4" : "translate-x-0",
                  ].join(" ")}
                />
              </button>
            </div>
          ))}
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button size="sm">
          <Save className="h-4 w-4" />
          Save Changes
        </Button>
      </div>
    </div>
  );
}

// ─── AI Configuration ─────────────────────────────────────────────────────────

const RUBRIC_WEIGHTS = [
  { key: "relevance", label: "Relevance" },
  { key: "depth", label: "Depth" },
  { key: "accuracy", label: "Accuracy" },
  { key: "communication", label: "Communication" },
  { key: "confidence", label: "Confidence" },
];

function AIConfig() {
  const [threshold, setThreshold] = useState(60);
  const [model, setModel] = useState("gpt-4o");
  const [weights, setWeights] = useState<Record<string, number>>({
    relevance: 25,
    depth: 25,
    accuracy: 20,
    communication: 20,
    confidence: 10,
  });

  const totalWeight = Object.values(weights).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Default Settings</CardTitle>
          <CardDescription>Applied to all new job postings unless overridden.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-text-primary">
                Default Eligibility Threshold
              </label>
              <span className="text-sm font-bold text-brand tabular-nums">
                {threshold}%
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              className="w-full max-w-sm h-2 rounded-full bg-border appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-brand [&::-webkit-slider-thumb]:shadow"
            />
            <p className="text-xs text-text-muted mt-1">
              Candidates below this score are auto-rejected.
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-text-primary mb-1.5">
              Evaluation Model
            </label>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="h-10 rounded-lg border border-input-border bg-surface px-3 text-sm text-text-primary focus:border-brand focus:ring-1 focus:ring-brand/20 transition-all duration-100 max-w-xs w-full"
            >
              <option value="gpt-4o">GPT-4o (Recommended)</option>
              <option value="claude-sonnet">Claude Sonnet 4.5</option>
              <option value="gemini-pro">Gemini 2.0 Pro</option>
            </select>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Rubric Weights</CardTitle>
          <CardDescription>
            Adjust how each dimension contributes to the overall score.{" "}
            <span className={totalWeight !== 100 ? "text-error font-semibold" : "text-success font-semibold"}>
              Total: {totalWeight}% {totalWeight !== 100 ? "(must equal 100%)" : ""}
            </span>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {RUBRIC_WEIGHTS.map(({ key, label }) => (
            <div key={key}>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-sm font-medium text-text-primary">
                  {label}
                </label>
                <div className="flex items-center gap-1.5">
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={weights[key]}
                    onChange={(e) =>
                      setWeights((prev) => ({
                        ...prev,
                        [key]: Number(e.target.value),
                      }))
                    }
                    className="w-16 h-8 text-center rounded-md border border-input-border bg-surface text-sm text-text-primary focus:border-brand focus:outline-none"
                  />
                  <span className="text-sm text-text-muted">%</span>
                </div>
              </div>
              <input
                type="range"
                min={0}
                max={50}
                step={5}
                value={weights[key]}
                onChange={(e) =>
                  setWeights((prev) => ({ ...prev, [key]: Number(e.target.value) }))
                }
                className="w-full h-2 rounded-full bg-border appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-brand [&::-webkit-slider-thumb]:shadow"
              />
            </div>
          ))}
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button size="sm">
          <Save className="h-4 w-4" />
          Save AI Config
        </Button>
      </div>
    </div>
  );
}

// ─── Templates ────────────────────────────────────────────────────────────────

const DEFAULT_TEMPLATES = [
  {
    id: "t1",
    name: "Introduction Round",
    type: "introduction",
    questions: [
      "Tell me about yourself and your background.",
      "What motivated you to apply for this role?",
      "Walk me through your most recent project.",
    ],
  },
  {
    id: "t2",
    name: "Behavioral Round",
    type: "behavioral",
    questions: [
      "Tell me about a time you faced a difficult challenge at work. How did you handle it?",
      "Describe a situation where you had to work with a difficult team member.",
      "Give an example of when you took initiative on a project.",
    ],
  },
];

function Templates() {
  const [templates] = useState(DEFAULT_TEMPLATES);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-text-muted">
          Question templates used for generating interview questions.
        </p>
        <Button size="sm">
          <Plus className="h-4 w-4" />
          New Template
        </Button>
      </div>
      {templates.map((t) => (
        <Card key={t.id}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>{t.name}</CardTitle>
              <Button variant="ghost" size="sm">
                <Trash2 className="h-4 w-4 text-error" />
              </Button>
            </div>
            <CardDescription className="capitalize">{t.type} round</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {t.questions.map((q, i) => (
              <div key={i}>
                <Textarea
                  defaultValue={q}
                  rows={2}
                  className="text-sm"
                />
              </div>
            ))}
            <Button variant="secondary" size="sm">
              <Plus className="h-4 w-4" />
              Add Question
            </Button>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// ─── Team ─────────────────────────────────────────────────────────────────────

const TEAM_MEMBERS = [
  { id: "u1", name: "Dhruv Agarwal", email: "dhruv@intra-ai.com", role: "Admin" },
  { id: "u2", name: "Anjali Singh", email: "anjali@intra-ai.com", role: "Recruiter" },
  { id: "u3", name: "Rahul Dev", email: "rahul.dev@intra-ai.com", role: "Recruiter" },
];

function TeamSettings() {
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("recruiter");

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Invite Team Member</CardTitle>
          <CardDescription>
            Send an invite to add a new recruiter or admin.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex-1 min-w-[200px]">
              <label className="block text-sm font-medium text-text-primary mb-1.5">
                Email Address
              </label>
              <Input
                type="email"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                placeholder="colleague@company.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-text-primary mb-1.5">
                Role
              </label>
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
                className="h-10 rounded-lg border border-input-border bg-surface px-3 text-sm text-text-primary focus:border-brand focus:outline-none"
              >
                <option value="recruiter">Recruiter</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <Button size="sm">
              <UserPlus className="h-4 w-4" />
              Send Invite
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Current Members ({TEAM_MEMBERS.length})</CardTitle>
        </CardHeader>
        <CardContent className="divide-y divide-border -my-1">
          {TEAM_MEMBERS.map((m) => (
            <div
              key={m.id}
              className="flex items-center justify-between py-3"
            >
              <div className="flex items-center gap-3">
                <Avatar size="sm" name={m.name} />
                <div>
                  <p className="text-sm font-medium text-text-primary">
                    {m.name}
                  </p>
                  <p className="text-xs text-text-muted">{m.email}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs font-medium text-text-muted bg-border rounded-full px-2 py-0.5">
                  {m.role}
                </span>
                {m.role !== "Admin" && (
                  <Button variant="ghost" size="sm" className="text-error">
                    Remove
                  </Button>
                )}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Settings</h1>
        <p className="text-sm text-text-muted mt-0.5">
          Configure your Intra AI workspace.
        </p>
      </div>

      <Tabs defaultValue="general">
        <TabsList>
          <TabsTrigger value="general">General</TabsTrigger>
          <TabsTrigger value="ai">AI Configuration</TabsTrigger>
          <TabsTrigger value="templates">Templates</TabsTrigger>
          <TabsTrigger value="team">Team</TabsTrigger>
        </TabsList>
        <TabsContent value="general">
          <GeneralSettings />
        </TabsContent>
        <TabsContent value="ai">
          <AIConfig />
        </TabsContent>
        <TabsContent value="templates">
          <Templates />
        </TabsContent>
        <TabsContent value="team">
          <TeamSettings />
        </TabsContent>
      </Tabs>
    </div>
  );
}
