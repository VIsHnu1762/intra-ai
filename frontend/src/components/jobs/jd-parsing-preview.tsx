/**
Intra AI — JD Parsing Review & Edit Card (P3-03).

Provides an interactive preview card allowing recruiters to inspect, edit,
and confirm parsed opportunity requirements extracted via GPT-4o before populating the form.
 */

import React, { useState } from "react";
import { Sparkles, Check, X, Plus, Edit3, Trash2, ArrowRight, ShieldCheck, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { JdParseResponse } from "@/types/api";

export interface JdParsingPreviewProps {
  initialData: JdParseResponse;
  onConfirm: (data: JdParseResponse) => void;
  onDiscard: () => void;
}

export function JdParsingPreview({
  initialData,
  onConfirm,
  onDiscard,
}: JdParsingPreviewProps) {
  const [formData, setFormData] = useState<JdParseResponse>({
    ...initialData,
    required_skills: [...(initialData.required_skills || [])],
    suggested_competencies: [...(initialData.suggested_competencies || [])],
  });

  const [newSkill, setNewSkill] = useState("");
  const [newCompetency, setNewCompetency] = useState("");

  const handleFieldChange = (field: keyof JdParseResponse, value: any) => {
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleAddSkill = () => {
    const trimmed = newSkill.trim();
    if (trimmed && !formData.required_skills.includes(trimmed)) {
      setFormData((prev) => ({
        ...prev,
        required_skills: [...prev.required_skills, trimmed],
      }));
      setNewSkill("");
    }
  };

  const handleRemoveSkill = (skillToRemove: string) => {
    setFormData((prev) => ({
      ...prev,
      required_skills: prev.required_skills.filter((s) => s !== skillToRemove),
    }));
  };

  const handleAddCompetency = () => {
    const trimmed = newCompetency.trim().toLowerCase().replace(/\s+/g, "_");
    if (trimmed && !formData.suggested_competencies.includes(trimmed)) {
      setFormData((prev) => ({
        ...prev,
        suggested_competencies: [...prev.suggested_competencies, trimmed],
      }));
      setNewCompetency("");
    }
  };

  const handleRemoveCompetency = (compToRemove: string) => {
    setFormData((prev) => ({
      ...prev,
      suggested_competencies: prev.suggested_competencies.filter((c) => c !== compToRemove),
    }));
  };

  const handleSave = () => {
    onConfirm(formData);
  };

  return (
    <Card className="border-brand/30 bg-card shadow-md animate-in fade-in-50 duration-300">
      <CardHeader className="border-b border-border pb-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-brand/10 text-brand flex items-center justify-center">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <CardTitle className="text-base font-semibold text-text-primary flex items-center gap-2">
                Parsed Job Description
                <Badge variant="outline" className="bg-brand/10 text-brand border-brand/20 text-[11px] font-medium">
                  Auto-extracted
                </Badge>
              </CardTitle>
              <CardDescription className="text-xs text-text-muted">
                We configured the role and interview defaults from this document. Review the summary, make any corrections, then continue.
              </CardDescription>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={onDiscard}
              className="text-text-muted hover:text-text-primary text-xs h-8"
            >
              Discard & Re-upload
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={handleSave}
              className="bg-brand hover:bg-brand-hover text-white text-xs h-8 gap-1.5 shadow-sm"
            >
              <Check className="h-3.5 w-3.5" />
              Review & Continue
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-5 space-y-5">
        {/* Basic Information */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-text-secondary">Role Title</label>
            <Input
              value={formData.title}
              onChange={(e) => handleFieldChange("title", e.target.value)}
              placeholder="e.g. Senior Backend Engineer"
              className="text-sm font-medium"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-text-secondary">Department</label>
            <Input
              value={formData.department}
              onChange={(e) => handleFieldChange("department", e.target.value)}
              placeholder="e.g. Engineering"
              className="text-sm"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-text-secondary">Location</label>
            <Input
              value={formData.location}
              onChange={(e) => handleFieldChange("location", e.target.value)}
              placeholder="e.g. Remote or San Francisco"
              className="text-sm"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-text-secondary">Work Model</label>
            <select
              value={formData.job_type}
              onChange={(e) => handleFieldChange("job_type", e.target.value)}
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
          <label className="text-xs font-medium text-text-secondary">Role Summary & Description</label>
          <Textarea
            rows={3}
            value={formData.description}
            onChange={(e) => handleFieldChange("description", e.target.value)}
            placeholder="Extracted role description and mission..."
            className="text-xs leading-relaxed"
          />
        </div>

        {/* Required Skills Tag Editor */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-xs font-medium text-text-secondary">
              Required Skills ({formData.required_skills.length})
            </label>
            <span className="text-[11px] text-text-muted">Press Enter or click Add to append</span>
          </div>
          <div className="flex flex-wrap gap-1.5 p-3 rounded-lg border border-border bg-bg/50 min-h-[52px]">
            {formData.required_skills.map((skill) => (
              <span
                key={skill}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-card border border-border text-xs font-medium text-text-primary shadow-xs"
              >
                {skill}
                <button
                  type="button"
                  onClick={() => handleRemoveSkill(skill)}
                  className="text-text-muted hover:text-danger rounded p-0.5"
                  title={`Remove ${skill}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
            <div className="inline-flex items-center gap-1">
              <input
                type="text"
                value={newSkill}
                onChange={(e) => setNewSkill(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
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

        {/* Experience & Education */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-1">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-text-secondary">Min Experience (Years)</label>
            <Input
              type="number"
              min={0}
              max={25}
              value={formData.experience_min ?? 0}
              onChange={(e) => handleFieldChange("experience_min", parseInt(e.target.value) || 0)}
              className="text-sm"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-text-secondary">Max Experience (Years)</label>
            <Input
              type="number"
              min={0}
              max={30}
              value={formData.experience_max ?? 5}
              onChange={(e) => handleFieldChange("experience_max", parseInt(e.target.value) || 0)}
              className="text-sm"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-text-secondary">Education Requirement</label>
            <Input
              value={formData.education || ""}
              onChange={(e) => handleFieldChange("education", e.target.value)}
              placeholder="e.g. Bachelor's in Computer Science"
              className="text-sm"
            />
          </div>
        </div>

        {/* Suggested Focal Competencies */}
        <div className="space-y-2 pt-1 border-t border-border">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <ShieldCheck className="h-4 w-4 text-brand" />
              <label className="text-xs font-semibold text-text-primary">
                Suggested M1 Evaluation Competencies ({formData.suggested_competencies.length})
              </label>
            </div>
            <span className="text-[11px] text-text-muted">These will pre-seed your round competencies</span>
          </div>

          <div className="flex flex-wrap gap-1.5 p-3 rounded-lg border border-border bg-bg/50">
            {formData.suggested_competencies.map((comp) => (
              <span
                key={comp}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-brand/10 border border-brand/20 text-xs font-medium text-brand capitalize"
              >
                {comp.replace(/_/g, " ")}
                <button
                  type="button"
                  onClick={() => handleRemoveCompetency(comp)}
                  className="text-brand/70 hover:text-danger rounded p-0.5"
                  title={`Remove ${comp}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
            <div className="inline-flex items-center gap-1">
              <input
                type="text"
                value={newCompetency}
                onChange={(e) => setNewCompetency(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleAddCompetency();
                  }
                }}
                placeholder="Add competency..."
                className="h-7 text-xs bg-transparent px-2 border-none outline-none focus:ring-0 w-32 text-text-primary placeholder:text-text-muted"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleAddCompetency}
                className="h-6 w-6 p-0 text-text-muted hover:text-brand"
              >
                <Plus className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
