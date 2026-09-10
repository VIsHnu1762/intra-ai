BEGIN;

ALTER TABLE public.gd_events ADD COLUMN IF NOT EXISTS projection_next_attempt_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE public.roleplay_events ADD COLUMN IF NOT EXISTS projection_next_attempt_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS gd_projection_retry_idx ON public.gd_events(projection_next_attempt_at,session_id)
  WHERE projection_status IN ('pending','failed');
CREATE INDEX IF NOT EXISTS roleplay_projection_retry_idx ON public.roleplay_events(projection_next_attempt_at,session_id)
  WHERE projection_status IN ('pending','failed');

CREATE TABLE IF NOT EXISTS public.feature_worker_health (
  worker_id uuid PRIMARY KEY,
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  status text NOT NULL CHECK (status IN ('working','ok','degraded')),
  detail jsonb NOT NULL DEFAULT '{}'::jsonb
);
ALTER TABLE public.feature_worker_health ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.feature_worker_health FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.feature_worker_health TO service_role;
DROP POLICY IF EXISTS feature_worker_server_only ON public.feature_worker_health;
CREATE POLICY feature_worker_server_only ON public.feature_worker_health TO service_role USING (true) WITH CHECK (true);

CREATE OR REPLACE FUNCTION public.pending_gd_analysis_sessions(p_limit integer DEFAULT 8)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
  SELECT COALESCE(jsonb_agg(work.session_id),'[]'::jsonb) FROM (
    SELECT session_id FROM public.gd_events WHERE analysis->>'status'='pending'
    GROUP BY session_id ORDER BY min(created_at) LIMIT greatest(1,least(p_limit,50))
  ) work;
$$;

CREATE OR REPLACE FUNCTION public.pending_gd_projection_sessions(p_limit integer DEFAULT 8)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
  SELECT COALESCE(jsonb_agg(work.session_id),'[]'::jsonb) FROM (
    SELECT session_id FROM public.gd_events
    WHERE projection_status IN ('pending','failed') AND projection_next_attempt_at<=now()
    GROUP BY session_id ORDER BY min(created_at) LIMIT greatest(1,least(p_limit,50))
  ) work;
$$;

CREATE OR REPLACE FUNCTION public.pending_roleplay_projection_sessions(p_limit integer DEFAULT 8)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
  SELECT COALESCE(jsonb_agg(work.session_id),'[]'::jsonb) FROM (
    SELECT session_id FROM public.roleplay_events
    WHERE projection_status IN ('pending','failed') AND projection_next_attempt_at<=now()
    GROUP BY session_id ORDER BY min(created_at) LIMIT greatest(1,least(p_limit,50))
  ) work;
$$;

REVOKE ALL ON FUNCTION public.pending_gd_analysis_sessions(integer),public.pending_gd_projection_sessions(integer),
  public.pending_roleplay_projection_sessions(integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.pending_gd_analysis_sessions(integer),public.pending_gd_projection_sessions(integer),
  public.pending_roleplay_projection_sessions(integer) TO service_role;

NOTIFY pgrst,'reload schema';
COMMIT;
