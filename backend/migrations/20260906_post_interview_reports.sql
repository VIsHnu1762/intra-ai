-- Post-interview state and immutable report publication. No live voice changes.
BEGIN;
ALTER TABLE public.scheduled_interviews
  ADD COLUMN IF NOT EXISTS report_generation jsonb NOT NULL DEFAULT '{"status":"not_started"}'::jsonb,
  ADD COLUMN IF NOT EXISTS report_source jsonb,
  ADD COLUMN IF NOT EXISTS report_draft jsonb;
ALTER TABLE public.reports
  ADD COLUMN IF NOT EXISTS candidate_rating numeric CHECK (candidate_rating BETWEEN 1 AND 5),
  ADD COLUMN IF NOT EXISTS candidate_feedback jsonb,
  ADD COLUMN IF NOT EXISTS analysis jsonb;

-- One predicate for both publication and read/retry readiness. JSON null,
-- scalar feedback, empty strings, and partial legacy rows are not final output.
CREATE OR REPLACE FUNCTION public.interview_report_output_complete(
  p_score numeric, p_rating numeric, p_feedback jsonb, p_analysis jsonb
) RETURNS boolean LANGUAGE plpgsql IMMUTABLE SET search_path = public AS $$
DECLARE line jsonb;
BEGIN
  IF p_score IS NULL OR p_score < 0 OR p_score > 100
     OR p_rating IS NULL OR p_rating < 1 OR p_rating > 5
     OR abs(p_rating - round(1 + p_score / 25, 1)) > 0.0001 THEN RETURN false; END IF;
  IF jsonb_typeof(p_feedback) IS DISTINCT FROM 'array' THEN RETURN false; END IF;
  IF jsonb_array_length(p_feedback) <> 3 THEN RETURN false; END IF;
  FOR line IN SELECT value FROM jsonb_array_elements(p_feedback) LOOP
    IF jsonb_typeof(line) IS DISTINCT FROM 'string' OR (line #>> '{}') !~ '[^[:space:]]' THEN RETURN false; END IF;
  END LOOP;
  RETURN jsonb_typeof(p_analysis) IS NOT DISTINCT FROM 'object' AND p_analysis <> '{}'::jsonb;
END $$;

CREATE OR REPLACE FUNCTION public.claim_interview_report(p_interview_id text, p_attempt_id text, p_source jsonb)
RETURNS jsonb LANGUAGE plpgsql SET search_path = public AS $$
DECLARE meeting public.scheduled_interviews%ROWTYPE; saved public.reports%ROWTYPE; result jsonb; claimed_at timestamptz;
BEGIN
  IF p_attempt_id IS NULL OR btrim(p_attempt_id) = '' OR length(p_attempt_id) > 200 THEN
    RAISE EXCEPTION 'REPORT_ATTEMPT_INVALID';
  END IF;
  IF p_source IS NOT NULL AND jsonb_typeof(p_source) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'REPORT_SOURCE_INVALID';
  END IF;
  SELECT * INTO meeting FROM public.scheduled_interviews WHERE id::text = p_interview_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'INTERVIEW_NOT_FOUND'; END IF;
  IF meeting.status <> 'completed' THEN RETURN jsonb_build_object('status','not_completed'); END IF;
  SELECT * INTO saved FROM public.reports WHERE interview_id::text = p_interview_id;
  IF FOUND AND public.interview_report_output_complete(saved.overall_score,saved.candidate_rating,saved.candidate_feedback,saved.analysis) THEN
    RETURN jsonb_build_object('status','ready','report_id',saved.id);
  END IF;
  BEGIN
    claimed_at := (meeting.report_generation->>'started_at')::timestamptz;
  EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN
    claimed_at := NULL;
  END;
  IF meeting.report_generation->>'status' = 'generating'
     AND NULLIF(btrim(meeting.report_generation->>'attempt_id'),'') IS NOT NULL
     AND claimed_at > now() - interval '5 minutes' THEN
    RETURN meeting.report_generation;
  END IF;
  result := jsonb_build_object('status','generating','attempt_id',p_attempt_id,'started_at',now());
  UPDATE public.scheduled_interviews SET report_generation=result,
    report_source=COALESCE(report_source,p_source) WHERE id=meeting.id;
  RETURN result;
END $$;

CREATE OR REPLACE FUNCTION public.finish_interview_report(p_interview_id text, p_attempt_id text, p_report jsonb)
RETURNS jsonb LANGUAGE plpgsql SET search_path = public AS $$
DECLARE meeting public.scheduled_interviews%ROWTYPE; payload public.reports%ROWTYPE; saved public.reports%ROWTYPE;
BEGIN
  SELECT * INTO meeting FROM public.scheduled_interviews WHERE id::text=p_interview_id FOR UPDATE;
  IF NOT FOUND OR meeting.status <> 'completed' OR p_attempt_id IS NULL OR btrim(p_attempt_id) = ''
     OR meeting.report_generation->>'attempt_id' IS DISTINCT FROM p_attempt_id THEN
    RAISE EXCEPTION 'REPORT_ATTEMPT_SUPERSEDED';
  END IF;
  SELECT * INTO saved FROM public.reports WHERE interview_id=meeting.id;
  IF meeting.report_generation->>'status' = 'ready' AND FOUND
     AND public.interview_report_output_complete(saved.overall_score,saved.candidate_rating,saved.candidate_feedback,saved.analysis) THEN
    RETURN to_jsonb(saved);
  END IF;
  IF meeting.report_generation->>'status' IS DISTINCT FROM 'generating' THEN
    RAISE EXCEPTION 'REPORT_ATTEMPT_SUPERSEDED';
  END IF;
  IF jsonb_typeof(p_report) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'REPORT_INCOMPLETE'; END IF;
  SELECT * INTO payload FROM jsonb_populate_record(NULL::public.reports,p_report);
  IF payload.interview_id::text IS DISTINCT FROM p_interview_id OR payload.id IS NULL OR btrim(payload.id::text) = ''
     OR payload.created_at IS NULL OR payload.recommendation IS NULL
     OR NOT public.interview_report_output_complete(payload.overall_score,payload.candidate_rating,payload.candidate_feedback,payload.analysis) THEN
    RAISE EXCEPTION 'REPORT_INCOMPLETE';
  END IF;
  INSERT INTO public.reports(id,interview_id,round_assessments,overall_score,recommendation,strengths,improvements,
      salary_recommendation,proctoring_summary,pdf_url,created_at,candidate_rating,candidate_feedback,analysis)
    VALUES(payload.id,payload.interview_id,payload.round_assessments,payload.overall_score,payload.recommendation,
      payload.strengths,payload.improvements,payload.salary_recommendation,payload.proctoring_summary,payload.pdf_url,
      payload.created_at,payload.candidate_rating,payload.candidate_feedback,payload.analysis)
    ON CONFLICT(interview_id) DO UPDATE SET round_assessments=EXCLUDED.round_assessments,
      overall_score=EXCLUDED.overall_score,recommendation=EXCLUDED.recommendation,strengths=EXCLUDED.strengths,
      improvements=EXCLUDED.improvements,candidate_rating=EXCLUDED.candidate_rating,
      candidate_feedback=EXCLUDED.candidate_feedback,analysis=EXCLUDED.analysis
    WHERE NOT public.interview_report_output_complete(public.reports.overall_score,public.reports.candidate_rating,
      public.reports.candidate_feedback,public.reports.analysis);
  SELECT * INTO saved FROM public.reports WHERE interview_id=meeting.id;
  IF NOT FOUND OR NOT public.interview_report_output_complete(saved.overall_score,saved.candidate_rating,saved.candidate_feedback,saved.analysis) THEN
    RAISE EXCEPTION 'REPORT_INCOMPLETE';
  END IF;
  UPDATE public.scheduled_interviews SET report_generation=jsonb_build_object('status','ready','report_id',saved.id,'attempt_id',p_attempt_id,'finished_at',now()),
      report_draft=NULL WHERE id=meeting.id;
  RETURN to_jsonb(saved);
END $$;
REVOKE ALL ON FUNCTION public.interview_report_output_complete(numeric,numeric,jsonb,jsonb) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.claim_interview_report(text,text,jsonb) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.finish_interview_report(text,text,jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.interview_report_output_complete(numeric,numeric,jsonb,jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_interview_report(text,text,jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION public.finish_interview_report(text,text,jsonb) TO service_role;
NOTIFY pgrst, 'reload schema';
COMMIT;
