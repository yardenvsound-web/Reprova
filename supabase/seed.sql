-- Reprova demo data (Milestone 1). Dummy data only.
-- Before running: create the two users in Authentication > Users, then put the
-- operator's email below. The runner_id must match "runner_id" in runner.json.

do $$
declare
  operator_email text := 'yardenvsoundoperator@gmail.com';   -- <-- change to your operator user's email
  runner_id      text := 'runner-mac';
  op   uuid;
  p_web uuid; p_api uuid; p_plugin uuid; p_agent uuid; p_flow uuid;
  r1 uuid;
begin
  select id into op from auth.users where email = operator_email;
  if op is null then
    raise exception 'operator user % not found. Create it in Authentication > Users first.', operator_email;
  end if;

  -- five demo projects
  insert into public.projects (owner_id, name, status, client, product_type, parts, targets, test_set)
  values
    (op, 'Demo Booking Web', 'active',
     '{"name":"Demo Hospitality Ltd.","ai_enabled":true,"retention_days":30}', 'web', '["gui","e2e"]',
     '[{"id":"t-web","kind":"web","access_mode":"black_box","location":"http://localhost:8765","environment":"staging","is_production":false,"production_approved":false,"secret_refs":["demo_web_login"]}]',
     '["smoke","functional","negative"]')
  returning id into p_web;

  insert into public.projects (owner_id, name, status, client, product_type, parts, targets, test_set)
  values
    (op, 'Demo Customer API', 'active',
     '{"name":"Demo CRM Inc.","ai_enabled":true,"retention_days":30}', 'api', '["api","auth"]',
     '[{"id":"t-api","kind":"api","access_mode":"black_box","location":"http://localhost:8766","environment":"staging","is_production":false,"production_approved":false,"secret_refs":["demo_api_key"]}]',
     '["smoke","functional","negative","boundary"]')
  returning id into p_api;

  insert into public.projects (owner_id, name, status, client, product_type, parts, targets, test_set)
  values
    (op, 'Demo Plugin', 'setup',
     '{"name":"Demo Audio Ltd.","ai_enabled":true,"retention_days":30}', 'desktop_plugin', '["gui","engine","install"]',
     '[{"id":"t-pkg","kind":"installer","access_mode":"black_box","location":"fixtures/demo-plugin/","environment":"local_mac","is_production":false,"production_approved":false,"secret_refs":[]}]',
     '["smoke","install","functional","boundary","negative"]')
  returning id into p_plugin;

  insert into public.projects (owner_id, name, status, client, product_type, parts, targets)
  values
    (op, 'Demo Support Agent', 'on_hold',
     '{"name":"Demo Retail","ai_enabled":false,"retention_days":30}', 'ai_agent', '["ai"]', '[]')
  returning id into p_agent;

  insert into public.projects (owner_id, name, status, client, product_type, parts, targets)
  values
    (op, 'Demo Lead Workflow', 'closed',
     '{"name":"Demo Agency","ai_enabled":true,"retention_days":30}', 'workflow', '["workflow"]', '[]')
  returning id into p_flow;

  -- the runner's heartbeat row (the runner can only update it, not create it)
  insert into public.runs (owner_id, project_id, kind, status, claimed_by)
  values (op, null, 'runner_heartbeat', 'running', runner_id)
  on conflict do nothing;

  -- five demo runs
  insert into public.runs (owner_id, project_id, kind, status, summary, started_at, finished_at)
  values (op, p_web, 'test_run', 'done', '{"passed":18,"failed":1,"error":0,"blocked":0,"skipped":0,"flaky":0}',
          now() - interval '2 days', now() - interval '2 days' + interval '6 minutes')
  returning id into r1;

  insert into public.runs (owner_id, project_id, kind, status, summary, error, started_at, finished_at)
  values
    (op, p_web, 'test_run', 'error', '{"passed":4,"failed":0,"error":3,"blocked":0,"skipped":0,"flaky":0}',
     'demo: browser crashed', now() - interval '1 day', now() - interval '1 day' + interval '2 minutes'),
    (op, p_api, 'test_run', 'done', '{"passed":24,"failed":3,"error":0,"blocked":0,"skipped":0,"flaky":0}',
     null, now() - interval '3 days', now() - interval '3 days' + interval '4 minutes'),
    (op, p_plugin, 'test_run', 'done', '{"passed":51,"failed":2,"error":0,"blocked":0,"skipped":0,"flaky":1}',
     null, now() - interval '5 hours', now() - interval '5 hours' + interval '9 minutes');

  -- an empty job for the Walking Skeleton: the runner should move it to done
  insert into public.runs (owner_id, project_id, kind, status)
  values (op, p_plugin, 'test_run', 'queued');

  -- five demo findings
  insert into public.findings (owner_id, project_id, run_id, test_case_id, target_id, fingerprint, title,
                               severity, priority, triage_status, ai_verdict, expected, actual)
  values
    (op, p_web, r1, 'WEB-03', 't-web', 'demo-fp-web-03', 'Double booking on the same night', 'high', 'p1', 'investigate',
     '{"verdict":"suspected","confidence":0.55}', 'Second booking is refused', 'Both bookings are accepted'),
    (op, p_web, r1, 'WEB-09', 't-web', 'demo-fp-web-09', 'Title missing on reload', 'low', 'p4', 'rejected',
     '{"verdict":"false_positive","confidence":0.8}', 'Page title is shown', 'Title appears after 300 ms'),
    (op, p_api, null, 'API-07', 't-api', 'demo-fp-api-07', 'Viewer can DELETE a customer', 'critical', 'p1', 'pending',
     '{"verdict":"confirmed","confidence":0.9}', '403 and no change', '204 and the customer is deleted'),
    (op, p_api, null, 'API-02', 't-api', 'demo-fp-api-02', 'Malformed JSON returns 500', 'medium', 'p3', 'needs_manual_triage',
     '{}', '400 with an error message', '500'),
    (op, p_plugin, null, 'ENG-04', 't-pkg', 'demo-fp-eng-04', 'Typo "Paino" goes to UNSORTED', 'high', 'p2', 'pending',
     '{"verdict":"confirmed","confidence":0.86}', '"Paino L" goes to KEYS', '"Paino L" goes to UNSORTED');
end;
$$;
