-- GD owns its lifecycle and ordered event/analysis transactions.
BEGIN;
DO $ddl$
DECLARE utype text; ctype text;
BEGIN
 SELECT format_type(atttypid,atttypmod) INTO utype FROM pg_attribute WHERE attrelid='public.users'::regclass AND attname='id';
 SELECT format_type(atttypid,atttypmod) INTO ctype FROM pg_attribute WHERE attrelid='public.candidates'::regclass AND attname='id';
 EXECUTE format('CREATE TABLE IF NOT EXISTS public.gd_sessions (
  id text PRIMARY KEY,created_by %s NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  tenant_key text NOT NULL,configuration jsonb NOT NULL CHECK(jsonb_typeof(configuration)=''object''),
  status text NOT NULL DEFAULT ''lobby'' CHECK(status IN (''lobby'',''active'',''completed'',''cancelled'')),
  revision integer NOT NULL DEFAULT 0 CHECK(revision>=0),moderator_state jsonb NOT NULL DEFAULT ''{}'',
  request_id text NOT NULL,request_hash text NOT NULL,started_at timestamptz,ended_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(created_by,request_id))',utype);
 EXECUTE format('CREATE TABLE IF NOT EXISTS public.gd_participants (
  id text PRIMARY KEY,session_id text NOT NULL REFERENCES public.gd_sessions(id) ON DELETE CASCADE,
  candidate_id %s NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
  display_name text NOT NULL CHECK(length(display_name) BETWEEN 1 AND 80),
  status text NOT NULL DEFAULT ''invited'' CHECK(status IN (''invited'',''joined'',''left'',''removed'')),
  invitation_hash text NOT NULL CHECK(length(invitation_hash)=64),invitation_expires_at timestamptz NOT NULL,
  invite_request_id text NOT NULL,invite_request_hash text NOT NULL,accepted_request_id text,accepted_at timestamptz,
  joined_at timestamptz,left_at timestamptz,hand_raised boolean NOT NULL DEFAULT false,
  report_status text NOT NULL DEFAULT ''not_started'' CHECK(report_status IN (''not_started'',''failed'',''ready'')),
  report jsonb,report_error text,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(session_id,candidate_id),UNIQUE(session_id,invite_request_id),UNIQUE(invitation_hash))',ctype);
 EXECUTE format('CREATE TABLE IF NOT EXISTS public.gd_events (
  id text PRIMARY KEY,session_id text NOT NULL REFERENCES public.gd_sessions(id) ON DELETE CASCADE,
  participant_id text REFERENCES public.gd_participants(id) ON DELETE CASCADE,
  actor_id %s REFERENCES public.users(id) ON DELETE SET NULL,candidate_id %s REFERENCES public.candidates(id) ON DELETE CASCADE,
  sequence integer NOT NULL CHECK(sequence>0),
  kind text NOT NULL CHECK(kind IN (''invitation'',''join'',''leave'',''rejoin'',''raise_hand'',''lower_hand'',''remove'',''start'',''finish'',''cancel'',''message'',''expired'')),
  request_id text NOT NULL,request_hash text NOT NULL,
  source_text text NOT NULL DEFAULT '''' CHECK(length(source_text)<=4000),
  response text NOT NULL DEFAULT '''' CHECK(length(response)<=800),reply_to text REFERENCES public.gd_events(id),
  action jsonb NOT NULL DEFAULT ''{}'',analysis jsonb NOT NULL DEFAULT ''{"status":"not_applicable"}'',
  evidence jsonb NOT NULL DEFAULT ''[]'' CHECK(jsonb_typeof(evidence)=''array'' AND jsonb_array_length(evidence)<=8),
  deterministic_signals jsonb NOT NULL DEFAULT ''{}'',policy_context jsonb,
  analysis_attempts integer NOT NULL DEFAULT 0,moderation_lease text,moderation_lease_until timestamptz,
  projection_status text NOT NULL DEFAULT ''skipped'' CHECK(projection_status IN (''pending'',''delivered'',''failed'',''skipped'')),
  projection_attempts integer NOT NULL DEFAULT 0,projection_error text,projection_attempted_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(session_id,sequence),UNIQUE(session_id,request_id))',utype,ctype);
END $ddl$;
CREATE INDEX IF NOT EXISTS gd_sessions_owner_idx ON public.gd_sessions(created_by,tenant_key,created_at DESC);
CREATE INDEX IF NOT EXISTS gd_sessions_active_idx ON public.gd_sessions(started_at) WHERE status='active';
CREATE INDEX IF NOT EXISTS gd_participants_candidate_idx ON public.gd_participants(candidate_id,created_at DESC);
CREATE INDEX IF NOT EXISTS gd_events_pending_idx ON public.gd_events(session_id,sequence) WHERE analysis->>'status'='pending';
CREATE INDEX IF NOT EXISTS gd_events_projection_idx ON public.gd_events(projection_status,created_at) WHERE projection_status IN ('pending','failed');
DO $$ DECLARE tab text; BEGIN
 FOREACH tab IN ARRAY ARRAY['gd_sessions','gd_participants','gd_events'] LOOP
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',tab);
  EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC,anon,authenticated,authenticator',tab);
  EXECUTE format('GRANT ALL ON public.%I TO service_role',tab);
  EXECUTE format('DROP POLICY IF EXISTS feature_server ON public.%I',tab);
  EXECUTE format('CREATE POLICY feature_server ON public.%I TO service_role USING(true) WITH CHECK(true)',tab);
 END LOOP;
END $$;

CREATE OR REPLACE FUNCTION public.create_gd_session(p_actor text,p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE u public.users%ROWTYPE;s public.gd_sessions%ROWTYPE;scope text;
BEGIN
 SELECT * INTO u FROM public.users WHERE id::text=p_actor;
 IF NOT FOUND OR u.role::text NOT IN ('recruiter','admin') OR to_jsonb(u)->>'is_active'='false' THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN';END IF;
 scope:=COALESCE(to_jsonb(u)->>'tenant_id','user:'||p_actor);
 PERFORM pg_advisory_xact_lock(hashtextextended('gd-create:'||(p_payload->>'id'),0));
 SELECT * INTO s FROM public.gd_sessions WHERE id=p_payload->>'id';
 IF FOUND THEN
  IF s.created_by<>u.id OR s.tenant_key<>scope THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN';END IF;
  IF s.request_hash IS DISTINCT FROM p_payload->>'request_hash' THEN RAISE EXCEPTION 'REPLAY_MISMATCH';END IF;
  RETURN to_jsonb(s);
 END IF;
 INSERT INTO public.gd_sessions(id,created_by,tenant_key,configuration,request_id,request_hash)
  VALUES(p_payload->>'id',u.id,scope,p_payload->'configuration',p_payload->>'request_id',p_payload->>'request_hash') RETURNING * INTO s;
 RETURN to_jsonb(s);
END $$;

CREATE OR REPLACE FUNCTION public.invite_gd_participant(p_actor text,p_session_id text,p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE u public.users%ROWTYPE;s public.gd_sessions%ROWTYPE;p public.gd_participants%ROWTYPE;c public.candidates%ROWTYPE;
BEGIN
 SELECT * INTO s FROM public.gd_sessions WHERE id=p_session_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'FEATURE_NOT_FOUND';END IF;
 SELECT * INTO u FROM public.users WHERE id::text=p_actor;
 IF NOT FOUND OR u.role::text NOT IN ('recruiter','admin') OR to_jsonb(u)->>'is_active'='false'
  OR s.created_by<>u.id OR s.tenant_key<>COALESCE(to_jsonb(u)->>'tenant_id','user:'||p_actor) THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN';END IF;
 SELECT * INTO p FROM public.gd_participants WHERE session_id=s.id AND invite_request_id=p_payload->>'request_id';
 IF FOUND THEN
  IF p.invite_request_hash IS DISTINCT FROM p_payload->>'request_hash' THEN RAISE EXCEPTION 'REPLAY_MISMATCH';END IF;
  RETURN to_jsonb(p);
 END IF;
 IF s.status NOT IN ('lobby','active') OR s.revision>=990 THEN RAISE EXCEPTION 'FEATURE_INVALID';END IF;
 SELECT * INTO c FROM public.candidates WHERE id::text=p_payload->>'candidate_id';
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM public.applications a JOIN public.jobs j ON j.id=a.job_id WHERE a.candidate_id=c.id AND j.created_by=u.id
   AND (to_jsonb(j)->>'tenant_id' IS NULL OR to_jsonb(j)->>'tenant_id'=to_jsonb(u)->>'tenant_id')) THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN';END IF;
 SELECT * INTO p FROM public.gd_participants WHERE session_id=s.id AND candidate_id=c.id;
 IF FOUND AND p.status='joined' THEN RAISE EXCEPTION 'FEATURE_INVALID_ALREADY_JOINED';END IF;
 IF (p.id IS NULL OR p.status='removed') AND (SELECT count(*) FROM public.gd_participants WHERE session_id=s.id AND status<>'removed')>=(s.configuration->>'max_participants')::integer THEN RAISE EXCEPTION 'FEATURE_INVALID_CAPACITY';END IF;
 INSERT INTO public.gd_participants(id,session_id,candidate_id,display_name,invitation_hash,invitation_expires_at,invite_request_id,invite_request_hash)
  VALUES(p_payload->>'id',s.id,c.id,p_payload->>'display_name',p_payload->>'token_hash',(p_payload->>'expires_at')::timestamptz,p_payload->>'request_id',p_payload->>'request_hash')
  ON CONFLICT(session_id,candidate_id) DO UPDATE SET status='invited',invitation_hash=EXCLUDED.invitation_hash,invitation_expires_at=EXCLUDED.invitation_expires_at,
   invite_request_id=EXCLUDED.invite_request_id,invite_request_hash=EXCLUDED.invite_request_hash,accepted_at=NULL,accepted_request_id=NULL,hand_raised=false,updated_at=now() RETURNING * INTO p;
 INSERT INTO public.gd_events(id,session_id,participant_id,actor_id,candidate_id,sequence,kind,request_id,request_hash)
  VALUES(gen_random_uuid()::text,s.id,p.id,u.id,c.id,s.revision+1,'invitation',p_payload->>'request_id',p_payload->>'request_hash');
 UPDATE public.gd_sessions SET revision=revision+1,updated_at=now() WHERE id=s.id;
 RETURN to_jsonb(p);
END $$;

CREATE OR REPLACE FUNCTION public.accept_gd_invitation(p_actor text,p_session_id text,p_token_hash text,p_request_id text)
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE s public.gd_sessions%ROWTYPE;p public.gd_participants%ROWTYPE;u public.users%ROWTYPE;
BEGIN
 SELECT * INTO s FROM public.gd_sessions WHERE id=p_session_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'FEATURE_NOT_FOUND';END IF;
 SELECT * INTO u FROM public.users WHERE id::text=p_actor;
 IF NOT FOUND OR u.role::text<>'candidate' OR to_jsonb(u)->>'is_active'='false' THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN';END IF;
 SELECT p0.* INTO p FROM public.gd_participants p0 JOIN public.candidates c ON c.id=p0.candidate_id
  WHERE p0.session_id=s.id AND lower(c.email)=lower(u.email) AND p0.invitation_hash=p_token_hash LIMIT 1;
 IF NOT FOUND OR NOT public.assessment_actor_can_access(p_actor,s.created_by::text,p.candidate_id::text,s.tenant_key) THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN';END IF;
 IF p.accepted_at IS NOT NULL THEN
  IF p.accepted_request_id=p_request_id AND p.status<>'removed' THEN RETURN to_jsonb(p);END IF;
  RAISE EXCEPTION 'VERSION_CONFLICT_INVITATION_CONSUMED';
 END IF;
 IF p.status<>'invited' OR p.invitation_expires_at<=now() OR s.status NOT IN ('lobby','active')
  OR (s.started_at IS NOT NULL AND now()>=s.started_at+make_interval(secs=>(s.configuration->>'duration_seconds')::integer)) THEN RAISE EXCEPTION 'FEATURE_INVALID_INVITATION_EXPIRED';END IF;
 UPDATE public.gd_participants SET status='joined',accepted_at=now(),accepted_request_id=p_request_id,joined_at=now(),left_at=NULL,updated_at=now() WHERE id=p.id RETURNING * INTO p;
 INSERT INTO public.gd_events(id,session_id,participant_id,actor_id,candidate_id,sequence,kind,request_id,request_hash)
  VALUES(gen_random_uuid()::text,s.id,p.id,u.id,p.candidate_id,s.revision+1,'join',p_request_id,p_token_hash);
 UPDATE public.gd_sessions SET revision=revision+1,updated_at=now() WHERE id=s.id;
 RETURN to_jsonb(p);
END $$;

CREATE OR REPLACE FUNCTION public.control_gd_session(p_actor text,p_session_id text,p_action text,p_expected_revision integer,p_request_id text)
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE s public.gd_sessions%ROWTYPE;u public.users%ROWTYPE;e public.gd_events%ROWTYPE;next_status text;
BEGIN
 SELECT * INTO s FROM public.gd_sessions WHERE id=p_session_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'FEATURE_NOT_FOUND';END IF;
 SELECT * INTO u FROM public.users WHERE id::text=p_actor;
 IF NOT FOUND OR u.role::text NOT IN ('recruiter','admin') OR to_jsonb(u)->>'is_active'='false' OR s.created_by<>u.id
  OR s.tenant_key<>COALESCE(to_jsonb(u)->>'tenant_id','user:'||p_actor) THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN';END IF;
 SELECT * INTO e FROM public.gd_events WHERE session_id=s.id AND request_id=p_request_id;
 IF FOUND THEN
  IF e.actor_id<>u.id OR e.request_hash<>'control:'||p_action THEN RAISE EXCEPTION 'REPLAY_MISMATCH';END IF;
  RETURN to_jsonb(s);
 END IF;
 IF s.revision<>p_expected_revision THEN RAISE EXCEPTION 'VERSION_CONFLICT';END IF;
 IF p_action='start' THEN
  IF s.status<>'lobby' OR (SELECT count(*) FROM public.gd_participants WHERE session_id=s.id AND status='joined')<(s.configuration->>'min_participants')::integer THEN RAISE EXCEPTION 'FEATURE_INVALID_QUORUM';END IF;
  next_status:='active';
 ELSIF p_action IN ('finish','cancel') AND s.status IN ('lobby','active') THEN
  next_status:=CASE WHEN p_action='finish' THEN 'completed' ELSE 'cancelled' END;
 ELSE RAISE EXCEPTION 'FEATURE_INVALID';END IF;
 INSERT INTO public.gd_events(id,session_id,actor_id,sequence,kind,request_id,request_hash,response)
  VALUES(gen_random_uuid()::text,s.id,u.id,s.revision+1,p_action,p_request_id,'control:'||p_action,
   CASE WHEN p_action='start' THEN 'The discussion has started. Please give everyone an opportunity to contribute.' ELSE 'The discussion has ended. Thank you for your contributions.' END);
 UPDATE public.gd_sessions SET status=next_status,revision=revision+1,updated_at=now(),
  started_at=CASE WHEN next_status='active' THEN now() ELSE started_at END,ended_at=CASE WHEN next_status IN ('completed','cancelled') THEN now() ELSE NULL END WHERE id=s.id RETURNING * INTO s;
 RETURN to_jsonb(s);
END $$;

CREATE OR REPLACE FUNCTION public.change_gd_participant(p_actor text,p_session_id text,p_action text,p_request_id text,p_participant_id text DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE s public.gd_sessions%ROWTYPE;u public.users%ROWTYPE;p public.gd_participants%ROWTYPE;e public.gd_events%ROWTYPE;
BEGIN
 SELECT * INTO s FROM public.gd_sessions WHERE id=p_session_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'FEATURE_NOT_FOUND';END IF;
 SELECT * INTO u FROM public.users WHERE id::text=p_actor;
 IF NOT FOUND OR to_jsonb(u)->>'is_active'='false' THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN';END IF;
 IF p_action='remove' THEN
  IF u.role::text NOT IN ('recruiter','admin') OR s.created_by<>u.id OR s.tenant_key<>COALESCE(to_jsonb(u)->>'tenant_id','user:'||p_actor) THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN';END IF;
  SELECT * INTO p FROM public.gd_participants WHERE session_id=s.id AND id=p_participant_id;
 ELSE
  IF u.role::text<>'candidate' THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN';END IF;
  SELECT p0.* INTO p FROM public.gd_participants p0 JOIN public.candidates c ON c.id=p0.candidate_id WHERE p0.session_id=s.id AND lower(c.email)=lower(u.email) LIMIT 1;
 END IF;
 IF p.id IS NULL OR NOT public.assessment_actor_can_access(p_actor,s.created_by::text,p.candidate_id::text,s.tenant_key) THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN';END IF;
 SELECT * INTO e FROM public.gd_events WHERE session_id=s.id AND request_id=p_request_id;
 IF FOUND THEN
  IF e.actor_id<>u.id OR e.participant_id<>p.id OR e.kind<>p_action THEN RAISE EXCEPTION 'REPLAY_MISMATCH';END IF;
  RETURN to_jsonb(p);
 END IF;
 IF s.status NOT IN ('lobby','active') OR s.revision>=990 THEN RAISE EXCEPTION 'FEATURE_INVALID';END IF;
 IF p_action='remove' THEN
  UPDATE public.gd_participants SET status='removed',hand_raised=false,left_at=now(),updated_at=now() WHERE id=p.id RETURNING * INTO p;
 ELSIF p_action='rejoin' AND p.status='left' AND p.accepted_at IS NOT NULL THEN
  UPDATE public.gd_participants SET status='joined',joined_at=now(),left_at=NULL,updated_at=now() WHERE id=p.id RETURNING * INTO p;
 ELSIF p_action='leave' AND p.status='joined' THEN
  UPDATE public.gd_participants SET status='left',left_at=now(),hand_raised=false,updated_at=now() WHERE id=p.id RETURNING * INTO p;
 ELSIF p_action IN ('raise_hand','lower_hand') AND p.status='joined' THEN
  UPDATE public.gd_participants SET hand_raised=(p_action='raise_hand'),updated_at=now() WHERE id=p.id RETURNING * INTO p;
 ELSE RAISE EXCEPTION 'FEATURE_INVALID_PARTICIPANT_TRANSITION';END IF;
 INSERT INTO public.gd_events(id,session_id,participant_id,actor_id,candidate_id,sequence,kind,request_id,request_hash)
  VALUES(gen_random_uuid()::text,s.id,p.id,u.id,p.candidate_id,s.revision+1,p_action,p_request_id,'attendance:'||p_action);
 UPDATE public.gd_sessions SET revision=revision+1,updated_at=now() WHERE id=s.id;
 RETURN to_jsonb(p);
END $$;

CREATE OR REPLACE FUNCTION public.append_gd_message(p_actor text,p_session_id text,p_event jsonb)
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE s public.gd_sessions%ROWTYPE;u public.users%ROWTYPE;p public.gd_participants%ROWTYPE;e public.gd_events%ROWTYPE;r public.gd_events%ROWTYPE;
BEGIN
 SELECT * INTO s FROM public.gd_sessions WHERE id=p_session_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'FEATURE_NOT_FOUND';END IF;
 SELECT * INTO u FROM public.users WHERE id::text=p_actor;
 IF NOT FOUND OR u.role::text<>'candidate' OR to_jsonb(u)->>'is_active'='false' THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN';END IF;
 SELECT p0.* INTO p FROM public.gd_participants p0 JOIN public.candidates c ON c.id=p0.candidate_id WHERE p0.session_id=s.id AND lower(c.email)=lower(u.email) LIMIT 1;
 IF p.id IS NULL OR p.status<>'joined' OR p.accepted_at IS NULL OR NOT public.assessment_actor_can_access(p_actor,s.created_by::text,p.candidate_id::text,s.tenant_key) THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN';END IF;
 SELECT * INTO e FROM public.gd_events WHERE session_id=s.id AND request_id=p_event->>'request_id';
 IF FOUND THEN
  IF e.actor_id<>u.id OR e.participant_id<>p.id OR e.request_hash IS DISTINCT FROM p_event->>'request_hash' THEN RAISE EXCEPTION 'REPLAY_MISMATCH';END IF;
  RETURN to_jsonb(e);
 END IF;
 IF s.status<>'active' OR now()>=s.started_at+make_interval(secs=>(s.configuration->>'duration_seconds')::integer) OR s.revision>=990 THEN RAISE EXCEPTION 'FEATURE_INVALID_DISCUSSION_ENDED';END IF;
 IF (SELECT count(*) FROM public.gd_events WHERE participant_id=p.id AND kind='message' AND created_at>now()-interval '10 seconds')>=5 THEN RAISE EXCEPTION 'FEATURE_INVALID_MESSAGE_RATE';END IF;
 IF p_event->>'reply_to' IS NOT NULL THEN
  SELECT * INTO r FROM public.gd_events WHERE id=p_event->>'reply_to' AND session_id=s.id AND kind='message';
  IF NOT FOUND OR r.participant_id=p.id THEN RAISE EXCEPTION 'FEATURE_INVALID_REPLY';END IF;
 END IF;
 IF length(btrim(p_event->>'source_text')) NOT BETWEEN 1 AND 4000 THEN RAISE EXCEPTION 'FEATURE_INVALID';END IF;
 INSERT INTO public.gd_events(id,session_id,participant_id,actor_id,candidate_id,sequence,kind,request_id,request_hash,source_text,reply_to,analysis)
  VALUES(p_event->>'id',s.id,p.id,u.id,p.candidate_id,s.revision+1,'message',p_event->>'request_id',p_event->>'request_hash',p_event->>'source_text',p_event->>'reply_to','{"status":"pending"}') RETURNING * INTO e;
 UPDATE public.gd_sessions SET revision=revision+1,updated_at=now() WHERE id=s.id;
 RETURN to_jsonb(e);
END $$;

CREATE OR REPLACE FUNCTION public.claim_gd_analysis(p_session_id text,p_lease text)
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE s public.gd_sessions%ROWTYPE;e public.gd_events%ROWTYPE;
BEGIN
 SELECT * INTO s FROM public.gd_sessions WHERE id=p_session_id FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL;END IF;
 SELECT * INTO e FROM public.gd_events WHERE session_id=s.id AND analysis->>'status'='pending' ORDER BY sequence LIMIT 1 FOR UPDATE;
 IF NOT FOUND OR (e.moderation_lease IS NOT NULL AND e.moderation_lease_until>now()) THEN RETURN NULL;END IF;
 IF p_lease IS NULL OR length(p_lease)<20 THEN RAISE EXCEPTION 'FEATURE_INVALID_LEASE';END IF;
 UPDATE public.gd_events SET moderation_lease=p_lease,moderation_lease_until=now()+interval '2 minutes',analysis_attempts=analysis_attempts+1 WHERE id=e.id RETURNING * INTO e;
 RETURN jsonb_build_object('event',to_jsonb(e),'session',to_jsonb(s));
END $$;

CREATE OR REPLACE FUNCTION public.finish_gd_analysis(p_session_id text,p_event_id text,p_lease text,p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE s public.gd_sessions%ROWTYPE;e public.gd_events%ROWTYPE;item jsonb;response_text text;
BEGIN
 SELECT * INTO s FROM public.gd_sessions WHERE id=p_session_id FOR UPDATE;
 SELECT * INTO e FROM public.gd_events WHERE id=p_event_id AND session_id=p_session_id FOR UPDATE;
 IF NOT FOUND OR e.moderation_lease IS DISTINCT FROM p_lease OR e.moderation_lease_until<=now() OR e.analysis->>'status'<>'pending' THEN RAISE EXCEPTION 'VERSION_CONFLICT_ANALYSIS_LEASE';END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(p_payload->'evidence') LOOP
  IF item->>'event_id' IS DISTINCT FROM e.id OR item->>'session_id' IS DISTINCT FROM s.id OR item->>'candidate_id' IS DISTINCT FROM e.candidate_id::text
   OR item->>'participant_id' IS DISTINCT FROM e.participant_id OR item->>'source_type'<>'group_discussion'
   OR position(item->>'quote' IN e.source_text)=0 THEN RAISE EXCEPTION 'FEATURE_INVALID_EVIDENCE';END IF;
 END LOOP;
 IF p_payload->'action'->>'target_participant_id' IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.gd_participants WHERE id=p_payload->'action'->>'target_participant_id' AND session_id=s.id AND status='joined') THEN
  -- A participant may leave while reasoning is in flight. Suppress the stale prompt.
  response_text:='';
 ELSE response_text:=CASE WHEN s.status='active' THEN p_payload->>'response' ELSE '' END;END IF;
 UPDATE public.gd_events SET analysis=p_payload->'analysis',evidence=p_payload->'evidence',action=p_payload->'action',response=response_text,
  deterministic_signals=p_payload->'deterministic_signals',policy_context=p_payload->'policy_context',moderation_lease=NULL,moderation_lease_until=NULL,
  projection_status=CASE WHEN jsonb_array_length(p_payload->'evidence')>0 THEN 'pending' ELSE 'skipped' END WHERE id=e.id RETURNING * INTO e;
 UPDATE public.gd_sessions SET moderator_state=(p_payload->'moderator_state')||jsonb_build_object('last_processed_sequence',e.sequence),updated_at=now() WHERE id=s.id;
 IF p_payload->'action'->>'action'='END_DISCUSSION' AND s.status='active' AND now()>=s.started_at+make_interval(secs=>(s.configuration->>'duration_seconds')::integer) THEN
  UPDATE public.gd_sessions SET status='completed',ended_at=now() WHERE id=s.id;
 END IF;
 RETURN to_jsonb(e);
END $$;

CREATE OR REPLACE FUNCTION public.publish_gd_report(p_actor text,p_participant_id text,p_report jsonb,p_error text)
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE p public.gd_participants%ROWTYPE;s public.gd_sessions%ROWTYPE;item jsonb;score numeric;
BEGIN
 SELECT * INTO p FROM public.gd_participants WHERE id=p_participant_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'FEATURE_NOT_FOUND';END IF;
 SELECT * INTO s FROM public.gd_sessions WHERE id=p.session_id;
 IF NOT public.assessment_actor_can_access(p_actor,s.created_by::text,p.candidate_id::text,s.tenant_key) OR (p.status='removed' AND p_actor<>s.created_by::text) THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN';END IF;
 IF s.status<>'completed' THEN RAISE EXCEPTION 'FEATURE_INVALID';END IF;
 IF p.report_status='ready' THEN RETURN p.report;END IF;
 IF p_report IS NULL THEN
  UPDATE public.gd_participants SET report_status='failed',report_error=left(p_error,80) WHERE id=p.id;
  RETURN jsonb_build_object('status','failed');
 END IF;
 IF EXISTS(SELECT 1 FROM public.gd_events WHERE participant_id=p.id AND analysis->>'status'='pending')
  OR (SELECT count(*) FROM public.gd_events WHERE participant_id=p.id AND jsonb_array_length(evidence)>0)<2
  OR jsonb_typeof(p_report->'narrative') IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'FEATURE_INVALID_REPORT';END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(p_report->'evidence') LOOP
  IF NOT EXISTS(SELECT 1 FROM public.gd_events e CROSS JOIN LATERAL jsonb_array_elements(e.evidence) v WHERE e.participant_id=p.id AND v.value=item) THEN RAISE EXCEPTION 'FEATURE_INVALID_EVIDENCE';END IF;
 END LOOP;
 SELECT round(avg(dimension_score),2) INTO score FROM (
  SELECT avg((v.value->>'score')::numeric)*10 AS dimension_score FROM public.gd_events e CROSS JOIN LATERAL jsonb_array_elements(e.evidence) v
  WHERE e.participant_id=p.id GROUP BY v.value->>'competency') dimensions;
 IF abs(score-(p_report->>'overall_score')::numeric)>0.02 OR abs(round(1+score/25,1)-(p_report->>'candidate_rating')::numeric)>0.0001 THEN RAISE EXCEPTION 'FEATURE_INVALID_REPORT';END IF;
 UPDATE public.gd_participants SET report=p_report,report_status='ready',report_error=NULL WHERE id=p.id;
 RETURN p_report;
END $$;
REVOKE ALL ON FUNCTION public.create_gd_session(text,jsonb),public.invite_gd_participant(text,text,jsonb),public.accept_gd_invitation(text,text,text,text),public.control_gd_session(text,text,text,integer,text),public.change_gd_participant(text,text,text,text,text),public.append_gd_message(text,text,jsonb),public.claim_gd_analysis(text,text),public.finish_gd_analysis(text,text,text,jsonb),public.publish_gd_report(text,text,jsonb,text) FROM PUBLIC,anon,authenticated,authenticator;
GRANT EXECUTE ON FUNCTION public.create_gd_session(text,jsonb),public.invite_gd_participant(text,text,jsonb),public.accept_gd_invitation(text,text,text,text),public.control_gd_session(text,text,text,integer,text),public.change_gd_participant(text,text,text,text,text),public.append_gd_message(text,text,jsonb),public.claim_gd_analysis(text,text),public.finish_gd_analysis(text,text,text,jsonb),public.publish_gd_report(text,text,jsonb,text) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
