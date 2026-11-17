-- Reprova schema (Milestones 1 and 2)
-- Run in the Supabase SQL editor, in this order: schema.sql, policies.sql, seed.sql
-- Three tables only (course-stack rule). Lists that belong to a row live in jsonb columns.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------- helpers
create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

-- ---------------------------------------------------------------- projects
create table if not exists public.projects (
  id               uuid primary key default gen_random_uuid(),
  owner_id         uuid not null references auth.users(id) on delete cascade,
  name             text not null,
  status           text not null default 'setup'
                   check (status in ('setup', 'active', 'on_hold', 'closed')),
  client           jsonb not null default '{}'::jsonb,     -- {name, contacts[], ai_enabled, retention_days}
  product_type     text not null,                          -- web / api / desktop_plugin / ai_agent / workflow ...
  parts            jsonb not null default '[]'::jsonb,     -- ["gui","engine","install"]
  targets          jsonb not null default '[]'::jsonb,     -- [{id, kind, access_mode, location, environment, is_production, production_approved, secret_refs[]}]
  report_language  text not null default 'en' check (report_language in ('en', 'he')),
  test_set         jsonb not null default '[]'::jsonb,     -- catalog ids
  test_plan        jsonb not null default '{"version":0,"status":"draft","cases":[]}'::jsonb,
  budget           jsonb not null default '{"max_minutes":60,"max_ai_usd":1,"repro_attempts":3}'::jsonb,
  reports          jsonb not null default '[]'::jsonb,
  intake           jsonb not null default '[]'::jsonb,     -- F49: what we need from the client [{key, status, file_path, ...}]
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  -- F07: a Production target is never stored without an explicit approval tick
  constraint projects_production_needs_approval check (
    not jsonb_path_exists(targets, '$[*] ? (@.is_production == true && !(exists(@.production_approved ? (@ == true))))')
  )
);

-- ---------------------------------------------------------------- runs (also the job queue)
create table if not exists public.runs (
  id              uuid primary key default gen_random_uuid(),
  owner_id        uuid not null references auth.users(id) on delete cascade,
  project_id      uuid references public.projects(id) on delete cascade,  -- null only for runner_heartbeat
  kind            text not null
                  check (kind in ('test_run', 'retest', 'report_pdf', 'runner_heartbeat')),
  status          text not null default 'queued'
                  check (status in ('queued', 'running', 'cancel_requested', 'done', 'error', 'cancelled')),
  plan_version    int,
  build           jsonb not null default '{}'::jsonb,      -- {version, file_hash, commit}
  retest_of       uuid references public.runs(id) on delete set null,
  payload         jsonb not null default '{}'::jsonb,      -- test_run: {total}; report_pdf: {report_version}
  claimed_by      text,
  claimed_at      timestamptz,
  heartbeat_at    timestamptz,
  started_at      timestamptz,
  finished_at     timestamptz,
  summary         jsonb not null default '{}'::jsonb,      -- {passed, failed, error, blocked, skipped, flaky}
  results         jsonb not null default '[]'::jsonb,      -- NormalizedTestResult[] (+ attempts[])
  evidence_paths  jsonb not null default '[]'::jsonb,
  output          jsonb not null default '{}'::jsonb,      -- report_pdf: {pdf_path}; runner_heartbeat: {secret_refs, checked_at}
  error           text,
  ai_cost_usd     numeric(10, 4) not null default 0,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint runs_project_required check (kind = 'runner_heartbeat' or project_id is not null)
);

create index if not exists runs_queue_idx on public.runs (status, created_at) where kind <> 'runner_heartbeat';
create unique index if not exists runs_one_heartbeat_per_runner on public.runs (claimed_by) where kind = 'runner_heartbeat';
create index if not exists runs_owner_idx on public.runs (owner_id);
create index if not exists runs_project_idx on public.runs (project_id);
create index if not exists runs_retest_idx on public.runs (retest_of);

-- ---------------------------------------------------------------- findings
create table if not exists public.findings (
  id             uuid primary key default gen_random_uuid(),
  owner_id       uuid not null references auth.users(id) on delete cascade,
  project_id     uuid not null references public.projects(id) on delete cascade,
  run_id         uuid references public.runs(id) on delete set null,
  test_case_id   text not null,
  target_id      text,
  fingerprint    text not null,
  title          text not null,
  severity       text check (severity in ('critical', 'high', 'medium', 'low')),
  priority       text check (priority in ('p1', 'p2', 'p3', 'p4')),
  triage_status  text not null default 'pending'
                 check (triage_status in ('pending', 'needs_manual_triage', 'verified', 'rejected',
                                          'investigate', 'duplicate', 'deferred', 'fixed')),
  ai_verdict     jsonb not null default '{}'::jsonb,
  repro          jsonb not null default '{}'::jsonb,
  expected       text,
  actual         text,
  cluster        text,
  duplicate_of   uuid references public.findings(id) on delete set null,
  occurrences    jsonb not null default '[]'::jsonb,
  retest_links   jsonb not null default '[]'::jsonb,
  audit_trail    jsonb not null default '[]'::jsonb,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint findings_fingerprint_unique unique (project_id, fingerprint)
);

create index if not exists projects_owner_idx on public.projects (owner_id);
create index if not exists findings_owner_idx on public.findings (owner_id);
create index if not exists findings_run_idx on public.findings (run_id);
create index if not exists findings_dup_idx on public.findings (duplicate_of);

-- ---------------------------------------------------------------- updated_at triggers
drop trigger if exists projects_updated_at on public.projects;
create trigger projects_updated_at before update on public.projects
  for each row execute function public.set_updated_at();

drop trigger if exists runs_updated_at on public.runs;
create trigger runs_updated_at before update on public.runs
  for each row execute function public.set_updated_at();

drop trigger if exists findings_updated_at on public.findings;
create trigger findings_updated_at before update on public.findings
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------- storage buckets (private)
insert into storage.buckets (id, name, public)
values ('evidence', 'evidence', false), ('reports', 'reports', false), ('intake', 'intake', false)
on conflict (id) do nothing;
