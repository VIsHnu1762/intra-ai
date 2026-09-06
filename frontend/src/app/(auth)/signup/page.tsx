"use client";

import { useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Eye, EyeOff, Briefcase, User, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useAuth } from "@/context/AuthContext";
import { formatApiErrorMessage } from "@/lib/api/error-handler";

type Role = "recruiter" | "candidate";

interface FormState {
  fullName: string;
  email: string;
  password: string;
  confirmPassword: string;
}

interface FormErrors {
  fullName?: string;
  email?: string;
  password?: string;
  confirmPassword?: string;
}

function SignupForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { signup } = useAuth();

  const [role, setRole] = useState<Role>("candidate");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>({
    fullName: "",
    email: "",
    password: "",
    confirmPassword: "",
  });
  const [errors, setErrors] = useState<FormErrors>({});

  const update = (field: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [field]: e.target.value }));

  const validate = (): boolean => {
    const next: FormErrors = {};
    if (!form.fullName.trim()) next.fullName = "Full name is required";
    if (!form.email) next.email = "Email is required";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) next.email = "Enter a valid email";
    if (!form.password) next.password = "Password is required";
    else if (form.password.length < 8) next.password = "Password must be at least 8 characters";
    if (!form.confirmPassword) next.confirmPassword = "Please confirm your password";
    else if (form.password !== form.confirmPassword) next.confirmPassword = "Passwords do not match";
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setServerError(null);
    if (!validate()) return;
    setLoading(true);

    try {
      const res = await signup({
        email: form.email,
        password: form.password,
        name: form.fullName.trim(),
        role,
      });

      const userRole = res?.user?.role || role;
      const isHr = userRole === "recruiter" || userRole === "admin";
      const fromParam = searchParams.get("from") || searchParams.get("redirect");

      let destination: string;
      if (isHr) {
        // HR / Recruiter must ONLY navigate to /admin routes, never candidate portal
        if (fromParam && fromParam.startsWith("/admin")) {
          destination = fromParam;
        } else {
          destination = "/admin/dashboard";
        }
      } else {
        // Candidate must ONLY navigate to candidate-allowed routes, never admin console
        if (
          fromParam &&
          fromParam.startsWith("/") &&
          !fromParam.startsWith("/admin") &&
          !fromParam.startsWith("/login") &&
          !fromParam.startsWith("/signup")
        ) {
          destination = fromParam;
        } else {
          destination = "/portal";
        }
      }

      window.location.href = destination;
    } catch (err: unknown) {
      setServerError(formatApiErrorMessage(err, "Failed to create account. Please try again."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardContent className="p-8">
        {/* Heading */}
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-bold text-text-primary">Create your account</h1>
          <p className="mt-1.5 text-sm text-text-muted">
            Join Intra AI and streamline your hiring
          </p>
        </div>

        {serverError && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-error/30 bg-error/10 p-3 text-xs text-error">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{serverError}</span>
          </div>
        )}

        {/* Role toggle */}
        <div className="mb-5 grid grid-cols-2 gap-2 rounded-lg border border-border p-1 bg-bg">
          <button
            type="button"
            onClick={() => setRole("candidate")}
            className={cn(
              "flex items-center justify-center gap-2 rounded-md py-2.5 text-sm font-medium transition-colors duration-150",
              role === "candidate"
                ? "bg-surface text-brand shadow-sm border border-border"
                : "text-text-muted hover:text-text-primary"
            )}
          >
            <User className="h-4 w-4" />
            I&apos;m a candidate
          </button>
          <button
            type="button"
            onClick={() => setRole("recruiter")}
            className={cn(
              "flex items-center justify-center gap-2 rounded-md py-2.5 text-sm font-medium transition-colors duration-150",
              role === "recruiter"
                ? "bg-surface text-brand shadow-sm border border-border"
                : "text-text-muted hover:text-text-primary"
            )}
          >
            <Briefcase className="h-4 w-4" />
            I&apos;m hiring
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-text-primary">
              Full name
            </label>
            <Input
              type="text"
              placeholder="Dhruv Sharma"
              value={form.fullName}
              onChange={update("fullName")}
              error={errors.fullName}
              autoComplete="name"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-text-primary">
              Email address
            </label>
            <Input
              type="email"
              placeholder="you@company.com"
              value={form.email}
              onChange={update("email")}
              error={errors.email}
              autoComplete="email"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-text-primary">
              Password
            </label>
            <div className="relative">
              <Input
                type={showPassword ? "text" : "password"}
                placeholder="Min. 8 characters"
                value={form.password}
                onChange={update("password")}
                error={errors.password}
                autoComplete="new-password"
                className="pr-10"
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="absolute right-3 top-3 text-text-muted hover:text-text-primary transition-colors"
                tabIndex={-1}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-text-primary">
              Confirm password
            </label>
            <div className="relative">
              <Input
                type={showConfirm ? "text" : "password"}
                placeholder="Re-enter your password"
                value={form.confirmPassword}
                onChange={update("confirmPassword")}
                error={errors.confirmPassword}
                autoComplete="new-password"
                className="pr-10"
              />
              <button
                type="button"
                onClick={() => setShowConfirm((v) => !v)}
                className="absolute right-3 top-3 text-text-muted hover:text-text-primary transition-colors"
                tabIndex={-1}
              >
                {showConfirm ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <Button type="submit" size="lg" className="w-full mt-1" loading={loading}>
            Create Account
          </Button>
        </form>

        {/* Divider */}
        <div className="my-5 flex items-center gap-3">
          <div className="h-px flex-1 bg-border" />
          <span className="text-xs text-text-muted">or continue with</span>
          <div className="h-px flex-1 bg-border" />
        </div>

        {/* Google */}
        <Button
          type="button"
          variant="secondary"
          size="lg"
          className="w-full"
          onClick={() => {}}
        >
          <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" aria-hidden>
            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
          </svg>
          Sign up with Google
        </Button>

        {/* Terms */}
        <p className="mt-4 text-center text-xs text-text-muted">
          By creating an account you agree to our{" "}
          <Link href="#" className="text-brand hover:underline">Terms of Service</Link>
          {" "}and{" "}
          <Link href="#" className="text-brand hover:underline">Privacy Policy</Link>.
        </p>

        {/* Sign in link */}
        <p className="mt-3 text-center text-sm text-text-muted">
          Already have an account?{" "}
          <Link
            href="/login"
            className="font-medium text-brand hover:text-brand-hover transition-colors"
          >
            Sign in
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}

export default function SignupPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-sm text-text-muted">Loading...</div>}>
      <SignupForm />
    </Suspense>
  );
}
