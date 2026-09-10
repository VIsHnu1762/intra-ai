BEGIN;
DO $ddl$
DECLARE utype text;
BEGIN
 SELECT format_type(atttypid,atttypmod) INTO utype FROM pg_attribute WHERE attrelid='public.users'::regclass AND attname='id';
 EXECUTE format('CREATE TABLE IF NOT EXISTS public.company_documents (
  id text PRIMARY KEY, created_by %s NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  tenant_key text NOT NULL, title text NOT NULL CHECK(length(title) BETWEEN 1 AND 160),
  policy_key text NOT NULL CHECK(policy_key ~ ''^[a-z0-9][a-z0-9_-]{0,79}$''),
  revision integer NOT NULL DEFAULT 0 CHECK(revision>=0), archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(created_by,tenant_key,policy_key))',utype);
END $ddl$;
CREATE TABLE IF NOT EXISTS public.company_document_versions (
 id text PRIMARY KEY, document_id text NOT NULL REFERENCES public.company_documents(id) ON DELETE CASCADE,
 version integer NOT NULL CHECK(version>0), title text NOT NULL CHECK(length(title) BETWEEN 1 AND 160),
 content text NOT NULL CHECK(length(content) BETWEEN 30 AND 100000),
 audience text NOT NULL CHECK(audience IN ('candidate','internal')),
 effective_from timestamptz NOT NULL, effective_until timestamptz,
 request_id text NOT NULL, payload_sha256 text NOT NULL CHECK(length(payload_sha256)=64),
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK(effective_until IS NULL OR effective_until>effective_from),
 UNIQUE(document_id,version), UNIQUE(document_id,request_id)
);
CREATE TABLE IF NOT EXISTS public.company_document_chunks (
 id text PRIMARY KEY, version_id text NOT NULL REFERENCES public.company_document_versions(id) ON DELETE CASCADE,
 ordinal integer NOT NULL CHECK(ordinal>=0), title text NOT NULL,
 content text NOT NULL CHECK(length(content) BETWEEN 1 AND 1400),
 search tsvector GENERATED ALWAYS AS (to_tsvector('english',title||' '||content)) STORED,
 UNIQUE(version_id,ordinal)
);
CREATE TABLE IF NOT EXISTS public.company_document_audit (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 document_id text NOT NULL REFERENCES public.company_documents(id) ON DELETE CASCADE,
 actor_id text NOT NULL, action text NOT NULL CHECK(action IN ('publish_version','archive','restore')),
 details jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS company_documents_scope_idx ON public.company_documents(created_by,tenant_key,created_at DESC);
CREATE INDEX IF NOT EXISTS company_versions_effective_idx ON public.company_document_versions(document_id,effective_from DESC);
CREATE INDEX IF NOT EXISTS company_chunks_search_idx ON public.company_document_chunks USING gin(search);
CREATE INDEX IF NOT EXISTS company_audit_document_idx ON public.company_document_audit(document_id,created_at DESC);
DO $$ DECLARE tab text; BEGIN
 FOREACH tab IN ARRAY ARRAY['company_documents','company_document_versions','company_document_chunks','company_document_audit'] LOOP
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',tab);
  EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC,anon,authenticated,authenticator',tab);
  EXECUTE format('GRANT ALL ON public.%I TO service_role',tab);
  EXECUTE format('DROP POLICY IF EXISTS feature_server ON public.%I',tab);
  EXECUTE format('CREATE POLICY feature_server ON public.%I TO service_role USING(true) WITH CHECK(true)',tab);
 END LOOP;
END $$;
REVOKE ALL ON SEQUENCE public.company_document_audit_id_seq FROM PUBLIC,anon,authenticated,authenticator;
GRANT USAGE,SELECT ON SEQUENCE public.company_document_audit_id_seq TO service_role;

CREATE OR REPLACE FUNCTION public.save_company_document(p_actor text,p_document_id text,p_expected_revision integer,p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE u public.users%ROWTYPE; d public.company_documents%ROWTYPE; v public.company_document_versions%ROWTYPE;
 scope text; next_version integer; starts timestamptz; finishes timestamptz; item jsonb;
BEGIN
 SELECT * INTO u FROM public.users WHERE id::text=p_actor;
 IF NOT FOUND OR u.role::text NOT IN ('admin','recruiter') OR to_jsonb(u)->>'is_active'='false' THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN'; END IF;
 scope:=COALESCE(to_jsonb(u)->>'tenant_id','user:'||p_actor);
 PERFORM pg_advisory_xact_lock(hashtextextended('company-document:'||p_document_id,0));
 SELECT * INTO d FROM public.company_documents WHERE id=p_document_id FOR UPDATE;
 IF FOUND THEN
  IF d.created_by::text<>p_actor OR d.tenant_key<>scope THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN'; END IF;
  SELECT * INTO v FROM public.company_document_versions WHERE document_id=d.id AND request_id=p_payload->>'request_id';
  IF FOUND THEN
   IF v.payload_sha256 IS DISTINCT FROM p_payload->>'payload_sha256' THEN RAISE EXCEPTION 'REPLAY_MISMATCH'; END IF;
   RETURN to_jsonb(v);
  END IF;
  IF d.archived_at IS NOT NULL OR d.policy_key IS DISTINCT FROM p_payload->>'policy_key' THEN RAISE EXCEPTION 'FEATURE_INVALID'; END IF;
 ELSE
  IF p_expected_revision<>0 THEN RAISE EXCEPTION 'VERSION_CONFLICT'; END IF;
  INSERT INTO public.company_documents(id,created_by,tenant_key,title,policy_key)
   VALUES(p_document_id,u.id,scope,p_payload->>'title',p_payload->>'policy_key') RETURNING * INTO d;
 END IF;
 IF d.revision IS DISTINCT FROM p_expected_revision THEN RAISE EXCEPTION 'VERSION_CONFLICT'; END IF;
 starts:=(p_payload->>'effective_from')::timestamptz;
 finishes:=(p_payload->>'effective_until')::timestamptz;
 IF starts IS NULL OR (finishes IS NOT NULL AND finishes<=starts) THEN RAISE EXCEPTION 'FEATURE_INVALID'; END IF;
 IF EXISTS(SELECT 1 FROM public.company_document_versions WHERE document_id=d.id AND
   (effective_from>=starts OR (effective_until IS NOT NULL AND effective_until>starts))) THEN RAISE EXCEPTION 'FEATURE_INVALID_EFFECTIVE_WINDOW'; END IF;
 SELECT COALESCE(max(version),0)+1 INTO next_version FROM public.company_document_versions WHERE document_id=d.id;
 -- Supersession closes an open validity interval; immutable content is never rewritten.
 UPDATE public.company_document_versions SET effective_until=starts WHERE document_id=d.id AND effective_until IS NULL;
 INSERT INTO public.company_document_versions(id,document_id,version,title,content,audience,effective_from,effective_until,request_id,payload_sha256)
  VALUES(p_payload->>'id',d.id,next_version,p_payload->>'title',p_payload->>'content',p_payload->>'audience',starts,finishes,p_payload->>'request_id',p_payload->>'payload_sha256') RETURNING * INTO v;
 IF jsonb_typeof(p_payload->'chunks') IS DISTINCT FROM 'array' OR jsonb_array_length(p_payload->'chunks') NOT BETWEEN 1 AND 100 THEN RAISE EXCEPTION 'FEATURE_INVALID'; END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(p_payload->'chunks') LOOP
  INSERT INTO public.company_document_chunks(id,version_id,ordinal,title,content)
   VALUES(item->>'id',v.id,(item->>'ordinal')::integer,v.title,item->>'content');
 END LOOP;
 UPDATE public.company_documents SET revision=revision+1,title=v.title,updated_at=now() WHERE id=d.id;
 INSERT INTO public.company_document_audit(document_id,actor_id,action,details)
  VALUES(d.id,p_actor,'publish_version',jsonb_build_object('version_id',v.id,'effective_from',starts,'effective_until',finishes));
 RETURN to_jsonb(v);
END $$;

CREATE OR REPLACE FUNCTION public.archive_company_document(p_actor text,p_document_id text,p_expected_revision integer,p_archived boolean)
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE u public.users%ROWTYPE; d public.company_documents%ROWTYPE;
BEGIN
 SELECT * INTO u FROM public.users WHERE id::text=p_actor;
 IF NOT FOUND OR u.role::text NOT IN ('admin','recruiter') OR to_jsonb(u)->>'is_active'='false' THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN'; END IF;
 SELECT * INTO d FROM public.company_documents WHERE id=p_document_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'FEATURE_NOT_FOUND'; END IF;
 IF d.created_by::text<>p_actor OR d.tenant_key<>COALESCE(to_jsonb(u)->>'tenant_id','user:'||p_actor) THEN RAISE EXCEPTION 'FEATURE_FORBIDDEN'; END IF;
 IF d.revision<>p_expected_revision THEN RAISE EXCEPTION 'VERSION_CONFLICT'; END IF;
 UPDATE public.company_documents SET archived_at=CASE WHEN p_archived THEN now() ELSE NULL END,
  revision=revision+1,updated_at=now() WHERE id=d.id RETURNING * INTO d;
 INSERT INTO public.company_document_audit(document_id,actor_id,action) VALUES(d.id,p_actor,CASE WHEN p_archived THEN 'archive' ELSE 'restore' END);
 RETURN to_jsonb(d);
END $$;

CREATE OR REPLACE FUNCTION public.retrieve_company_chunks(p_owner_id text,p_tenant_key text,p_query text,p_effective_at timestamptz,p_candidate_visible boolean)
RETURNS jsonb LANGUAGE sql STABLE SET search_path=public AS $$
 SELECT COALESCE(jsonb_agg(to_jsonb(matches)),'[]'::jsonb) FROM (
  SELECT c.id AS chunk_id,d.id AS document_id,v.id AS version_id,v.version,v.title,d.policy_key,
   v.effective_from,v.effective_until,c.content
  FROM public.company_documents d JOIN public.company_document_versions v ON v.document_id=d.id
   JOIN public.company_document_chunks c ON c.version_id=v.id
  WHERE d.created_by::text=p_owner_id AND d.tenant_key=p_tenant_key AND d.archived_at IS NULL
   AND v.effective_from<=p_effective_at AND (v.effective_until IS NULL OR p_effective_at<v.effective_until)
   AND (NOT p_candidate_visible OR v.audience='candidate')
   AND length(p_query)<=1500 AND c.search@@websearch_to_tsquery('english',p_query)
  ORDER BY ts_rank(c.search,websearch_to_tsquery('english',p_query)) DESC,v.effective_from DESC,c.ordinal,c.id LIMIT 30
 ) matches
$$;
REVOKE ALL ON FUNCTION public.save_company_document(text,text,integer,jsonb),public.archive_company_document(text,text,integer,boolean),public.retrieve_company_chunks(text,text,text,timestamptz,boolean) FROM PUBLIC,anon,authenticated,authenticator;
GRANT EXECUTE ON FUNCTION public.save_company_document(text,text,integer,jsonb),public.archive_company_document(text,text,integer,boolean),public.retrieve_company_chunks(text,text,text,timestamptz,boolean) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
