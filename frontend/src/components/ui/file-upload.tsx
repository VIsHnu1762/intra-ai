/**
Intra AI — Reusable Accessible File Upload Dropzone Component.

Supports PDF, DOCX, drag-and-drop, format & size validation, upload progress,
error states, and keyboard accessibility.
 */

import React, { useState, useRef, useCallback } from "react";
import { UploadCloud, FileText, CheckCircle2, AlertCircle, X, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";

export interface FileUploadProps {
  accept?: string[];
  maxSizeMb?: number;
  onFileSelect: (file: File) => void;
  /** Optional explicit action shown after a file is selected. */
  onParse?: () => void;
  parseLabel?: string;
  isParsing?: boolean;
  onClearFile?: () => void;
  isUploading?: boolean;
  uploadProgress?: number;
  error?: string | null;
  onClearError?: () => void;
  label?: string;
  description?: string;
  uploadingLabel?: string;
  uploadingDescription?: string;
  className?: string;
  disabled?: boolean;
  currentFile?: File | null;
}

export function FileUpload({
  accept = [".pdf", ".docx", ".doc", ".txt"],
  maxSizeMb = 10,
  onFileSelect,
  onParse,
  parseLabel = "Parse JD",
  isParsing = false,
  onClearFile,
  isUploading = false,
  uploadProgress = 0,
  error = null,
  onClearError,
  label = "Upload Job Description",
  description = "Drag & drop your PDF or DOCX file here, or browse files",
  uploadingLabel = "Analyzing Document with GPT-4o...",
  uploadingDescription = "Extracting role responsibilities, skills, and competencies",
  className,
  disabled = false,
  currentFile,
}: FileUploadProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [internalFile, setInternalFile] = useState<File | null>(null);
  const selectedFile = currentFile !== undefined ? currentFile : internalFile;
  const [validationError, setValidationError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const activeError = error || validationError;

  const validateAndProcessFile = useCallback(
    (file: File) => {
      setValidationError(null);
      if (onClearError) onClearError();

      // Check size
      const maxSizeBytes = maxSizeMb * 1024 * 1024;
      if (file.size > maxSizeBytes) {
        setValidationError(
          `File size exceeds ${maxSizeMb}MB (${(file.size / (1024 * 1024)).toFixed(1)}MB). Please choose a smaller file.`
        );
        return;
      }

      // Check extension / type
      const ext = "." + file.name.split(".").pop()?.toLowerCase();
      const isAcceptedExt = accept.some((a) => a.toLowerCase() === ext);
      const isAcceptedMime =
        file.type.includes("pdf") ||
        file.type.includes("word") ||
        file.type.includes("officedocument") ||
        file.type.startsWith("text/");

      if (!isAcceptedExt && !isAcceptedMime) {
        setValidationError(
          `Invalid file format. Accepted formats: ${accept.join(", ")}`
        );
        return;
      }

      setInternalFile(file);
      onFileSelect(file);
    },
    [accept, maxSizeMb, onFileSelect, onClearError]
  );

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (disabled || isUploading) return;
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    if (disabled || isUploading) return;

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndProcessFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      validateAndProcessFile(e.target.files[0]);
    }
  };

  const triggerBrowse = () => {
    if (disabled || isUploading) return;
    fileInputRef.current?.click();
  };

  const clearSelection = (e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setInternalFile(null);
    setValidationError(null);
    if (onClearFile) onClearFile();
    if (onClearError) onClearError();
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className={cn("w-full space-y-3", className)}>
      <div
        role="button"
        tabIndex={disabled || isUploading ? -1 : 0}
        aria-label={label}
        onClick={triggerBrowse}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && !disabled && !isUploading) {
            e.preventDefault();
            triggerBrowse();
          }
        }}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          "relative flex flex-col items-center justify-center p-6 border-2 border-dashed rounded-xl cursor-pointer transition-all duration-200 outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
          isDragOver
            ? "border-brand bg-brand/5 scale-[1.005] shadow-sm"
            : "border-border hover:border-brand/40 hover:bg-bg/50 bg-card",
          (disabled || isUploading) && "opacity-75 cursor-not-allowed",
          activeError && "border-danger/60 bg-danger/5"
        )}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={accept.join(",")}
          onChange={handleFileInputChange}
          className="hidden"
          disabled={disabled || isUploading}
        />

        {/* Uploading State */}
        {isUploading ? (
          <div className="w-full max-w-sm flex flex-col items-center text-center py-3 space-y-3">
            <div className="h-10 w-10 rounded-full bg-brand/10 text-brand flex items-center justify-center animate-pulse">
              <RefreshCw className="h-5 w-5 animate-spin" />
            </div>
            <div>
              <p className="text-sm font-medium text-text-primary">
                {uploadingLabel}
              </p>
              <p className="text-xs text-text-muted mt-0.5">
                {uploadingDescription}
              </p>
            </div>
            {uploadProgress > 0 && (
              <div className="w-full space-y-1">
                <Progress value={uploadProgress} className="h-1.5" />
                <p className="text-[11px] text-text-muted text-right">
                  {uploadProgress}%
                </p>
              </div>
            )}
          </div>
        ) : selectedFile ? (
          /* File Selected State */
          <div className="w-full flex items-center justify-between p-2 rounded-lg bg-bg border border-border">
            <div className="flex items-center gap-3 overflow-hidden">
              <div className="h-10 w-10 shrink-0 rounded-lg bg-brand/10 text-brand flex items-center justify-center">
                <FileText className="h-5 w-5" />
              </div>
            <div className="overflow-hidden text-left">
                <p className="text-sm font-medium text-text-primary truncate">
                  {selectedFile.name}
                </p>
                <p className="text-xs text-text-muted">
                  {formatFileSize(selectedFile.size)} • Ready to analyze or change
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {onParse && (
                <Button
                  type="button"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    onParse();
                  }}
                  disabled={isParsing}
                  className="h-8 gap-1.5 text-xs bg-brand hover:bg-brand-hover text-white"
                >
                  {isParsing ? (
                    <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <CheckCircle2 className="h-3.5 w-3.5" />
                  )}
                  {isParsing ? "Analyzing..." : parseLabel}
                </Button>
              )}
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={clearSelection}
                className="h-8 w-8 p-0 text-text-muted hover:text-text-primary"
                title="Remove file"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
        ) : (
          /* Default Empty Dropzone */
          <div className="flex flex-col items-center text-center space-y-2 py-2">
            <div className="h-12 w-12 rounded-full bg-surface text-brand flex items-center justify-center border border-border/80 shadow-xs">
              <UploadCloud className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-medium text-text-primary">{label}</p>
              <p className="text-xs text-text-muted mt-0.5">{description}</p>
            </div>
            <div className="flex items-center gap-2 pt-1">
              <span className="inline-flex items-center text-[11px] font-medium px-2 py-0.5 rounded-full bg-surface border border-border text-text-muted">
                PDF or DOCX
              </span>
              <span className="inline-flex items-center text-[11px] font-medium px-2 py-0.5 rounded-full bg-surface border border-border text-text-muted">
                Max {maxSizeMb}MB
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Error Alert */}
      {activeError && (
        <div className="flex items-start gap-2.5 p-3 rounded-lg bg-danger/10 border border-danger/30 text-danger text-xs animate-in fade-in duration-200">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-medium">{activeError}</p>
          </div>
          <button
            type="button"
            onClick={clearSelection}
            className="text-danger/80 hover:text-danger p-0.5"
            title="Dismiss"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </div>
  );
}
