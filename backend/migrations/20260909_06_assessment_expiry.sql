-- Domain-specific timeout transitions, scheduled by the existing recovery worker.
BEGIN;
CREATE INDEX IF NOT EXISTS roleplay_active_expiry_idx ON public.roleplay_sessions(updated_at) WHERE status='active';

CREATE OR REPLACE FUNCTION public.expire_roleplay_sessions(p_limit integer DEFAULT 32)
RETURNS integer LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE s public.roleplay_sessions%ROWTYPE; changed integer := 0; phase text;
BEGIN
 FOR s IN SELECT * FROM public.roleplay_sessions
  WHERE status='active' AND (state->>'started_at')::timestamptz +
    make_interval(secs=>(scenario_snapshot->'definition'->>'duration_seconds')::integer)<=now()
  ORDER BY updated_at LIMIT greatest(1,least(p_limit,100)) FOR UPDATE SKIP LOCKED
 LOOP
  phase := s.scenario_snapshot->'definition'->'phases'->((s.state->>'phase_index')::integer)->>'id';
  INSERT INTO public.roleplay_events(id,session_id,candidate_id,revision,kind,request_id,request_hash,
    source_text,response,action,analysis,evidence,projection_status)
   VALUES(gen_random_uuid()::text,s.id,s.candidate_id,s.revision+1,'finish','system:timeout:'||s.id,
    'system:time_limit','','The simulation has ended because its time limit was reached.',
    jsonb_build_object('action','END_SCENARIO','rationale','time_limit','phase_id',phase),
    '{"status":"not_applicable"}','[]','skipped');
  UPDATE public.roleplay_sessions SET state=state||jsonb_build_object('status','completed',
    'ended_at',now(),'completion_reason','time_limit'),revision=revision+1,updated_at=now() WHERE id=s.id;
  changed := changed+1;
 END LOOP;
 RETURN changed;
END $$;

CREATE OR REPLACE FUNCTION public.expire_gd_sessions(p_limit integer DEFAULT 32)
RETURNS integer LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE s public.gd_sessions%ROWTYPE; changed integer := 0;
BEGIN
 FOR s IN SELECT * FROM public.gd_sessions WHERE status='active'
  AND started_at+make_interval(secs=>(configuration->>'duration_seconds')::integer)<=now()
  ORDER BY started_at LIMIT greatest(1,least(p_limit,100)) FOR UPDATE SKIP LOCKED
 LOOP
  INSERT INTO public.gd_events(id,session_id,sequence,kind,request_id,request_hash,response,action)
   VALUES(gen_random_uuid()::text,s.id,s.revision+1,'expired','system:timeout:'||s.id,'system:time_limit',
    'The discussion has ended because its time limit was reached.',
    '{"action":"END_DISCUSSION","rationale":"time_limit"}');
  UPDATE public.gd_sessions SET status='completed',ended_at=now(),revision=revision+1,
    moderator_state=moderator_state||'{"completion_reason":"time_limit"}'::jsonb,updated_at=now() WHERE id=s.id;
  changed := changed+1;
 END LOOP;
 RETURN changed;
END $$;

REVOKE ALL ON FUNCTION public.expire_roleplay_sessions(integer),public.expire_gd_sessions(integer)
 FROM PUBLIC,anon,authenticated,authenticator;
GRANT EXECUTE ON FUNCTION public.expire_roleplay_sessions(integer),public.expire_gd_sessions(integer) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
