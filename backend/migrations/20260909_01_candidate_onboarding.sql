-- Independent resume versions. Supports both legacy TEXT and hosted UUID identities.
BEGIN;
DO $ddl$
DECLARE utype text; ctype text;
BEGIN
  SELECT format_type(atttypid,atttypmod) INTO utype FROM pg_attribute WHERE attrelid='public.users'::regclass AND attname='id';
  SELECT format_type(atttypid,atttypmod) INTO ctype FROM pg_attribute WHERE attrelid='public.candidates'::regclass AND attname='id';
  EXECUTE format('CREATE TABLE IF NOT EXISTS public.candidate_profiles (
    user_id %s PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    candidate_id %s NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
    current_resume_id text, revision integer NOT NULL DEFAULT 0 CHECK(revision>=0),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now())',utype,ctype);
  EXECUTE format('CREATE TABLE IF NOT EXISTS public.candidate_resume_versions (
    id text PRIMARY KEY, user_id %s NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    candidate_id %s NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
    version integer NOT NULL CHECK(version>0), request_id text NOT NULL,
    filename text NOT NULL CHECK(length(filename) BETWEEN 1 AND 180),
    extension text NOT NULL CHECK(extension IN (''pdf'',''docx'')),
    storage_key text NOT NULL UNIQUE, content_sha256 text NOT NULL CHECK(length(content_sha256)=64),
    profile jsonb NOT NULL CHECK(jsonb_typeof(profile)=''object''),
    raw_text text NOT NULL CHECK(length(raw_text) BETWEEN 30 AND 100000),
    parse_source text NOT NULL CHECK(parse_source IN (''aicredits'',''local_fallback'')),
    created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(user_id,version), UNIQUE(user_id,request_id))',utype,ctype);
END $ddl$;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='candidate_profiles_current_resume_fk') THEN
  ALTER TABLE public.candidate_profiles ADD CONSTRAINT candidate_profiles_current_resume_fk
   FOREIGN KEY(current_resume_id) REFERENCES public.candidate_resume_versions(id) ON DELETE SET NULL;
 END IF;
END $$;
CREATE INDEX IF NOT EXISTS candidate_resume_candidate_idx ON public.candidate_resume_versions(candidate_id,created_at DESC);
ALTER TABLE public.candidate_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.candidate_resume_versions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.candidate_profiles,public.candidate_resume_versions FROM PUBLIC,anon,authenticated,authenticator;
GRANT ALL ON public.candidate_profiles,public.candidate_resume_versions TO service_role;
-- Local development service_role lacks Supabase's BYPASSRLS attribute.
DROP POLICY IF EXISTS candidate_profiles_server ON public.candidate_profiles;
CREATE POLICY candidate_profiles_server ON public.candidate_profiles TO service_role USING(true) WITH CHECK(true);
DROP POLICY IF EXISTS candidate_resumes_server ON public.candidate_resume_versions;
CREATE POLICY candidate_resumes_server ON public.candidate_resume_versions TO service_role USING(true) WITH CHECK(true);

CREATE OR REPLACE FUNCTION public.save_candidate_resume(p_user_id text,p_expected_revision integer,p_resume jsonb)
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE u public.users%ROWTYPE; c public.candidates%ROWTYPE;
 p public.candidate_profiles%ROWTYPE; v public.candidate_resume_versions%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('candidate-profile:'||p_user_id,0));
 SELECT * INTO u FROM public.users WHERE id::text=p_user_id;
 IF NOT FOUND OR u.role::text<>'candidate' OR to_jsonb(u)->>'is_active'='false' THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN'; END IF;
 IF jsonb_typeof(p_resume) IS DISTINCT FROM 'object' OR p_resume->>'request_id' IS NULL THEN RAISE EXCEPTION 'FEATURE_INVALID'; END IF;
 SELECT * INTO v FROM public.candidate_resume_versions WHERE user_id::text=p_user_id AND request_id=p_resume->>'request_id';
 IF FOUND THEN
  IF v.content_sha256 IS DISTINCT FROM p_resume->>'content_sha256' THEN RAISE EXCEPTION 'REPLAY_MISMATCH'; END IF;
  RETURN to_jsonb(v);
 END IF;
 SELECT * INTO p FROM public.candidate_profiles WHERE user_id::text=p_user_id FOR UPDATE;
 IF COALESCE(p.revision,0) IS DISTINCT FROM p_expected_revision THEN RAISE EXCEPTION 'VERSION_CONFLICT'; END IF;
 SELECT * INTO c FROM public.candidates WHERE lower(email)=lower(u.email) ORDER BY created_at,id LIMIT 1;
 IF NOT FOUND THEN
  SELECT * INTO c FROM jsonb_populate_record(NULL::public.candidates,jsonb_build_object('id',gen_random_uuid()::text,'email',lower(u.email),'name',u.name));
  INSERT INTO public.candidates(id,email,name) VALUES(c.id,c.email,c.name) RETURNING * INTO c;
 END IF;
 IF to_jsonb(u)->>'tenant_id' IS NOT NULL AND to_jsonb(c)->>'tenant_id' IS NOT NULL
    AND to_jsonb(u)->>'tenant_id' IS DISTINCT FROM to_jsonb(c)->>'tenant_id' THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN'; END IF;
 INSERT INTO public.candidate_profiles(user_id,candidate_id) VALUES(u.id,c.id) ON CONFLICT(user_id) DO NOTHING;
 INSERT INTO public.candidate_resume_versions(id,user_id,candidate_id,version,request_id,filename,extension,
   storage_key,content_sha256,profile,raw_text,parse_source)
 VALUES(p_resume->>'id',u.id,c.id,p_expected_revision+1,p_resume->>'request_id',p_resume->>'filename',
   p_resume->>'extension',p_resume->>'storage_key',p_resume->>'content_sha256',p_resume->'profile',
   p_resume->>'raw_text',p_resume->>'parse_source') RETURNING * INTO v;
 UPDATE public.candidate_profiles SET current_resume_id=v.id,revision=v.version,updated_at=now() WHERE user_id=u.id;
 RETURN to_jsonb(v);
END $$;
REVOKE ALL ON FUNCTION public.save_candidate_resume(text,integer,jsonb) FROM PUBLIC,anon,authenticated,authenticator;
GRANT EXECUTE ON FUNCTION public.save_candidate_resume(text,integer,jsonb) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
