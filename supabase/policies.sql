-- Reprova row-level security (Milestone 1)
-- Two roles, set by hand in the Supabase dashboard on each user's app_metadata:
--   operator: {"role": "admin"}
--   runner:   {"role": "runner"}
-- Anonymous visitors get nothing: there is no anon policy on any table.

create or replace function public.app_role()
returns text
language sql
stable
set search_path = ''
as $$
  select coalesce(auth.jwt() -> 'app_metadata' ->> 'role', '');
$$;

alter table public.projects enable row level security;
alter table public.runs     enable row level security;
alter table public.findings enable row level security;

-- ---------------------------------------------------------------- projects
drop policy if exists projects_admin_all   on public.projects;
drop policy if exists projects_runner_read on public.projects;

create policy projects_admin_all on public.projects
  for all to authenticated
  using      ((select public.app_role()) = 'admin' and owner_id = (select auth.uid()))
  with check ((select public.app_role()) = 'admin' and owner_id = (select auth.uid()));

create policy projects_runner_read on public.projects
  for select to authenticated
  using ((select public.app_role()) = 'runner');

-- ---------------------------------------------------------------- runs
drop policy if exists runs_admin_all     on public.runs;
drop policy if exists runs_runner_read   on public.runs;
drop policy if exists runs_runner_update on public.runs;

create policy runs_admin_all on public.runs
  for all to authenticated
  using      ((select public.app_role()) = 'admin' and owner_id = (select auth.uid()))
  with check ((select public.app_role()) = 'admin' and owner_id = (select auth.uid()));

create policy runs_runner_read on public.runs
  for select to authenticated
  using ((select public.app_role()) = 'runner');

-- The runner may only touch jobs that are in flight, and its own heartbeat row.
-- It may move a job to running / done / error / cancelled, never back to queued.
create policy runs_runner_update on public.runs
  for update to authenticated
  using (
    (select public.app_role()) = 'runner'
    and (status in ('queued', 'running', 'cancel_requested') or kind = 'runner_heartbeat')
  )
  with check (
    (select public.app_role()) = 'runner'
    and (status in ('running', 'cancel_requested', 'done', 'error', 'cancelled') or kind = 'runner_heartbeat')
  );

-- ---------------------------------------------------------------- findings
drop policy if exists findings_admin_all     on public.findings;
drop policy if exists findings_runner_read   on public.findings;
drop policy if exists findings_runner_insert on public.findings;
drop policy if exists findings_runner_update on public.findings;

create policy findings_admin_all on public.findings
  for all to authenticated
  using      ((select public.app_role()) = 'admin' and owner_id = (select auth.uid()))
  with check ((select public.app_role()) = 'admin' and owner_id = (select auth.uid()));

create policy findings_runner_read on public.findings
  for select to authenticated
  using ((select public.app_role()) = 'runner');

create policy findings_runner_insert on public.findings
  for insert to authenticated
  with check ((select public.app_role()) = 'runner');

create policy findings_runner_update on public.findings
  for update to authenticated
  using      ((select public.app_role()) = 'runner')
  with check ((select public.app_role()) = 'runner');

-- The runner may change only ai_verdict, repro and occurrences on a finding.
-- RLS is row-level, so the column limit is enforced with a trigger.
create or replace function public.findings_runner_columns_guard()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if public.app_role() = 'runner' then
    if (to_jsonb(new) - array['ai_verdict', 'repro', 'occurrences', 'updated_at'])
       is distinct from
       (to_jsonb(old) - array['ai_verdict', 'repro', 'occurrences', 'updated_at']) then
      raise exception 'runner may only update ai_verdict, repro and occurrences';
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists findings_runner_columns on public.findings;
create trigger findings_runner_columns before update on public.findings
  for each row execute function public.findings_runner_columns_guard();

-- ---------------------------------------------------------------- storage
drop policy if exists storage_admin_read    on storage.objects;
drop policy if exists storage_runner_read   on storage.objects;
drop policy if exists storage_runner_write  on storage.objects;
drop policy if exists storage_runner_update on storage.objects;
drop policy if exists storage_runner_delete on storage.objects;

create policy storage_admin_read on storage.objects
  for select to authenticated
  using (bucket_id in ('evidence', 'reports') and (select public.app_role()) = 'admin');

create policy storage_runner_read on storage.objects
  for select to authenticated
  using (bucket_id in ('evidence', 'reports') and (select public.app_role()) = 'runner');

create policy storage_runner_write on storage.objects
  for insert to authenticated
  with check (bucket_id in ('evidence', 'reports') and (select public.app_role()) = 'runner');

create policy storage_runner_update on storage.objects
  for update to authenticated
  using (bucket_id in ('evidence', 'reports') and (select public.app_role()) = 'runner');

-- Retention cleanup (Milestone 6) deletes old evidence.
create policy storage_runner_delete on storage.objects
  for delete to authenticated
  using (bucket_id = 'evidence' and (select public.app_role()) = 'runner');

-- anon gets nothing on these tables
revoke all on public.projects, public.runs, public.findings from anon;

-- ---------------------------------------------------------------- intake bucket (F49): operator only
drop policy if exists storage_admin_intake_read   on storage.objects;
drop policy if exists storage_admin_intake_write  on storage.objects;
drop policy if exists storage_admin_intake_update on storage.objects;
drop policy if exists storage_admin_intake_delete on storage.objects;
create policy storage_admin_intake_read on storage.objects
  for select to authenticated
  using (bucket_id = 'intake' and (select public.app_role()) = 'admin');
create policy storage_admin_intake_write on storage.objects
  for insert to authenticated
  with check (bucket_id = 'intake' and (select public.app_role()) = 'admin');
create policy storage_admin_intake_update on storage.objects
  for update to authenticated
  using (bucket_id = 'intake' and (select public.app_role()) = 'admin');
create policy storage_admin_intake_delete on storage.objects
  for delete to authenticated
  using (bucket_id = 'intake' and (select public.app_role()) = 'admin');
