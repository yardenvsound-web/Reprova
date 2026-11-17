# Reprova

Operator console and local runner for a managed QA service.
Spec documents (PRD, ARCHITECTURE, DESIGN, MILESTONES) live outside this public repo.

**Current state: Milestone 1, Walking Skeleton.** The browser, Supabase, the local runner
and n8n are connected end to end. There are no product features yet.

> This repo is public. Never commit keys, passwords, client names, URLs or files.
> Secrets live only in the macOS Keychain and in n8n Credentials.

## Layout

```
index.html, login.html     GitHub Pages site (no build step)
assets/  i18n/             CSS, JS modules, EN/HE strings
supabase/                  schema.sql, policies.sql, seed.sql
runner/                    Python runner (runs on the operator's Mac)
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
cd runner && pytest -q
```
