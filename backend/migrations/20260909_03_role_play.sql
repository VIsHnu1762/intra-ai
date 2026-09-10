BEGIN;
DO $ddl$
DECLARE utype text; ctype text;
BEGIN
 SELECT format_type(atttypid,atttypmod) INTO utype FROM pg_attribute WHERE attrelid='public.users'::regclass AND attname='id';
 SELECT format_type(atttypid,atttypmod) INTO ctype FROM pg_attribute WHERE attrelid='public.candidates'::regclass AND attname='id';
 EXECUTE format('CREATE TABLE IF NOT EXISTS public.roleplay_definitions (
  id text PRIMARY KEY, kind text NOT NULL CHECK(kind IN (''persona'',''scenario'')),
  created_by %s NOT NULL REFERENCES public.users(id) ON DELETE CASCADE, tenant_key text NOT NULL,
  persona_id text REFERENCES public.roleplay_definitions(id), definition jsonb NOT NULL CHECK(jsonb_typeof(definition)=''object''),
  revision integer NOT NULL CHECK(revision>0), request_id text NOT NULL, request_hash text NOT NULL,
  archived_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK((kind=''persona'' AND persona_id IS NULL) OR (kind=''scenario'' AND persona_id IS NOT NULL)))',utype);
 EXECUTE format('CREATE TABLE IF NOT EXISTS public.roleplay_sessions (
  id text PRIMARY KEY, created_by %s NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  candidate_id %s NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE, tenant_key text NOT NULL,
  scenario_id text NOT NULL REFERENCES public.roleplay_definitions(id),
  scenario_snapshot jsonb NOT NULL, persona_snapshot jsonb NOT NULL, candidate_profile jsonb NOT NULL DEFAULT ''{}'',
  state jsonb NOT NULL CHECK(jsonb_typeof(state)=''object''),
  status text GENERATED ALWAYS AS (state->>''status'') STORED,
  revision integer NOT NULL DEFAULT 0 CHECK(revision>=0), request_id text NOT NULL, request_hash text NOT NULL,
  report_status text NOT NULL DEFAULT ''not_started'' CHECK(report_status IN (''not_started'',''failed'',''ready'')),
  report jsonb, report_error text, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK(state->>''status'' IN (''assigned'',''active'',''completed'',''cancelled'')),
  CHECK((state->>''phase_index'')::integer>=0 AND (state->>''phase_index'')::integer<jsonb_array_length(scenario_snapshot->''definition''->''phases'')),
  UNIQUE(created_by,request_id))',utype,ctype);
 EXECUTE format('CREATE TABLE IF NOT EXISTS public.roleplay_events (
  id text PRIMARY KEY, session_id text NOT NULL REFERENCES public.roleplay_sessions(id) ON DELETE CASCADE,
  candidate_id %s NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
  revision integer NOT NULL CHECK(revision>0), kind text NOT NULL CHECK(kind IN (''turn'',''start'',''finish'',''cancel'')),
  request_id text NOT NULL, request_hash text NOT NULL, source_text text NOT NULL CHECK(length(source_text)<=4000),
  response text NOT NULL CHECK(length(response)<=1200), action jsonb NOT NULL, analysis jsonb NOT NULL,
  evidence jsonb NOT NULL DEFAULT ''[]'' CHECK(jsonb_typeof(evidence)=''array'' AND jsonb_array_length(evidence)<=8),
  policy_context jsonb, created_at timestamptz NOT NULL DEFAULT now(),
  projection_status text NOT NULL DEFAULT ''pending'' CHECK(projection_status IN (''pending'',''delivered'',''failed'',''skipped'')),
  projection_attempts integer NOT NULL DEFAULT 0, projection_error text, projection_attempted_at timestamptz,
  UNIQUE(session_id,revision), UNIQUE(session_id,request_id))',ctype);
END $ddl$;
CREATE INDEX IF NOT EXISTS roleplay_definitions_owner_idx ON public.roleplay_definitions(created_by,tenant_key,kind,created_at DESC);
CREATE INDEX IF NOT EXISTS roleplay_sessions_owner_idx ON public.roleplay_sessions(created_by,tenant_key,created_at DESC);
CREATE INDEX IF NOT EXISTS roleplay_sessions_candidate_idx ON public.roleplay_sessions(candidate_id,created_at DESC);
CREATE INDEX IF NOT EXISTS roleplay_events_pending_idx ON public.roleplay_events(projection_status,created_at) WHERE projection_status IN ('pending','failed');
DO $$ DECLARE tab text; BEGIN
 FOREACH tab IN ARRAY ARRAY['roleplay_definitions','roleplay_sessions','roleplay_events'] LOOP
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',tab);
  EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC,anon,authenticated,authenticator',tab);
  EXECUTE format('GRANT ALL ON public.%I TO service_role',tab);
  EXECUTE format('DROP POLICY IF EXISTS feature_server ON public.%I',tab);
  EXECUTE format('CREATE POLICY feature_server ON public.%I TO service_role USING(true) WITH CHECK(true)',tab);
 END LOOP;
END $$;

-- Persisted identity predicate for transaction boundaries, with no JWT role trust.
CREATE OR REPLACE FUNCTION public.assessment_actor_can_access(p_actor text,p_owner text,p_candidate text,p_tenant_key text)
RETURNS boolean LANGUAGE sql STABLE SET search_path=public AS $$
 SELECT EXISTS(SELECT 1 FROM public.users u WHERE u.id::text=p_actor AND to_jsonb(u)->>'is_active' IS DISTINCT FROM 'false'
  AND ((u.role::text IN ('admin','recruiter') AND u.id::text=p_owner AND COALESCE(to_jsonb(u)->>'tenant_id','user:'||p_actor)=p_tenant_key)
   OR (u.role::text='candidate' AND EXISTS(SELECT 1 FROM public.candidates c WHERE c.id::text=p_candidate AND lower(c.email)=lower(u.email)
    AND (to_jsonb(u)->>'tenant_id' IS NULL OR to_jsonb(c)->>'tenant_id' IS NULL OR to_jsonb(c)->>'tenant_id'=to_jsonb(u)->>'tenant_id')))))
$$;

CREATE OR REPLACE FUNCTION public.save_roleplay_definition(p_actor text,p_id text,p_kind text,p_expected_revision integer,p_request_id text,p_request_hash text,p_definition jsonb)
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE u public.users%ROWTYPE; d public.roleplay_definitions%ROWTYPE; scope text; persona text;
BEGIN
 SELECT * INTO u FROM public.users WHERE id::text=p_actor;
 IF NOT FOUND OR u.role::text NOT IN ('admin','recruiter') OR to_jsonb(u)->>'is_active'='false' THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN'; END IF;
 scope:=COALESCE(to_jsonb(u)->>'tenant_id','user:'||p_actor);
 IF p_kind IS NULL OR p_kind NOT IN ('persona','scenario') THEN RAISE EXCEPTION 'FEATURE_INVALID'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('roleplay-definition:'||p_id,0));
 SELECT * INTO d FROM public.roleplay_definitions WHERE id=p_id FOR UPDATE;
 IF FOUND THEN
  IF d.created_by::text<>p_actor OR d.tenant_key<>scope OR d.kind<>p_kind THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN'; END IF;
  IF d.request_id=p_request_id THEN
   IF d.request_hash<>p_request_hash THEN RAISE EXCEPTION 'REPLAY_MISMATCH'; END IF;
   RETURN to_jsonb(d);
  END IF;
  IF d.revision<>p_expected_revision THEN RAISE EXCEPTION 'VERSION_CONFLICT'; END IF;
 ELSE
  IF p_expected_revision<>0 THEN RAISE EXCEPTION 'VERSION_CONFLICT'; END IF;
 END IF;
 persona:=CASE WHEN p_kind='scenario' THEN p_definition->>'persona_id' ELSE NULL END;
 IF p_kind='scenario' AND NOT EXISTS(SELECT 1 FROM public.roleplay_definitions WHERE id=persona AND kind='persona' AND created_by=u.id AND tenant_key=scope AND archived_at IS NULL) THEN RAISE EXCEPTION 'FEATURE_INVALID'; END IF;
 INSERT INTO public.roleplay_definitions(id,kind,created_by,tenant_key,persona_id,definition,revision,request_id,request_hash)
  VALUES(p_id,p_kind,u.id,scope,persona,p_definition,p_expected_revision+1,p_request_id,p_request_hash)
  ON CONFLICT(id) DO UPDATE SET persona_id=EXCLUDED.persona_id,definition=EXCLUDED.definition,revision=EXCLUDED.revision,
   request_id=EXCLUDED.request_id,request_hash=EXCLUDED.request_hash,updated_at=now() RETURNING * INTO d;
 RETURN to_jsonb(d);
END $$;

CREATE OR REPLACE FUNCTION public.create_roleplay_session(p_actor text,p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE u public.users%ROWTYPE; c public.candidates%ROWTYPE; s public.roleplay_sessions%ROWTYPE;
 sc public.roleplay_definitions%ROWTYPE; p public.roleplay_definitions%ROWTYPE; scope text;
BEGIN
 SELECT * INTO u FROM public.users WHERE id::text=p_actor;
 IF NOT FOUND OR u.role::text NOT IN ('admin','recruiter') OR to_jsonb(u)->>'is_active'='false' THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN'; END IF;
 scope:=COALESCE(to_jsonb(u)->>'tenant_id','user:'||p_actor);
 PERFORM pg_advisory_xact_lock(hashtextextended('roleplay-session:'||(p_payload->>'id'),0));
 SELECT * INTO s FROM public.roleplay_sessions WHERE id=p_payload->>'id';
 IF FOUND THEN
  IF s.created_by<>u.id OR s.tenant_key<>scope THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN'; END IF;
  IF s.request_hash IS DISTINCT FROM p_payload->>'request_hash' THEN RAISE EXCEPTION 'REPLAY_MISMATCH'; END IF;
  RETURN to_jsonb(s);
 END IF;
 SELECT * INTO sc FROM public.roleplay_definitions WHERE id=p_payload->>'scenario_id' AND kind='scenario' AND created_by=u.id AND tenant_key=scope AND archived_at IS NULL FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN'; END IF;
 SELECT * INTO p FROM public.roleplay_definitions WHERE id=sc.persona_id AND created_by=u.id AND tenant_key=scope AND archived_at IS NULL FOR SHARE;
 IF NOT FOUND OR sc.definition IS DISTINCT FROM p_payload->'scenario_snapshot'->'definition' OR p.definition IS DISTINCT FROM p_payload->'persona_snapshot'->'definition' THEN RAISE EXCEPTION 'VERSION_CONFLICT'; END IF;
 SELECT * INTO c FROM public.candidates WHERE id::text=p_payload->>'candidate_id';
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM public.applications a JOIN public.jobs j ON j.id=a.job_id
  WHERE a.candidate_id=c.id AND j.created_by=u.id AND (to_jsonb(j)->>'tenant_id' IS NULL OR to_jsonb(j)->>'tenant_id'=to_jsonb(u)->>'tenant_id')) THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN'; END IF;
 INSERT INTO public.roleplay_sessions(id,created_by,candidate_id,tenant_key,scenario_id,scenario_snapshot,persona_snapshot,candidate_profile,state,request_id,request_hash)
  VALUES(p_payload->>'id',u.id,c.id,scope,sc.id,p_payload->'scenario_snapshot',p_payload->'persona_snapshot',p_payload->'candidate_profile',p_payload->'state',p_payload->>'request_id',p_payload->>'request_hash') RETURNING * INTO s;
 RETURN to_jsonb(s);
END $$;

CREATE OR REPLACE FUNCTION public.commit_roleplay_event(p_actor text,p_session_id text,p_expected_revision integer,p_event jsonb,p_state jsonb)
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE s public.roleplay_sessions%ROWTYPE; e public.roleplay_events%ROWTYPE; u public.users%ROWTYPE; item jsonb; kind text;
BEGIN
 SELECT * INTO s FROM public.roleplay_sessions WHERE id=p_session_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'FEATURE_NOT_FOUND'; END IF;
 IF NOT public.assessment_actor_can_access(p_actor,s.created_by::text,s.candidate_id::text,s.tenant_key) THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN'; END IF;
 SELECT * INTO u FROM public.users WHERE id::text=p_actor;
 SELECT * INTO e FROM public.roleplay_events WHERE session_id=s.id AND request_id=p_event->>'request_id';
 IF FOUND THEN
  IF e.request_hash IS DISTINCT FROM p_event->>'request_hash' THEN RAISE EXCEPTION 'REPLAY_MISMATCH'; END IF;
  RETURN to_jsonb(e);
 END IF;
 IF s.revision<>p_expected_revision THEN RAISE EXCEPTION 'VERSION_CONFLICT'; END IF;
 kind:=p_event->>'kind';
 IF kind IN ('start','turn') AND u.role::text<>'candidate' THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN'; END IF;
 IF s.status IN ('completed','cancelled') OR (kind='start' AND s.status<>'assigned') OR (kind='turn' AND s.status<>'active') THEN RAISE EXCEPTION 'FEATURE_INVALID'; END IF;
 IF (kind='start' AND p_state->>'status'<>'active') OR (kind='finish' AND p_state->>'status'<>'completed') OR
    (kind='cancel' AND p_state->>'status'<>'cancelled') OR (kind='turn' AND p_state->>'status' NOT IN ('active','completed')) THEN RAISE EXCEPTION 'FEATURE_INVALID'; END IF;
 IF kind='turn' AND (p_state->>'turn_count')::integer<>(s.state->>'turn_count')::integer+1 THEN RAISE EXCEPTION 'FEATURE_INVALID'; END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(p_event->'evidence') LOOP
  IF item->>'event_id' IS DISTINCT FROM p_event->>'id' OR item->>'session_id' IS DISTINCT FROM s.id
   OR item->>'candidate_id' IS DISTINCT FROM s.candidate_id::text OR item->>'source_type'<>'role_play'
   OR position(item->>'quote' IN p_event->>'source_text')=0 THEN RAISE EXCEPTION 'FEATURE_INVALID_EVIDENCE'; END IF;
 END LOOP;
 INSERT INTO public.roleplay_events(id,session_id,candidate_id,revision,kind,request_id,request_hash,source_text,response,action,analysis,evidence,policy_context,projection_status)
  VALUES(p_event->>'id',s.id,s.candidate_id,s.revision+1,kind,p_event->>'request_id',p_event->>'request_hash',p_event->>'source_text',p_event->>'response',
   p_event->'action',p_event->'analysis',p_event->'evidence',p_event->'policy_context',CASE WHEN jsonb_array_length(p_event->'evidence')>0 THEN 'pending' ELSE 'skipped' END) RETURNING * INTO e;
 UPDATE public.roleplay_sessions SET state=p_state,revision=revision+1,updated_at=now() WHERE id=s.id;
 RETURN to_jsonb(e);
END $$;

CREATE OR REPLACE FUNCTION public.publish_roleplay_report(p_actor text,p_session_id text,p_report jsonb,p_error text)
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE s public.roleplay_sessions%ROWTYPE; item jsonb; score numeric;
BEGIN
 SELECT * INTO s FROM public.roleplay_sessions WHERE id=p_session_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'FEATURE_NOT_FOUND'; END IF;
 IF NOT public.assessment_actor_can_access(p_actor,s.created_by::text,s.candidate_id::text,s.tenant_key) THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN'; END IF;
 IF s.status<>'completed' THEN RAISE EXCEPTION 'FEATURE_INVALID'; END IF;
 IF s.report_status='ready' THEN RETURN s.report; END IF;
 IF p_report IS NULL THEN
  UPDATE public.roleplay_sessions SET report_status='failed',report_error=left(p_error,80) WHERE id=s.id;
  RETURN jsonb_build_object('status','failed');
 END IF;
 IF (SELECT count(*) FROM public.roleplay_events WHERE session_id=s.id AND jsonb_array_length(evidence)>0)<2
  OR jsonb_typeof(p_report->'narrative') IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'FEATURE_INVALID_REPORT'; END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(p_report->'evidence') LOOP
  IF NOT EXISTS(SELECT 1 FROM public.roleplay_events e CROSS JOIN LATERAL jsonb_array_elements(e.evidence) v WHERE e.session_id=s.id AND v.value=item) THEN RAISE EXCEPTION 'FEATURE_INVALID_EVIDENCE'; END IF;
 END LOOP;
 SELECT round(avg(dimension_score),2) INTO score FROM (
  SELECT avg((v.value->>'score')::numeric)*10 AS dimension_score FROM public.roleplay_events e CROSS JOIN LATERAL jsonb_array_elements(e.evidence) v
  WHERE e.session_id=s.id GROUP BY v.value->>'competency') dimensions;
 IF abs(score-(p_report->>'overall_score')::numeric)>0.02 OR abs(round(1+score/25,1)-(p_report->>'candidate_rating')::numeric)>0.0001 THEN RAISE EXCEPTION 'FEATURE_INVALID_REPORT'; END IF;
 UPDATE public.roleplay_sessions SET report=p_report,report_status='ready',report_error=NULL WHERE id=s.id;
 RETURN p_report;
END $$;
REVOKE ALL ON FUNCTION public.assessment_actor_can_access(text,text,text,text),public.save_roleplay_definition(text,text,text,integer,text,text,jsonb),public.create_roleplay_session(text,jsonb),public.commit_roleplay_event(text,text,integer,jsonb,jsonb),public.publish_roleplay_report(text,text,jsonb,text) FROM PUBLIC,anon,authenticated,authenticator;
GRANT EXECUTE ON FUNCTION public.assessment_actor_can_access(text,text,text,text),public.save_roleplay_definition(text,text,text,integer,text,text,jsonb),public.create_roleplay_session(text,jsonb),public.commit_roleplay_event(text,text,integer,jsonb,jsonb),public.publish_roleplay_report(text,text,jsonb,text) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
