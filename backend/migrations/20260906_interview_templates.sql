-- Reusable interview rounds, with immutable copies on booked interviews.
-- Run with the database administrator role. No existing rows are rewritten.
BEGIN;

CREATE TABLE IF NOT EXISTS public.interview_templates (
    id TEXT PRIMARY KEY,
    created_by TEXT NOT NULL,
    tenant_id TEXT,
    name TEXT NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 160),
    description TEXT NOT NULL DEFAULT '' CHECK (length(description) <= 2000),
    rounds JSONB NOT NULL CHECK (jsonb_typeof(rounds) = 'array' AND jsonb_array_length(rounds) BETWEEN 1 AND 24),
    duration_minutes INTEGER NOT NULL CHECK (duration_minutes BETWEEN 1 AND 60),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS interview_templates_workspace_idx
    ON public.interview_templates (tenant_id, created_by, created_at DESC);

-- The application uses its own JWT issuer and persisted identity checks.
-- Only the server service-role client may query this table. Anonymous and
-- Supabase-authenticated clients have neither grants nor RLS policies.
ALTER TABLE public.interview_templates ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.interview_templates FROM PUBLIC, anon, authenticated, authenticator;
GRANT ALL ON public.interview_templates TO service_role;

ALTER TABLE public.scheduled_interviews
    ADD COLUMN IF NOT EXISTS template_snapshot JSONB;

COMMENT ON COLUMN public.scheduled_interviews.template_snapshot IS
    'Immutable template id/version/name/rounds/duration copied when scheduled; never refreshed from the source template.';

NOTIFY pgrst, 'reload schema';
COMMIT;
