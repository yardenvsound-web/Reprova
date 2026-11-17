# Reprova: instructions for Claude Code

Reprova is a managed-QA suite: an operator console (static site), a local Python runner on the
operator's Mac, Supabase, and n8n. The operator approves every finding and report.

## Where the spec lives
The spec is **not** in this repo (this repo is public). It is in the sibling folder
`../Reprova/` on the operator's Mac. Start Claude Code with:

```bash
cd ~/Documents/Claude/My\ Projects/reprova-app
claude --add-dir ../Reprova
```

Source of truth, in this order: `../Reprova/product-10-definitions.md`, `../Reprova/MVP.md`,
then `PRD.md`, `tech-stack.md`, `ARCHITECTURE.md`, `DESIGN.md` (with `wireframes.png`,
`mockups.png`, `style-guide.png`), `MILESTONES.md`, and `course-stack.md`.
If code and spec disagree, stop and ask. Never invent a requirement that is not in the spec.

## Status
- Milestone 1 (Walking Skeleton): **done** on 17.11.2026, all Definition of Done checks passed. Login, Dashboard,
  Supabase schema/RLS/seed, runner queue + heartbeat, n8n triage webhook all verified end to end.
- Milestone 2 (Web and API test plan end to end): **built 17.11.2026, waiting for the operator's
  check and approval.** Steps and the DoD checklist are in `README.md`.
- Decisions taken with the operator for Milestone 2 (not spelled out in the spec):
  1. The runner reports which client `secret_refs` exist in the Keychain (names only) on its
     heartbeat row, in `runs.output`; Readiness reads it. Runner offline means "not checked".
  2. A minimal re-run of failed cases (`budget.repro_attempts`) decides Flaky now. AI triage,
     fingerprints and findings stay in Milestone 4.
  3. Test case steps are edited by the operator in plan.html (PoC step format). Demo plans: `fixtures/demo_plans.json`.
  4. SQL changes are files the operator runs by hand (`supabase/m2.sql`).

## Rules
- **Stop at the end of every Milestone** and wait for the operator's explicit approval.
- Course stack only (`../Reprova/course-stack.md`). Approved exceptions: the local Python runner,
  and client credentials in the macOS Keychain.
- **No secrets in this repo, ever.** The browser holds only the Supabase anon key. The Gemini key
  and webhook secret live in n8n Credentials; the runner password, webhook secret and client
  credentials live in the Keychain (service `reprova`). No client names, URLs or files in the repo.
- Three Supabase tables only: `projects`, `runs`, `findings` (lists in jsonb columns).
  Keep `supabase/schema.sql` and `policies.sql` in sync with what is applied.
- The AI never closes a finding. Confirmed requires a failing repro on every attempt; an engine
  problem is `error` (execution error), never a product bug.
- UI is English by default with Hebrew (RTL) as an option; every status is color + icon + word.

## Live services
- Supabase project `reprova` (ref `wnqxqtbmadoetwwyceun`, eu-central-1). Users:
  operator (`app_metadata.role = admin`) and runner (`role = runner`).
- n8n Cloud workflow "Reprova · triage (walking skeleton)", webhook path `reprova-triage`,
  Header Auth `X-QA-Secret`.
- Site: GitHub Pages from `main` / root.

## Run and test
```bash
cd runner && source .venv/bin/activate
pytest -q                          # runner unit tests
python -m reprova_runner check     # sign in, heartbeat, ping n8n
python -m reprova_runner run       # keep the runner going
```
