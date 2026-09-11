"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  X,
  Plus,
  MapPin,
  Briefcase,
  DollarSign,
  FileText,
  Sparkles,
  Sliders,
  Send,
  Save,
  CheckCircle2,
  AlertCircle,
  Cpu,
  Compass,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useCreateJob, usePublishJob, useParseJdFile, useParseJdText } from "@/hooks/queries/useJobs";
import { FileUpload } from "@/components/ui/file-upload";
import { JdParsingPreview } from "@/components/jobs/jd-parsing-preview";
import { InterviewTemplatePicker } from "@/components/interviews/template-picker";
import { RoundSequencer } from "@/components/jobs/round-sequencer";
import { DurationBudgetBar } from "@/components/jobs/duration-budget-bar";
import { PublishValidationModal } from "@/components/jobs/publish-validation-modal";
import type { BackendJobCreatePayload, JdParseResponse } from "@/types/api";
import type { InterviewRoundConfig, InterviewRoundType, JobType } from "@/types";

const DEPARTMENTS = [
  "Engineering",
  "AI / Machine Learning",
  "Product Management",
  "Design / UX",
  "Data & Analytics",
  "Infrastructure & Cloud",
  "Security",
  "Developer Relations",
  "Sales",
  "Operations",
];

const EDUCATION_OPTIONS = [
  "Any",
  "High School Diploma",
  "Bachelor's Degree",
  "Master's Degree",
  "PhD",
];

const DEFAULT_ROUNDS: InterviewRoundConfig[] = [
  {
    type: "introduction",
    duration_minutes: 7,
    focus_areas: ["technical_depth", "user_empathy"],
    enabled: true,
    order_index: 1,
    agent_ids: ["alex"],
    agent_id: "alex",
  },
  {
    type: "technical",
    duration_minutes: 20,
    focus_areas: ["system_design", "software_architecture", "coding_problem_solving", "scalability"],
    enabled: true,
    order_index: 2,
    agent_ids: ["alex"],
    agent_id: "alex",
  },
  {
    type: "behavioral",
    duration_minutes: 15,
    focus_areas: ["product_sense", "customer_impact", "trade_off_analysis"],
    enabled: true,
    order_index: 3,
    agent_ids: ["jordan"],
    agent_id: "jordan",
  },
  {
    type: "hr_culture",
    duration_minutes: 10,
    focus_areas: ["stakeholder_management", "user_empathy"],
    enabled: true,
    order_index: 4,
    agent_ids: ["jordan"],
    agent_id: "jordan",
  },
];

const TECHNICAL_COMPETENCY_IDS = new Set([
  "system_design",
  "software_architecture",
  "coding_problem_solving",
  "scalability",
  "technical_decision_making",
  "debugging",
  "technical_depth",
  "distributed_systems",
  "database_optimization",
]);

const PRODUCT_COMPETENCY_IDS = new Set([
  "product_sense",
  "customer_impact",
  "trade_off_analysis",
  "metrics_and_roi",
  "user_empathy",
  "prioritization",
  "stakeholder_management",
]);

function uniqueValues(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

function buildAutoConfiguredRounds(suggestedCompetencies: string[]): InterviewRoundConfig[] {
  const extracted = new Set(suggestedCompetencies);
  const extractedTechnical = suggestedCompetencies.filter((id) => TECHNICAL_COMPETENCY_IDS.has(id));
  const extractedProduct = suggestedCompetencies.filter((id) => PRODUCT_COMPETENCY_IDS.has(id));

  return DEFAULT_ROUNDS.map((round) => {
    if (round.type === "technical") {
      return {
        ...round,
        enabled: true,
        focus_areas: uniqueValues([
          ...extractedTechnical,
          ...round.focus_areas,
        ]),
      };
    }
    if (round.type === "behavioral") {
      return {
        ...round,
        enabled: true,
        focus_areas: uniqueValues([
          ...extractedProduct,
          ...round.focus_areas,
        ]),
      };
    }
    if (round.type === "hr_culture") {
      return {
        ...round,
        enabled: true,
        focus_areas: uniqueValues([
          ...(extracted.has("stakeholder_management") ? ["stakeholder_management"] : []),
          ...(extracted.has("user_empathy") ? ["user_empathy"] : []),
          ...round.focus_areas,
        ]),
      };
    }
    return {
      ...round,
      enabled: true,
      focus_areas: uniqueValues([...extractedProduct, ...round.focus_areas]),
    };
  });
}

export default function NewJobPage() {
  const router = useRouter();

  // Active Wizard Tab: "jd-upload" | "details" | "rounds"
  const [activeTab, setActiveTab] = useState<string>("jd-upload");

  // Opportunity State
  const [title, setTitle] = useState("");
  const [department, setDepartment] = useState("Engineering");
  const [location, setLocation] = useState("Remote");
  const [jobType, setJobType] = useState<JobType>("remote");
  const [description, setDescription] = useState("");
  const [skills, setSkills] = useState<string[]>([]);
  const [skillInput, setSkillInput] = useState("");
  const [expMin, setExpMin] = useState<number>(2);
  const [expMax, setExpMax] = useState<number>(6);
  const [education, setEducation] = useState("Bachelor's Degree");
  const [salaryMin, setSalaryMin] = useState<string>("");
  const [salaryMax, setSalaryMax] = useState<string>("");
  const [threshold, setThreshold] = useState<number>(60);

  // Round Architecture State
  const [rounds, setRounds] = useState<InterviewRoundConfig[]>(DEFAULT_ROUNDS);

  // JD Parsing State
  const [parsedPreview, setParsedPreview] = useState<JdParseResponse | null>(null);
  const [selectedJdFile, setSelectedJdFile] = useState<File | null>(null);
  const [rawJdText, setRawJdText] = useState("");
  const [showRawTextEntry, setShowRawTextEntry] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);

  // Publish Modal State
  const [isPublishModalOpen, setIsPublishModalOpen] = useState(false);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Mutations
  const createJobMutation = useCreateJob();
  const publishJobMutation = usePublishJob();
  const parseJdFileMutation = useParseJdFile();
  const parseJdTextMutation = useParseJdText();

  // Parse the selected JD. Selection starts an automatic parse, while the
  // explicit button remains available when a browser/network request fails.
  const handleFileUpload = async (file: File) => {
    setParseError(null);
    try {
      const result = await parseJdFileMutation.mutateAsync(file);
      setParsedPreview(result);
    } catch (err: any) {
      setParseError(err?.message || "We could not read this file. Check the PDF and try Parse JD again.");
    }
  };

  const handleJdFileSelected = (file: File) => {
    setSelectedJdFile(file);
    void handleFileUpload(file);
  };

  const handleParseSelectedJd = () => {
    if (selectedJdFile) void handleFileUpload(selectedJdFile);
  };

  const handleClearJdFile = () => {
    setSelectedJdFile(null);
    setParsedPreview(null);
    setParseError(null);
  };

  // Handle Raw Text Parse
  const handleRawTextParse = async () => {
    if (!rawJdText.trim() || rawJdText.trim().length < 20) {
      setParseError("Please paste at least 20 characters of job description text.");
      return;
    }
    setParseError(null);
    try {
      const result = await parseJdTextMutation.mutateAsync({ text: rawJdText });
      setParsedPreview(result);
    } catch (err: any) {
      setParseError(err?.message || "Failed to parse text. Please check the content and try again.");
    }
  };

  // Apply parsed results to form state
  const handleConfirmParsed = (data: JdParseResponse) => {
    if (data.title) setTitle(data.title);
    if (data.department) setDepartment(data.department);
    if (data.location) setLocation(data.location);
    if (data.job_type && ["remote", "hybrid", "onsite"].includes(data.job_type)) {
      setJobType(data.job_type as JobType);
    }
    if (data.description) setDescription(data.description);
    if (data.required_skills && data.required_skills.length > 0) setSkills(uniqueValues(data.required_skills));
    if (data.experience_min !== null && data.experience_min !== undefined) {
      setExpMin(data.experience_min);
    }
    if (data.experience_max !== null && data.experience_max !== undefined) {
      setExpMax(data.experience_max);
    }
    if (data.education) setEducation(data.education);
    if (data.salary_min) setSalaryMin(String(data.salary_min));
    if (data.salary_max) setSalaryMax(String(data.salary_max));

    // Build a complete, publish-ready interview architecture from the JD.
    // Recruiters can still edit any round after this review step.
    setRounds(buildAutoConfiguredRounds(data.suggested_competencies || []));

    setParsedPreview(null);
    setGlobalError(null);
    setActiveTab("details");
  };

  // Skill Management
  const handleAddSkill = () => {
    const trimmed = skillInput.trim();
    if (trimmed && !skills.includes(trimmed)) {
      setSkills([...skills, trimmed]);
      setSkillInput("");
    }
  };

  const handleRemoveSkill = (skillToRemove: string) => {
    setSkills(skills.filter((s) => s !== skillToRemove));
  };

  // Build Payload
  const constructPayload = (): BackendJobCreatePayload => {
    return {
      title: title.trim(),
      department: department.trim(),
      location: location.trim(),
      job_type: jobType,
      description: description.trim(),
      required_skills: skills,
      experience_min: expMin,
      experience_max: expMax,
      salary_min: salaryMin ? parseFloat(salaryMin) : null,
      salary_max: salaryMax ? parseFloat(salaryMax) : null,
      education: education || null,
      eligibility_threshold: threshold,
      interview_rounds: rounds.filter((r) => r.enabled),
    };
  };

  // Save as Draft
  const handleSaveDraft = async () => {
    if (!title.trim()) {
      setGlobalError("Job Title is required to save a draft");
      setActiveTab("details");
      return;
    }
    if (!department.trim()) {
      setGlobalError("Department is required");
      setActiveTab("details");
      return;
    }
    if (skills.length === 0) {
      setGlobalError("Please add at least one required skill");
      setActiveTab("details");
      return;
    }

    setGlobalError(null);
    setIsSubmitting(true);
    try {
      const payload = constructPayload();
      const created = await createJobMutation.mutateAsync(payload);
      router.push(`/admin/jobs/${created.id}`);
    } catch (err: any) {
      setGlobalError(err?.message || "Failed to save draft");
    } finally {
      setIsSubmitting(false);
    }
  };

  // Publish Confirmed Handler
  const handleConfirmPublish = async () => {
    setGlobalError(null);
    setIsSubmitting(true);
    try {
      const payload = constructPayload();
      const created = await createJobMutation.mutateAsync(payload);
      if (created.id) {
        await publishJobMutation.mutateAsync(created.id);
        setIsPublishModalOpen(false);
        router.push(`/admin/jobs/${created.id}`);
      }
    } catch (err: any) {
      setGlobalError(err?.message || "Failed to publish opportunity");
      setIsPublishModalOpen(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto pb-16">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-5">
        <div className="flex items-center gap-3">
          <Link href="/admin/jobs">
            <Button
              variant="ghost"
              size="sm"
              className="h-9 w-9 p-0 rounded-lg text-text-muted hover:text-text-primary"
            >
              <ArrowLeft className="h-5 w-5" />
            </Button>
          </Link>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-text-primary">
              Create New Opportunity
            </h1>
            <p className="text-xs text-text-muted mt-0.5">
              Define candidate criteria, configure multi-agent interview rounds, and balance duration budgets.
            </p>
          </div>
        </div>

        {/* Global Error Banner */}
        {globalError && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-danger/10 border border-danger/30 text-danger text-xs">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{globalError}</span>
            <button
              type="button"
              onClick={() => setGlobalError(null)}
              className="p-0.5 text-danger/70 hover:text-danger ml-1"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        )}
      </div>

      {/* Main Stepper / Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList className="grid grid-cols-3 w-full sm:w-auto sm:inline-grid bg-card border border-border p-1 rounded-xl h-auto">
          <TabsTrigger
            value="jd-upload"
            className="gap-2 text-xs py-2 px-4 rounded-lg data-[state=active]:bg-surface data-[state=active]:shadow-xs"
          >
            <Sparkles className="h-3.5 w-3.5 text-brand" />
            <span>1. JD Document Upload</span>
          </TabsTrigger>
          <TabsTrigger
            value="details"
            className="gap-2 text-xs py-2 px-4 rounded-lg data-[state=active]:bg-surface data-[state=active]:shadow-xs"
          >
            <FileText className="h-3.5 w-3.5" />
            <span>2. Role Specifications</span>
          </TabsTrigger>
          <TabsTrigger
            value="rounds"
            className="gap-2 text-xs py-2 px-4 rounded-lg data-[state=active]:bg-surface data-[state=active]:shadow-xs"
          >
            <Sliders className="h-3.5 w-3.5" />
            <span>3. Round Architecture</span>
          </TabsTrigger>
        </TabsList>

        {/* TAB 1: JD DOCUMENT UPLOAD & PARSING */}
        <TabsContent value="jd-upload" className="space-y-6 animate-in fade-in-50">
          {parsedPreview ? (
            <JdParsingPreview
              initialData={parsedPreview}
              onConfirm={handleConfirmParsed}
              onDiscard={() => setParsedPreview(null)}
            />
          ) : (
            <Card className="border-border shadow-xs">
              <CardHeader>
                <div className="flex items-center gap-2.5">
                  <div className="h-8 w-8 rounded-lg bg-brand/10 text-brand flex items-center justify-center">
                    <Sparkles className="h-4 w-4" />
                  </div>
                  <div>
                    <CardTitle className="text-base">Smart Job Description Ingestion</CardTitle>
                    <CardDescription className="text-xs">
                      Upload a PDF or Word document and Intra AI will extract the role details, skills, experience, and interview focus automatically.
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>

              <CardContent className="space-y-5">
                {/* Upload Dropzone */}
                {!showRawTextEntry ? (
                  <div className="space-y-3">
                    <FileUpload
                      accept={[".pdf", ".docx", ".doc", ".txt"]}
                      maxSizeMb={10}
                      onFileSelect={handleJdFileSelected}
                      onClearFile={handleClearJdFile}
                      onParse={handleParseSelectedJd}
                      parseLabel="Parse JD"
                      isParsing={parseJdFileMutation.isPending}
                      currentFile={selectedJdFile}
                      isUploading={parseJdFileMutation.isPending}
                      error={parseError}
                      onClearError={() => setParseError(null)}
                      label="Upload Job Description Document"
                      description="Drop a PDF or DOCX here. We will analyze it automatically."
                      uploadingLabel="Analyzing your job description..."
                      uploadingDescription="Extracting role details, skills, experience, and interview focus"
                    />
                    <div className="text-center">
                      <button
                        type="button"
                        onClick={() => setShowRawTextEntry(true)}
                        className="text-xs text-brand hover:underline font-medium"
                      >
                        Prefer to paste raw text instead? Click here
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-medium text-text-secondary">
                        Paste Job Description Text
                      </label>
                      <button
                        type="button"
                        onClick={() => setShowRawTextEntry(false)}
                        className="text-xs text-brand hover:underline font-medium"
                      >
                        Switch back to file upload
                      </button>
                    </div>
                    <Textarea
                      rows={8}
                      value={rawJdText}
                      onChange={(e) => setRawJdText(e.target.value)}
                      placeholder="Paste the full job description, requirements, and responsibilities here..."
                      className="text-xs leading-relaxed"
                    />
                    {parseError && (
                      <p className="text-xs text-danger font-medium">{parseError}</p>
                    )}
                    <Button
                      type="button"
                      size="sm"
                      onClick={handleRawTextParse}
                      disabled={parseJdTextMutation.isPending}
                      className="gap-1.5 text-xs bg-brand text-white"
                    >
                      {parseJdTextMutation.isPending ? (
                        <>Analyzing job description...</>
                      ) : (
                        <>
                          <Sparkles className="h-3.5 w-3.5" />
                          Analyze JD Text
                        </>
                      )}
                    </Button>
                  </div>
                )}

                {/* Manual Alternative Callout */}
                <div className="pt-4 border-t border-border flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-bg/40 p-3 rounded-lg">
                  <div>
                    <p className="text-xs font-medium text-text-primary">
                      Don&apos;t have a document ready?
                    </p>
                    <p className="text-[11px] text-text-muted">
                      You can skip document upload and define the opportunity specifications manually.
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => setActiveTab("details")}
                    className="text-xs shrink-0"
                  >
                    Configure Manually
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* TAB 2: ROLE SPECIFICATIONS */}
        <TabsContent value="details" className="space-y-6 animate-in fade-in-50">
          <Card className="border-border shadow-xs">
            <CardHeader className="pb-4 border-b border-border">
              <CardTitle className="text-base font-semibold">Role Specifications</CardTitle>
              <CardDescription className="text-xs">
                Hiring criteria, department context, candidate requirements, and screening threshold.
              </CardDescription>
            </CardHeader>

            <CardContent className="pt-5 space-y-5">
              {/* Row 1: Title, Dept, Location, Type */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-text-secondary">
                    Opportunity Title *
                  </label>
                  <Input
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="e.g. Senior Backend Engineer"
                    className="text-sm"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-text-secondary">Department *</label>
                  <select
                    value={department}
                    onChange={(e) => setDepartment(e.target.value)}
                    className="w-full h-9 rounded-md border border-border bg-bg px-3 py-1 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-brand"
                  >
                    {DEPARTMENTS.map((d) => (
                      <option key={d} value={d}>
                        {d}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-text-secondary">Location *</label>
                  <Input
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                    placeholder="e.g. Remote, San Francisco, CA"
                    className="text-sm"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-text-secondary">Work Model</label>
                  <select
                    value={jobType}
                    onChange={(e) => setJobType(e.target.value as JobType)}
                    className="w-full h-9 rounded-md border border-border bg-bg px-3 py-1 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-brand"
                  >
                    <option value="remote">Remote</option>
                    <option value="hybrid">Hybrid</option>
                    <option value="onsite">On-site</option>
                  </select>
                </div>
              </div>

              {/* Description */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-text-secondary">
                  Role Description & Scope *
                </label>
                <Textarea
                  rows={4}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Describe the core responsibilities, key technical challenges, and team expectations..."
                  className="text-xs leading-relaxed"
                />
              </div>

              {/* Skills Tag Input */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-text-secondary">
                    Required Skills * ({skills.length})
                  </label>
                  <span className="text-[11px] text-text-muted">
                    Type and press Enter to add skills
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5 p-3 rounded-lg border border-border bg-bg/50 min-h-[50px]">
                  {skills.map((skill) => (
                    <span
                      key={skill}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-card border border-border text-xs font-medium text-text-primary shadow-xs"
                    >
                      {skill}
                      <button
                        type="button"
                        onClick={() => handleRemoveSkill(skill)}
                        className="text-text-muted hover:text-danger rounded p-0.5"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                  <div className="inline-flex items-center gap-1">
                    <input
                      type="text"
                      value={skillInput}
                      onChange={(e) => setSkillInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === ",") {
                          e.preventDefault();
                          handleAddSkill();
                        }
                      }}
                      placeholder="Add skill..."
                      className="h-7 text-xs bg-transparent px-2 border-none outline-none focus:ring-0 w-28 text-text-primary placeholder:text-text-muted"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={handleAddSkill}
                      className="h-6 w-6 p-0 text-text-muted hover:text-brand"
                    >
                      <Plus className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              </div>

              {/* Experience, Education & Compensation */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 pt-1">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-text-secondary">
                    Min Experience (Years)
                  </label>
                  <Input
                    type="number"
                    min={0}
                    max={25}
                    value={expMin}
                    onChange={(e) => setExpMin(parseInt(e.target.value) || 0)}
                    className="text-sm"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-text-secondary">
                    Max Experience (Years)
                  </label>
                  <Input
                    type="number"
                    min={0}
                    max={30}
                    value={expMax}
                    onChange={(e) => setExpMax(parseInt(e.target.value) || 0)}
                    className="text-sm"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-text-secondary">Education</label>
                  <select
                    value={education}
                    onChange={(e) => setEducation(e.target.value)}
                    className="w-full h-9 rounded-md border border-border bg-bg px-3 py-1 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-brand"
                  >
                    {EDUCATION_OPTIONS.map((edu) => (
                      <option key={edu} value={edu}>
                        {edu}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-text-secondary">
                    Screening Eligibility Threshold
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      type="range"
                      min={30}
                      max={90}
                      value={threshold}
                      onChange={(e) => setThreshold(parseInt(e.target.value))}
                      className="w-full accent-brand"
                    />
                    <span className="text-xs font-mono font-bold text-brand w-10 text-right">
                      {threshold}%
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex justify-end pt-3">
                <Button
                  type="button"
                  size="sm"
                  onClick={() => setActiveTab("rounds")}
                  className="bg-brand text-white text-xs"
                >
                  Proceed to Round Architecture →
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* TAB 3: ROUND ARCHITECTURE & AGENT MAPPING */}
        <TabsContent value="rounds" className="space-y-6 animate-in fade-in-50">
          <Card className="border-border shadow-xs">
            <CardHeader className="pb-4 border-b border-border">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                <div>
                  <CardTitle className="text-base font-semibold">
                    Interview Rounds
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Choose the interviewers, topics, and time for each round.
                  </CardDescription>
                </div>
              </div>
            </CardHeader>

            <CardContent className="pt-5 space-y-6">
              <InterviewTemplatePicker onApply={setRounds} />
              {/* Round Sequencer Component */}
              <RoundSequencer rounds={rounds} onChange={setRounds} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Floating / Sticky Bottom Bar with Duration Budget & Actions */}
      <div className="sticky bottom-4 z-40 bg-card/95 backdrop-blur-md border border-border rounded-xl p-4 shadow-lg space-y-3">
        <DurationBudgetBar rounds={rounds} maxMinutes={60} minMinutes={15} />

        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pt-2 border-t border-border">
          <div className="text-xs text-text-muted">
            {title ? (
              <span className="font-medium text-text-primary">
                Drafting: <span className="text-brand font-semibold">{title}</span>
              </span>
            ) : (
              <span>New Opportunity Configuration</span>
            )}
          </div>

          <div className="flex items-center gap-2.5 justify-end">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={handleSaveDraft}
              disabled={isSubmitting}
              className="text-xs h-9 gap-1.5"
            >
              <Save className="h-3.5 w-3.5" />
              Save as Draft
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={() => setIsPublishModalOpen(true)}
              disabled={isSubmitting}
              className="text-xs h-9 bg-brand hover:bg-brand-hover text-white gap-1.5 shadow-sm"
            >
              <Send className="h-3.5 w-3.5" />
              Publish Opportunity
            </Button>
          </div>
        </div>
      </div>

      {/* Publish Pre-Flight Validation Modal */}
      <PublishValidationModal
        open={isPublishModalOpen}
        onOpenChange={setIsPublishModalOpen}
        data={{
          title,
          department,
          location,
          description,
          skills,
          rounds,
        }}
        onConfirmPublish={handleConfirmPublish}
        isPublishing={isSubmitting}
      />
    </div>
  );
}
