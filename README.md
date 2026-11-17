# Reprova

Operator console and local runner for a managed QA service.
Spec documents (PRD, ARCHITECTURE, DESIGN, MILESTONES) live outside this public repo.

**Current state: Milestone 2, Web and API test plan end to end** (built, waiting for the operator's
check). Project Setup with Intake and Readiness, the methodology catalog, Test Plan & Run, the full
queue (cancel, timeout, time budget), Keychain credential refs, secret/PII redaction, the Web
(Playwright) and API (Pytest + httpx) adapters, and the first Dashboard.

> This repo is public. Never commit keys, passwords, client names, URLs or files.
> Secrets live only in the macOS Keychain and in n8n Credentials.

## Layout

```
index.html                 Dashboard
project.html               Projects list and Project Setup (Targets, Intake, Readiness)
plan.html                  Test Plan & Run
login.html                 sign in
assets/  i18n/             CSS, JS modules, EN/HE strings
catalog/methodologies.json methodology catalog (F11)
supabase/                  schema.sql, policies.sql, seed.sql, m2.sql (Milestone 2 migration)
runner/                    Python runner (runs on the operator's Mac)
fixtures/                  local demo targets with seeded defects, and the demo Test Plans
tests/web/                 Node tests for Intake and Readiness
n8n/                       exported workflows, without credentials
```

## Setup (one time)

### 1. Supabase
Done: project `reprova` (eu-central-1) exists, `schema.sql` and `policies.sql` are applied.
1. **Authentication > Users > Add user**, with **Auto Confirm User** checked: create `operator@…` and `runner@…`.
2. **Authentication > Sign In / Providers > Email**: turn off "Allow new users to sign up".
3. Set the roles and load the demo data (or ask Claude to do it with the two emails):
   ```sql
   update auth.users set raw_app_meta_data = raw_app_meta_data || '{"role":"admin"}'  where email = 'operator@…';
   update auth.users set raw_app_meta_data = raw_app_meta_data || '{"role":"runner"}' where email = 'runner@…';
   ```
   then run `supabase/seed.sql` (edit the operator email at its top first).

### 2. Website
1. `assets/js/config.js` already holds the project URL and the anon key (public by design).
2. Push to `main`, then **Settings > Pages > Deploy from branch > main / root**.
3. Open `https://<you>.github.io/<repo>/login.html` and sign in as the operator.

### 3. n8n (cloud instance)
The workflow **Reprova · triage (walking skeleton)** already exists in the connected n8n instance
(webhook path `reprova-triage`).
1. **Credentials > New > Header Auth**, name `Reprova webhook secret`,
   header name `X-QA-Secret`, value: a long random string.
2. Open the workflow, on the **Webhook triage** node set Authentication = **Header Auth** and pick that credential.
3. **Publish / Activate** the workflow.

### 4. Runner (on the Mac)
```bash
cd runner
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m reprova_runner init-config          # writes ~/Library/Application Support/Reprova/runner.json
# edit runner.json: runner_email (URL, anon key and n8n URL are prefilled)
python -m reprova_runner set-secret runner-password
python -m reprova_runner set-secret webhook-secret   # same value as the n8n credential
python -m reprova_runner check                # sign in, heartbeat, ping n8n
python -m reprova_runner run                  # keep it running
```

## Milestone 2 setup (once)
1. **Supabase:** run `supabase/m2.sql` in the SQL editor. It adds the Production-approval check and
   gives *Demo Booking Web* and *Demo Customer API* draft Test Plans (it resets them if run again).
2. **Runner:**
   ```bash
   cd runner && source .venv/bin/activate
   pip install -r requirements.txt && python -m playwright install chromium
   ```
3. **Demo credentials** (dummy values, any non-empty text). Copy each project's id from the address bar
   of its Project Setup page (`project.html?id=…`):
   ```bash
   python -m reprova_runner set-secret <web_project_id>/demo_web_login
   python -m reprova_runner set-secret <api_project_id>/demo_api_key
   python -m reprova_runner check     # lists every credential ref as found or MISSING
   ```
   The runner reports which refs exist (names only) on its heartbeat every 30 s, and Readiness shows them.
4. **Demo targets:** in a second terminal, `python fixtures/demo_targets.py` (Web on :8765, API on :8766).

## Milestone 2 walkthrough
1. Projects › *Demo Booking Web*: Readiness is **Not ready**. Upload a requirements document and a written
   approval in Intake (any dummy PDF), mark the test link and test users Received, and Save.
2. Go to Test Plan: approve the plan, then **Run**. Progress, events and results update every few seconds.
3. Same for *Demo Customer API*. Together the two runs show all six states.

| Case | Expected state | Why |
|---|---|---|
| WEB-01, API-01, API-03, API-04 | Passed | |
| WEB-02, API-02 | Failed | seeded bug: 0 nights is accepted |
| WEB-04 | Execution error | the step waits for an element that does not exist: a test-definition problem, not a product bug |
| API-05 | Flaky | fails every other call; the runner re-runs a failed case `repro_attempts` times |
| WEB-05, API-06 | Skipped | not selected in the plan |
| any case, demo targets stopped | Blocked | the environment is down, which is not a failure |

## Milestone 2 Definition of Done
- [ ] Run cannot be pressed while Readiness is incomplete or the plan is not approved.
- [ ] Without a requirements document and a written approval marked Received, Readiness shows Not ready.
- [ ] Adding a White Box target adds a read-only repo request to Intake; Copy request copies only the missing items.
- [ ] Deleting a `secret_ref` from the Keychain shows Not ready in the Keychain item (within ~30 s, with the runner online).
- [ ] The Web run and the API run finish, and all six states show as word and icon.
- [ ] A stopped demo environment returns `blocked`, not `failed`.
- [ ] Cancel during a run keeps what was completed and marks the run `cancelled`.
- [ ] A dummy password printed in a test log does not appear in the evidence in Storage (WEB-03 log shows `[REDACTED:demo_web_login]`).
- [ ] A Production target is not saved without the approval tick (also refused by the database).

Automated checks: `cd runner && pytest -q` (queue, executor, redaction, and both adapters against the
demo targets) and `npm test` (Intake and Readiness).

## Milestone 1 Definition of Done
- [ ] Sign-in as `operator` works; without a session `index.html` redirects to `login.html`.
- [ ] Reading `projects` with the anon key and no session returns no data
      (`curl "$URL/rest/v1/projects?select=id" -H "apikey: $ANON"` is refused with "permission denied": anon has no access at all).
- [ ] With the runner running the Dashboard shows "Runner online"; about 2 minutes after
      stopping it, "Runner offline".
- [ ] The seeded `queued` job moves to `done`; a job is claimed only once, even with two runners
      (`pytest runner/tests`).
- [ ] Searching the repo for key, token, password and secret finds no secret value.

## Tests
```bash
cd runner && pytest -q     # runner (about 45 s: the adapter tests drive Chromium and pytest)
npm test                   # console logic (Node 20+)
```
