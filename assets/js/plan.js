// F08 Test Plan & Run: edit and approve the plan, Run and Cancel, progress, events and results.
import { supabase, boot, loadRunner, pill, el, fmtTime, toast, params, t } from './ui.js';
import { readiness, allReady, ADAPTER_FOR_KIND } from './readiness.js';

const $ = (id) => document.getElementById(id);
const STATES = ['passed', 'failed', 'error', 'blocked', 'skipped', 'flaky'];
const ACTIVE = ['queued', 'running', 'cancel_requested'];
const STEP_EXAMPLE = {
  web_playwright: [{ action: 'goto', path: '/' }, { action: 'assert_text', selector: 'h1', contains: '' }],
  api_pytest: [{ action: 'request', method: 'GET', path: '/api/health', expected_status: 200 }],
};

let session;
let project;
let catalog = [];
let runs = [];
let viewRunId = params.get('run');
let runner = { state: 'unknown', keychain: null };
let editing = -1;
let timer;

const plan = () => project.test_plan || { version: 0, status: 'draft', cases: [] };
const activeRun = () => runs.find((r) => ACTIVE.includes(r.status));

// ---------------------------------------------------------------- data
async function loadProject() {
  const { data, error } = await supabase.from('projects').select('*').eq('id', params.get('id')).maybeSingle();
  if (error || !data) throw new Error(t('setup.notFound'));
  project = data;
}

async function loadRuns() {
  const { data } = await supabase.from('runs')
    .select('id, kind, status, plan_version, payload, claimed_by, claimed_at, started_at, finished_at, created_at, summary, results, error')
    .eq('project_id', project.id).neq('kind', 'runner_heartbeat')
    .order('created_at', { ascending: false }).limit(15);
  runs = data || [];
  if (!viewRunId || !runs.some((r) => r.id === viewRunId)) viewRunId = runs[0]?.id || null;
}

// Every change to the plan is saved at once. Changing an approved plan opens a new draft version:
// the approved version stays what the last run used, and must be approved again before running.
async function savePlan(mutate) {
  const p = structuredClone(plan());
  if (p.status === 'approved' || !p.version) {
    p.version = (p.version || 0) + 1;
    p.status = 'draft';
    p.approved_at = null;
  }
  mutate(p);
  const { data, error } = await supabase.from('projects').update({ test_plan: p }).eq('id', project.id).select('test_plan').single();
  if (error) { toast(t('common.error', { msg: error.message }), 'bad'); return false; }
  project.test_plan = data.test_plan;
  render();
  return true;
}

// ---------------------------------------------------------------- plan view
function methodName(id) { return catalog.find((m) => m.id === id)?.name || id || '–'; }

function renderPlan() {
  const p = plan();
  $('crumb-project').textContent = project.name;
  $('crumb-project').href = `project.html?id=${project.id}`;
  $('plan-tag').textContent = t('plan.tag', { v: p.version || 0, status: t(`plan.status.${p.status}`) });
  $('approve').disabled = p.status === 'approved' || !(p.cases || []).length;
  $('add-case').disabled = !(project.targets || []).length;
  $('add-case').title = (project.targets || []).length ? '' : t('plan.noTargets');
  const note = $('draft-note');
  note.hidden = p.status !== 'approved';
  note.textContent = t('plan.newDraft', { v: p.version, n: (p.version || 0) + 1 });

  const cases = p.cases || [];
  $('cases-body').replaceChildren(...cases.map((c, i) => el('tr', {},
    el('td', {}, el('input', { type: 'checkbox', checked: c.selected !== false, 'aria-label': `${t('col.select')} ${c.id}`,
      onchange: (e) => savePlan((np) => { np.cases[i].selected = e.target.checked; }) })),
    el('td', { class: 'mono' }, c.id),
    el('td', {}, c.title),
    el('td', { class: 'mono' }, c.target_id),
    el('td', {}, methodName(c.catalog_id)),
    el('td', {}, el('span', { class: `pill ${c.priority === 'high' || c.priority === 'critical' ? 'bad' : c.priority === 'medium' ? 'warn' : 'idle'}` }, t(`prio.${c.priority || 'medium'}`))),
    el('td', { class: 'mono' }, c.adapter),
    el('td', {}, el('button', { type: 'button', class: 'btn-link', onclick: () => openCase(i) }, t('common.edit'))))));
  if (!cases.length) $('cases-body').append(el('tr', {}, el('td', { colspan: '8', class: 'muted' }, t('plan.empty'))));
  const selected = cases.filter((c) => c.selected !== false);
  const methods = [...new Set(selected.map((c) => methodName(c.catalog_id)))].join(', ');
  $('cases-summary').textContent = `${t('plan.summary', { n: cases.length, s: selected.length })}${methods ? ` · ${methods}` : ''}`;
}

// ---------------------------------------------------------------- case dialog
function openCase(i) {
  editing = i;
  const targets = project.targets || [];
  const c = i >= 0 ? plan().cases[i] : {
    id: '', title: '', target_id: targets[0]?.id, catalog_id: project.test_set?.[0] || '', priority: 'medium',
    requirement: '', preconditions: '', expected: '', selected: true, tags: [],
    steps: STEP_EXAMPLE[ADAPTER_FOR_KIND[targets[0]?.kind]] || [],
  };
  $('c-target').replaceChildren(...targets.map((tg) => el('option', { value: tg.id }, `${tg.id} · ${t(`tkind.${tg.kind}`)}`)));
  const methods = catalog.filter((m) => (project.test_set || []).includes(m.id) || m.id === c.catalog_id);
  $('c-method').replaceChildren(...methods.map((m) => el('option', { value: m.id }, m.name)));
  $('c-id').value = c.id; $('c-title').value = c.title; $('c-target').value = c.target_id || '';
  $('c-method').value = c.catalog_id || ''; $('c-priority').value = c.priority || 'medium';
  $('c-req').value = c.requirement || ''; $('c-pre').value = c.preconditions || ''; $('c-expected').value = c.expected || '';
  $('c-steps').value = JSON.stringify(c.steps || [], null, 2);
  $('c-selected').checked = c.selected !== false;
  $('c-delete').hidden = i < 0;
  $('case-error').textContent = '';
  stepsHint();
  $('case-dialog').showModal();
}

function stepsHint() {
  const tg = (project.targets || []).find((x) => x.id === $('c-target').value);
  const adapter = ADAPTER_FOR_KIND[tg?.kind];
  $('c-steps-hint').textContent = adapter ? t(`f.stepsHint.${adapter}`) : t('case.err.adapter');
}

async function saveCase(e) {
  e.preventDefault();
  const tg = (project.targets || []).find((x) => x.id === $('c-target').value);
  const adapter = ADAPTER_FOR_KIND[tg?.kind];
  const id = $('c-id').value.trim();
  const others = plan().cases.filter((_, i) => i !== editing);
  let steps;
  try {
    steps = JSON.parse($('c-steps').value || '[]');
    if (!Array.isArray(steps)) throw new Error('not a list');
  } catch (err) {
    $('case-error').textContent = t('case.err.json', { msg: err.message });
    return;
  }
  if (!id || others.some((c) => c.id === id)) { $('case-error').textContent = t('case.err.id'); return; }
  if (!adapter || adapter === 'desktop_plugin') { $('case-error').textContent = t('case.err.adapter'); return; }
  const prev = editing >= 0 ? plan().cases[editing] : {};
  const c = {
    ...prev, id, title: $('c-title').value.trim(), target_id: tg.id, adapter, catalog_id: $('c-method').value,
    priority: $('c-priority').value, requirement: $('c-req').value.trim(), preconditions: $('c-pre').value.trim(),
    expected: $('c-expected').value.trim(), steps, selected: $('c-selected').checked, tags: prev.tags || [],
  };
  const at = editing;
  if (await savePlan((np) => { if (at >= 0) np.cases[at] = c; else np.cases.push(c); })) $('case-dialog').close();
}

async function approve() {
  const p = structuredClone(plan());
  p.status = 'approved';
  p.approved_at = new Date().toISOString();
  const { data, error } = await supabase.from('projects').update({ test_plan: p }).eq('id', project.id).select('test_plan').single();
  if (error) { toast(t('common.error', { msg: error.message }), 'bad'); return; }
  project.test_plan = data.test_plan;
  toast(t('plan.approvedToast', { v: p.version }));
  render();
}

// ---------------------------------------------------------------- run
function runBlockers() {
  const reasons = [];
  if (plan().status !== 'approved') reasons.push(t('run.why.plan'));
  const items = readiness(project, runner.keychain, { includePlan: false });
  const open = items.filter((i) => !i.ok).map((i) => t(`ready.${i.key}`));
  if (open.length) reasons.push(t('run.why.ready', { items: open.join(' · ') }));
  if (activeRun()) reasons.push(t('run.why.active'));
  return reasons;
}

function renderRunCard() {
  const used = [...new Set((plan().cases || []).map((c) => c.target_id))];
  $('run-targets').textContent = (project.targets || []).filter((tg) => used.includes(tg.id))
    .map((tg) => `${tg.id} · ${tg.location} · ${tg.environment || '–'}`).join('\n') || '–';
  $('run-targets').style.whiteSpace = 'pre-line';
  const reasons = runBlockers();
  // Run cannot be pressed while Readiness is incomplete or the plan is not approved (DoD).
  $('run').disabled = reasons.length > 0;
  $('run-why').replaceChildren(...reasons.map((r) => el('li', { class: 'no' }, el('span', { 'aria-hidden': 'true' }, '⚠'), el('span', {}, r))));
  if (!reasons.length && runner.state !== 'online') $('run-why').append(el('li', { class: 'no' }, el('span', { 'aria-hidden': 'true' }, 'ⓘ'), el('span', {}, t('run.offline'))));
  $('cancel').disabled = !activeRun() || activeRun().status === 'cancel_requested';
}

async function startRun() {
  if (runBlockers().length) return;
  const p = plan();
  const { data, error } = await supabase.from('runs').insert({
    owner_id: session.user.id, project_id: project.id, kind: 'test_run', status: 'queued',
    plan_version: p.version, payload: { total: (p.cases || []).length },
  }).select('id').single();
  if (error) { toast(t('common.error', { msg: error.message }), 'bad'); return; }
  viewRunId = data.id;
  toast(t('run.queued'));
  await refreshRuns();
}

async function cancelRun() {
  const r = activeRun();
  if (!r) return;
  // Nobody has claimed a queued job yet, so it can be cancelled directly; a running job asks the runner.
  const { error } = r.status === 'queued'
    ? await supabase.from('runs').update({ status: 'cancelled', finished_at: new Date().toISOString() }).eq('id', r.id).eq('status', 'queued')
    : await supabase.from('runs').update({ status: 'cancel_requested' }).eq('id', r.id).eq('status', 'running');
  if (error) { toast(t('common.error', { msg: error.message }), 'bad'); return; }
  toast(t('run.cancelRequested'));
  await refreshRuns();
}

// ---------------------------------------------------------------- progress, events, results
function renderProgress() {
  const r = runs.find((x) => x.id === viewRunId);
  const results = r?.results || [];
  const total = r?.payload?.total || (r?.status === 'queued' ? (plan().cases || []).length : results.length) || 0;
  const done = results.length;
  $('prog-pill').replaceChildren(r ? pill(r.status, `${t(`state.${r.status}`)} · ${t('prog.count', { done, total })}`) : '');
  const pct = total ? Math.round((done / total) * 100) : 0;
  $('prog-fill').style.width = `${pct}%`;
  $('prog-bar').setAttribute('aria-valuemax', String(total));
  $('prog-bar').setAttribute('aria-valuenow', String(done));
  $('prog-counts').replaceChildren(...STATES.map((s) => pill(s, `${t(`state.${s}`)} ${r?.summary?.[s] ?? 0}`)));
  $('prog-note').textContent = r?.error ? `${t('prog.stopped')}: ${r.error}` : '';

  const ev = [];
  const line = (at, text, cls = '') => ev.push(el('div', { class: cls },
    el('span', {}, fmtTime(at, { timeStyle: 'medium' })), '  ', el('bdi', { dir: 'auto' }, text)));
  if (r) {
    line(r.created_at, t('ev.queued', { v: r.plan_version ?? '–' }), 'dim');
    if (r.claimed_at) line(r.claimed_at, t('ev.claimed', { runner: r.claimed_by }));
    for (const x of results) {
      const tries = x.attempts?.length > 1 ? ` · ${x.attempts.filter((a) => a.state === 'failed').length}/${x.attempts.length} failed` : '';
      line(x.finished_at, `${x.test_case_id} ${t(`state.${x.state}`)}${tries}`, x.state === 'failed' ? 'bad' : x.state === 'flaky' ? 'flaky' : '');
    }
    if (r.finished_at) line(r.finished_at, t('ev.finished', { status: t(`state.${r.status}`) }), 'dim');
  }
  $('events').replaceChildren(...ev);
  $('events').scrollTop = $('events').scrollHeight;

  $('results-empty').hidden = Boolean(r);
  $('results-body').replaceChildren(...results.map((x) => el('tr', {},
    el('td', { class: 'mono' }, x.test_case_id),
    el('td', {}, x.title || ''),
    el('td', {}, pill(x.state)),
    el('td', { style: 'max-width:420px' }, x.actual || '', x.execution_error ? el('div', { class: 'mono muted' }, x.execution_error) : null),
    el('td', { class: 'num' }, String(x.attempts?.length || (x.state === 'skipped' || x.state === 'blocked' ? 0 : 1))),
    el('td', { class: 'evidence' }, (x.evidence || []).map((path) => el('button', {
      type: 'button', class: 'btn-link mono', style: 'font-size:11.5px;margin-inline-end:8px', onclick: () => openEvidence(path),
    }, path.split('/').pop()))))));

  $('history-body').replaceChildren(...runs.map((h) => {
    const s = h.summary || {};
    const tr = el('tr', { class: `click${h.id === viewRunId ? ' selected' : ''}`, tabindex: '0' },
      el('td', {}, fmtTime(h.started_at || h.created_at)), el('td', {}, pill(h.status)), el('td', { class: 'mono' }, `v${h.plan_version ?? '–'}`),
      el('td', { class: 'num' }, String(s.passed ?? 0)), el('td', { class: 'num' }, String(s.failed ?? 0)),
      el('td', { class: 'num' }, String(s.error ?? 0)), el('td', { class: 'num' }, String(s.flaky ?? 0)));
    const pick = () => { viewRunId = h.id; renderProgress(); };
    tr.addEventListener('click', pick);
    tr.addEventListener('keydown', (e) => { if (e.key === 'Enter') pick(); });
    return tr;
  }));
}

async function openEvidence(path) {
  const { data, error } = await supabase.storage.from('evidence').createSignedUrl(path, 120);
  if (error) { toast(t('common.error', { msg: error.message }), 'bad'); return; }
  window.open(data.signedUrl, '_blank', 'noopener');
}

function render() {
  renderPlan();
  renderRunCard();
  renderProgress();
}

// Poll fast while a run is in flight, slowly otherwise (no realtime in the course stack).
async function refreshRuns() {
  clearTimeout(timer);
  runner = await loadRunner();
  await loadRuns();
  render();
  timer = setTimeout(refreshRuns, activeRun() ? 3000 : 15000);
}

session = await boot();
if (session) {
  try {
    catalog = (await (await fetch('catalog/methodologies.json')).json()).methodologies;
    await loadProject();
    $('add-case').addEventListener('click', () => openCase(-1));
    $('approve').addEventListener('click', approve);
    $('case-form').addEventListener('submit', saveCase);
    $('c-target').addEventListener('change', stepsHint);
    $('c-cancel').addEventListener('click', () => $('case-dialog').close());
    $('c-delete').addEventListener('click', async () => {
      const at = editing;
      if (await savePlan((np) => { np.cases.splice(at, 1); })) $('case-dialog').close();
    });
    $('run').addEventListener('click', startRun);
    $('cancel').addEventListener('click', cancelRun);
    document.addEventListener('langchange', render);
    await refreshRuns();
  } catch (err) {
    $('page-error').textContent = err.message;
  }
}
