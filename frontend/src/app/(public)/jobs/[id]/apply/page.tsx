"use client";

import { useState, useEffect, use } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Check, AlertCircle, Briefcase, FileText, User, IndianRupee } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FileUpload } from "@/components/ui/file-upload";
import { usePublicJob } from "@/hooks/queries/useJobs";
import { useApplyToJob } from "@/hooks/queries/useApplications";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { useMutation } from "@tanstack/react-query";
import { onboardingApi, type ResumeVersion } from "@/features/candidate-onboarding/api";
import { SavedResumePicker } from "@/features/candidate-onboarding/components/saved-resume-picker";

// ─── Types ────────────────────────────────────────────────────────────────────

interface FormState {
  fullName: string;
  email: string;
  phone: string;
  currentRole: string;
  currentCompany: string;
  yearsOfExperience: string;
  expectedSalary: string;
  linkedinUrl: string;
}

interface FormErrors {
  fullName?: string;
  email?: string;
  phone?: string;
  yearsOfExperience?: string;
  expectedSalary?: string;
  resume?: string;
}

type Step = 1 | 2 | 3;

const STEPS: { label: string; step: Step }[] = [
  { label: "Your Info", step: 1 },
  { label: "Resume", step: 2 },
  { label: "Review & Submit", step: 3 },
];

// ─── Component ────────────────────────────────────────────────────────────────

export default function ApplyPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const { user } = useAuth();

  // Fetch live job detail
  const { data: job, isLoading: jobLoading } = usePublicJob(id);
  const jobTitle = job?.title || "Open Position";

  // Mutation hook
  const applyMutation = useApplyToJob();

  const [currentStep, setCurrentStep] = useState<Step>(1);
  const [form, setForm] = useState<FormState>({
    fullName: "",
    email: "",
    phone: "",
    currentRole: "",
    currentCompany: "",
    yearsOfExperience: "",
    expectedSalary: "",
    linkedinUrl: "",
  });
  const [errors, setErrors] = useState<FormErrors>({});
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [savedResume, setSavedResume] = useState<ResumeVersion | null>(null);
  const profileApplication = useMutation({ mutationFn: (details: Parameters<typeof onboardingApi.apply>[1]) => onboardingApi.apply(id, details) });
  const [submissionError, setSubmissionError] = useState<string | null>(null);

  // Prefill authenticated candidate details (P4-005)
  useEffect(() => {
    if (user) {
      queueMicrotask(() => {
        setForm((prev) => ({
          ...prev,
          fullName: prev.fullName || user.name || "",
          email: prev.email || user.email || "",
        }));
      });
    }
  }, [user]);

  const update = (field: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [field]: e.target.value }));

  // ─── Validation ─────────────────────────────────────────────────────────────

  const validateStep1 = (): boolean => {
    const next: FormErrors = {};
    if (!form.fullName.trim()) next.fullName = "Full name is required";
    if (!form.email.trim()) next.email = "Email is required";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) {
      next.email = "Enter a valid email address";
    }
    if (!form.phone.trim()) next.phone = "Phone number is required";
    if (!form.yearsOfExperience.trim()) next.yearsOfExperience = "Years of experience is required";
    if (!form.expectedSalary.trim()) next.expectedSalary = "Expected salary (LPA) is required";

    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const validateStep2 = (): boolean => {
    if (!resumeFile && !savedResume) {
      setErrors({ resume: "Please upload your resume (PDF or DOCX)" });
      return false;
    }
    setErrors({});
    return true;
  };

  // ─── Step Navigation ─────────────────────────────────────────────────────────

  const goNext = () => {
    setSubmissionError(null);
    if (currentStep === 1 && validateStep1()) setCurrentStep(2);
    else if (currentStep === 2 && validateStep2()) setCurrentStep(3);
  };

  const goBack = () => {
    setSubmissionError(null);
    if (currentStep === 2) setCurrentStep(1);
    else if (currentStep === 3) setCurrentStep(2);
  };

  // ─── Submit Handler (P4-007) ────────────────────────────────────────────────

  const handleSubmit = async () => {
    if (!resumeFile && !savedResume) {
      setCurrentStep(2);
      setErrors({ resume: "Please upload your resume before submitting" });
      return;
    }

    setSubmissionError(null);

    try {
      const res = savedResume ? await profileApplication.mutateAsync({
        resume_version_id: savedResume.id, phone: form.phone.trim(),
        years_experience: parseInt(form.yearsOfExperience, 10) || 0,
        current_role: form.currentRole.trim() || undefined, current_company: form.currentCompany.trim() || undefined,
        expected_salary_min: form.expectedSalary ? parseFloat(form.expectedSalary) : undefined,
        expected_salary_max: form.expectedSalary ? parseFloat(form.expectedSalary) : undefined,
        linkedin_url: form.linkedinUrl.trim() || undefined,
      }) : await applyMutation.mutateAsync({
        jobId: id,
        name: form.fullName.trim(),
        email: form.email.trim().toLowerCase(),
        phone: form.phone.trim(),
        yearsExperience: parseInt(form.yearsOfExperience, 10) || 0,
        resumeFile: resumeFile!,
        currentRole: form.currentRole.trim() || undefined,
        currentCompany: form.currentCompany.trim() || undefined,
        expectedSalaryMin: form.expectedSalary ? parseFloat(form.expectedSalary) : undefined,
        expectedSalaryMax: form.expectedSalary ? parseFloat(form.expectedSalary) : undefined,
        linkedinUrl: form.linkedinUrl.trim() || undefined,
      });

      router.push(
        `/jobs/${id}/apply/success?app_id=${res.id}&title=${encodeURIComponent(jobTitle)}`
      );
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        setSubmissionError(
          "You have already applied for this position with this email address. Track your progress in the Candidate Portal."
        );
      } else if (err instanceof Error) {
        setSubmissionError(err.message || "Failed to submit application. Please try again.");
      } else {
        setSubmissionError("An unexpected error occurred while submitting. Please try again.");
      }
    }
  };

  return (
    <div className="mx-auto max-w-2xl px-4 sm:px-6 lg:px-8 py-10">
      {/* Back Link */}
      <Link
        href={`/jobs/${id}`}
        className="inline-flex items-center gap-1.5 text-sm text-text-muted hover:text-text-primary transition-colors mb-6"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to position details
      </Link>

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-text-primary">
          Apply for{" "}
          <span className="text-brand">{jobLoading ? "..." : jobTitle}</span>
        </h1>
        <p className="mt-1 text-sm text-text-muted">
          Complete the form below. Intra AI&apos;s adaptive intelligence engine will evaluate your qualifications.
        </p>
      </div>

      {/* Progress Indicator */}
      <div className="mb-8">
        <div className="flex items-center gap-0">
          {STEPS.map((s, i) => (
            <div key={s.step} className="flex items-center flex-1 last:flex-none">
              {/* Step circle */}
              <div className="flex flex-col items-center gap-1">
                <div
                  className={cn(
                    "flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold transition-colors duration-200",
                    currentStep > s.step
                      ? "bg-brand text-white"
                      : currentStep === s.step
                      ? "bg-brand text-white ring-4 ring-brand/20"
                      : "bg-surface border border-border text-text-muted"
                  )}
                >
                  {currentStep > s.step ? <Check className="h-4 w-4" /> : s.step}
                </div>
                <span
                  className={cn(
                    "text-xs font-medium whitespace-nowrap",
                    currentStep === s.step ? "text-brand" : "text-text-muted"
                  )}
                >
                  {s.label}
                </span>
              </div>
              {/* Connector line */}
              {i < STEPS.length - 1 && (
                <div
                  className={cn(
                    "flex-1 h-px mx-3 mb-5 transition-colors duration-200",
                    currentStep > s.step ? "bg-brand" : "bg-border"
                  )}
                />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Error Alert */}
      {submissionError && (
        <div className="mb-6 rounded-lg border border-danger/30 bg-danger/10 p-4 text-danger flex items-start gap-3">
          <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
          <div className="flex-1 text-sm">
            <p className="font-semibold">Application Submission Notice</p>
            <p className="mt-0.5 text-xs text-danger/90 leading-relaxed">{submissionError}</p>
            {submissionError.includes("Candidate Portal") && (
              <div className="mt-3">
                <Button asChild size="sm" variant="secondary">
                  <Link href="/portal">Open Candidate Portal</Link>
                </Button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Step 1 — Personal & Professional Info */}
      {currentStep === 1 && (
        <Card>
          <CardContent className="p-6 flex flex-col gap-5">
            <div>
              <h2 className="text-base font-semibold text-text-primary">Personal Details</h2>
              <p className="text-xs text-text-muted mt-0.5">
                We will use this information to create your candidate record and contact you
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="sm:col-span-2">
                <label className="mb-1.5 block text-sm font-medium text-text-primary">
                  Full Name <span className="text-error">*</span>
                </label>
                <Input
                  placeholder="e.g. Jane Doe"
                  value={form.fullName}
                  onChange={update("fullName")}
                />
                {errors.fullName && (
                  <p className="mt-1 text-xs text-error">{errors.fullName}</p>
                )}
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-primary">
                  Email Address <span className="text-error">*</span>
                </label>
                <Input
                  type="email"
                  placeholder="jane@example.com"
                  value={form.email}
                  onChange={update("email")}
                />
                {errors.email && <p className="mt-1 text-xs text-error">{errors.email}</p>}
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-primary">
                  Phone Number <span className="text-error">*</span>
                </label>
                <Input
                  type="tel"
                  placeholder="+91 98765 43210"
                  value={form.phone}
                  onChange={update("phone")}
                />
                {errors.phone && <p className="mt-1 text-xs text-error">{errors.phone}</p>}
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-primary">
                  Current Role <span className="text-xs text-text-muted">(Optional)</span>
                </label>
                <Input
                  placeholder="e.g. Software Engineer"
                  value={form.currentRole}
                  onChange={update("currentRole")}
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-primary">
                  Current Company <span className="text-xs text-text-muted">(Optional)</span>
                </label>
                <Input
                  placeholder="e.g. Acme Inc."
                  value={form.currentCompany}
                  onChange={update("currentCompany")}
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-primary">
                  Years of Experience <span className="text-error">*</span>
                </label>
                <Input
                  type="number"
                  min="0"
                  placeholder="e.g. 5"
                  value={form.yearsOfExperience}
                  onChange={update("yearsOfExperience")}
                />
                {errors.yearsOfExperience && (
                  <p className="mt-1 text-xs text-error">{errors.yearsOfExperience}</p>
                )}
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-primary">
                  Expected Salary (LPA) <span className="text-error">*</span>
                </label>
                <Input
                  type="number"
                  min="0"
                  placeholder="e.g. 24"
                  value={form.expectedSalary}
                  onChange={update("expectedSalary")}
                />
                {errors.expectedSalary && (
                  <p className="mt-1 text-xs text-error">{errors.expectedSalary}</p>
                )}
              </div>

              <div className="sm:col-span-2">
                <label className="mb-1.5 block text-sm font-medium text-text-primary">
                  LinkedIn Profile URL <span className="text-xs text-text-muted">(Optional)</span>
                </label>
                <Input
                  type="url"
                  placeholder="https://linkedin.com/in/janedoe"
                  value={form.linkedinUrl}
                  onChange={update("linkedinUrl")}
                />
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <Button type="button" onClick={goNext}>
                Continue to Resume
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 2 — Resume Upload (P4-006) */}
      {currentStep === 2 && (
        <Card>
          <CardContent className="p-6 flex flex-col gap-5">
            <div>
              <h2 className="text-base font-semibold text-text-primary">Upload Resume / CV</h2>
              <p className="text-xs text-text-muted mt-0.5">
                Upload your resume in PDF or DOCX format for automated competency parsing
              </p>
            </div>

            <SavedResumePicker selected={Boolean(savedResume)} onSelect={setSavedResume} />
            <FileUpload
              label="Resume Document Dropzone"
              description="Drag & drop your PDF or DOCX resume here, or browse files"
              uploadingLabel="Submitting application..."
              uploadingDescription="Uploading your document to candidate cloud storage"
              accept={[".pdf", ".docx"]}
              maxSizeMb={10}
              currentFile={resumeFile}
              onFileSelect={(file) => {
                setResumeFile(file);
                setSavedResume(null);
                setErrors((prev) => ({ ...prev, resume: undefined }));
              }}
              onClearFile={() => setResumeFile(null)}
              error={errors.resume}
            />

            <div className="flex justify-between pt-2">
              <Button type="button" variant="secondary" onClick={goBack}>
                Back
              </Button>
              <Button type="button" onClick={goNext}>
                Continue to Review
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 3 — Review & Submit (P4-007) */}
      {currentStep === 3 && (
        <Card>
          <CardContent className="p-6 flex flex-col gap-6">
            <div>
              <h2 className="text-base font-semibold text-text-primary">Review & Confirm</h2>
              <p className="text-xs text-text-muted mt-0.5">
                Verify your details before submitting your application
              </p>
            </div>

            {/* Review Sections */}
            <div className="flex flex-col gap-4 rounded-lg border border-border/80 bg-surface/50 p-4">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div className="flex items-center gap-2">
                  <User className="h-4 w-4 text-brand" />
                  <span className="text-sm font-semibold text-text-primary">Contact & Identity</span>
                </div>
                <button
                  type="button"
                  onClick={() => setCurrentStep(1)}
                  className="text-xs text-brand hover:underline font-medium cursor-pointer"
                >
                  Edit
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div>
                  <span className="text-text-muted block">Full Name:</span>
                  <span className="font-medium text-text-primary">{form.fullName}</span>
                </div>
                <div>
                  <span className="text-text-muted block">Email:</span>
                  <span className="font-medium text-text-primary">{form.email}</span>
                </div>
                <div>
                  <span className="text-text-muted block">Phone:</span>
                  <span className="font-medium text-text-primary">{form.phone}</span>
                </div>
                <div>
                  <span className="text-text-muted block">Experience:</span>
                  <span className="font-medium text-text-primary">{form.yearsOfExperience} years</span>
                </div>
                {form.currentRole && (
                  <div>
                    <span className="text-text-muted block">Current Role:</span>
                    <span className="font-medium text-text-primary">
                      {form.currentRole} {form.currentCompany && `at ${form.currentCompany}`}
                    </span>
                  </div>
                )}
                <div>
                  <span className="text-text-muted block">Expected Salary:</span>
                  <span className="font-medium text-text-primary">₹{form.expectedSalary} LPA</span>
                </div>
              </div>
            </div>

            {/* Resume file summary */}
            <div className="flex flex-col gap-3 rounded-lg border border-border/80 bg-surface/50 p-4">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-brand" />
                  <span className="text-sm font-semibold text-text-primary">Attached Resume</span>
                </div>
                <button
                  type="button"
                  onClick={() => setCurrentStep(2)}
                  className="text-xs text-brand hover:underline font-medium cursor-pointer"
                >
                  Change
                </button>
              </div>

              {savedResume ? <p className="text-xs font-medium">Saved profile: {savedResume.filename} (v{savedResume.version})</p> : resumeFile ? (
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-text-primary">{resumeFile.name}</span>
                  <Badge variant="outline" className="text-[11px]">
                    {(resumeFile.size / (1024 * 1024)).toFixed(1)} MB
                  </Badge>
                </div>
              ) : (
                <p className="text-xs text-error">No resume attached.</p>
              )}
            </div>

            <p className="text-xs text-text-muted leading-relaxed">
              By submitting this application, you agree to allow Intra AI to process your resume,
              calculate eligibility scores, and invite you to multi-agent voice interviews.
            </p>

            <div className="flex justify-between pt-2">
              <Button
                type="button"
                variant="secondary"
                onClick={goBack}
                disabled={applyMutation.isPending || profileApplication.isPending}
              >
                Back
              </Button>
              <Button
                type="button"
                onClick={handleSubmit}
                disabled={applyMutation.isPending || profileApplication.isPending}
              >
                {applyMutation.isPending || profileApplication.isPending ? "Submitting Application..." : "Confirm & Submit Application"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
