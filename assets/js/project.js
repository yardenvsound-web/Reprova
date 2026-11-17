// F07 Project Setup with F49 Intake and the Readiness checklist. Without ?id: the projects list.
import { supabase, boot, loadRunner, pill, el, fmtTime, toast, params, t } from './ui.js';
import { buildIntake, isOpen, readiness, allReady, requestMessage, validateTargets } from './readiness.js';
import { currentLang } from './i18n.js';

const PARTS = ['gui', 'e2e', 'api', 'auth', 'engine', 'install', 'performance', 'audio'];
const $ = (id) => document.getElementById(id);

let session;
let catalog = [];
let project;            // the working copy, saved with "Save project"
let keychain = null;    // the runner's Keychain report, or null when offline
let editingTarget = -1;

// ---------------------------------------------------------------- list
async function showList() {
  $('list-view').hidden = false;
  const { data } = await supabase.from('projects').select('id, name, status, product_type, client, updated_at').order('updated_at', { ascending: false });
  const body = $('projects-body');
  body.replaceChildren();
  $('projects-empty').hidden = Boolean(data?.length);
  for (const p of data || []) {
    const tr = el('tr', { class: 'click', tabindex: '0' },
      el('td', { style: 'font-weight:600' }, p.name),
      el('td', {}, p.client?.name || '–'),
      el('td', { class: 'muted' }, t(`ptype.${p.product_type}`)),
      el('td', {}, el('span', { class: 'tag' }, t(`pstatus.${p.status}`))),
      el('td', { class: 'muted' }, fmtTime(p.updated_at)));
    const open = () => { window.location.href = `project.html?id=${p.id}`; };
    tr.addEventListener('click', open);
    tr.addEventListener('keydown', (e) => { if (e.key === 'Enter') open(); });
    body.append(tr);
  }
}

// ---------------------------------------------------------------- form <-> project
function blankProject() {
  return {
    id: null, name: '', status: 'setup', product_type: 'web', parts: [], targets: [], report_language: 'en',
    client: { name: '', contacts: [], ai_enabled: true, retention_days: 30 }, test_set: [],
    test_plan: { version: 0, status: 'draft', cases: [] },
    budget: { max_minutes: 60, max_ai_usd: 1, repro_attempts: 3 }, intake: [],
  };
}

function fillForm() {
  $('f-client').value = project.client?.name || '';
  $('f-name').value = project.name || '';
  $('f-type').value = project.product_type;
  $('f-status').value = project.status;
  $('f-lang').value = project.report_language;
  $('f-ai').checked = project.client?.ai_enabled !== false;
  $('f-minutes').value = project.budget?.max_minutes ?? 60;
  $('f-ai-usd').value = project.budget?.max_ai_usd ?? 1;
  $('f-repro').value = project.budget?.repro_attempts ?? 3;
  $('f-retention').value = project.client?.retention_days ?? 30;
}

function readForm() {
  project.client = { ...project.client, name: $('f-client').value.trim(), ai_enabled: $('f-ai').checked,
    retention_days: Number($('f-retention').value) || 30 };
  project.name = $('f-name').value.trim();
  project.product_type = $('f-type').value;
  project.status = $('f-status').value;
  project.report_language = $('f-lang').value;
  project.budget = { max_minutes: Number($('f-minutes').value) || 60, max_ai_usd: Number($('f-ai-usd').value) || 0,
    repro_attempts: Math.max(0, Number($('f-repro').value) || 0) };
}

// ---------------------------------------------------------------- render
function renderChips(holder, values, selected, label, onToggle, disabled = () => false) {
  holder.replaceChildren(...values.map((v) => el('button', {
    type: 'button', class: 'chip', 'aria-pressed': String(selected.includes(v)), disabled: disabled(v),
    onclick: () => onToggle(v),
  }, label(v))));
}

function renderParts() {
  renderChips($('parts'), PARTS, project.parts || [], (p) => t(`part.${p}`), (p) => {
    project.parts = project.parts.includes(p) ? project.parts.filter((x) => x !== p) : [...project.parts, p];
    render();
  });
}

function renderTestSet() {
  const fits = catalog.filter((m) => m.product_types.includes(project.product_type));
  $('testset-hint').textContent = t('testset.hint', { type: t(`ptype.${project.product_type}`) });
  renderChips($('testset'), fits.map((m) => m.id), project.test_set || [], (id) => catalog.find((x) => x.id === id).name, (id) => {
    project.test_set = project.test_set.includes(id) ? project.test_set.filter((x) => x !== id) : [...project.test_set, id];
    render();
  });
  // methodologies with no engine for this type are greyed (manual, or after the MVP), still selectable
  [...$('testset').children].forEach((b, i) => { if (!fits[i].engine?.[project.product_type]) b.style.opacity = '.6'; });
}

function refPill(ref) {
  const account = `${project.id}/${ref}`;
  if (!project.id || !keychain?.secret_refs) return el('span', { class: 'pill idle', title: t('ref.unknown') }, el('span', { class: 'dot' }), el('span', { class: 'mono' }, ref));
  const ok = keychain.secret_refs[account] === true;
  const p = pill(ok ? 'passed' : 'failed', ref);
  p.title = t(ok ? 'ref.found' : 'ref.missing');
  p.querySelector('span:last-child').classList.add('mono');
  return p;
}

function renderTargets() {
  const body = $('targets-body');
  body.replaceChildren(...project.targets.map((tg, i) => el('tr', {},
    el('td', { class: 'mono' }, tg.id),
    el('td', {}, t(`tkind.${tg.kind}`)),
    el('td', {}, el('span', { class: 'tag' }, t(`access.${tg.access_mode}`))),
    el('td', { class: 'mono' }, tg.location),
    el('td', { class: 'muted' }, tg.environment || '–'),
    el('td', {}, tg.is_production ? pill(tg.production_approved ? 'passed' : 'failed', t('common.yes')) : t('common.no')),
    el('td', {}, el('div', { class: 'row' }, (tg.secret_refs || []).map(refPill))),
    el('td', {}, el('button', { type: 'button', class: 'btn-link', onclick: () => openTarget(i) }, t('common.edit'))))));
}

function intakeLabel(item) {
  const base = item.key.split(':')[0];
  const tg = item.target_id ? project.targets.find((x) => x.id === item.target_id) : null;
  return t(`intake.item.${base}`) + (tg ? ` · ${tg.id}` : '') + (item.required ? '' : ` ${t('intake.optional')}`);
}

function renderIntake() {
  project.intake = buildIntake(project);
  const body = $('intake-body');
  body.replaceChildren(...project.intake.map((item) => {
    const when = item.status === 'received' ? item.received_at : item.requested_at;
    const actions = el('div', { class: 'row', style: 'justify-content:flex-end' });
    if (item.kind === 'file') {
      const input = el('input', { type: 'file', class: 'visually-hidden', id: `up-${item.key}`, onchange: (e) => upload(item, e.target.files[0]) });
      actions.append(input, el('label', { for: `up-${item.key}`, class: 'btn btn-secondary btn-sm', role: 'button', tabindex: '0',
        onkeydown: (e) => { if (e.key === 'Enter') input.click(); } }, t('intake.upload')));
      if (item.file_path) actions.append(el('button', { type: 'button', class: 'btn-link', onclick: () => viewFile(item) }, t('intake.view')));
    } else if (item.status !== 'received') {
      actions.append(el('button', { type: 'button', class: 'btn btn-secondary btn-sm', onclick: () => setIntake(item, 'received') }, t('intake.markReceived')));
    }
    if (!item.required && item.status !== 'not_needed') {
      actions.append(el('button', { type: 'button', class: 'btn-link', onclick: () => setIntake(item, 'not_needed') }, t('intake.markNeeded')));
    }
    if (item.status !== 'requested') {
      actions.append(el('button', { type: 'button', class: 'btn-link', onclick: () => setIntake(item, 'requested') }, t('intake.reset')));
    }
    return el('tr', {},
      el('td', {}, intakeLabel(item)),
      el('td', {}, pill(item.status), when ? el('div', { class: 'muted', style: 'font-size:12px;margin-top:2px' }, fmtTime(when)) : null),
      el('td', {}, actions));
  }));
  $('intake-note').textContent = project.id ? '' : t('setup.saveFirst');
}

function renderReadiness() {
  const items = readiness(project, keychain);
  const ok = items.filter((i) => i.ok).length;
  $('ready-ring').style.setProperty('--p', String(Math.round((ok / items.length) * 100)));
  $('ready-count').textContent = `${ok}/${items.length}`;
  $('ready-pill').replaceChildren(pill(allReady(items) ? 'ready' : 'not_ready'));
  $('ready-list').replaceChildren(...items.map((i) => {
    let why = '';
    if (!i.ok && i.key === 'keychain') why = t(i.unknown ? 'ready.why.keychainUnknown' : 'ready.why.keychain', { refs: i.detail.join(', ') });
    if (!i.ok && i.key === 'access') why = t('ready.why.access', { items: i.detail.map((k) => t(`intake.item.${k.split(':')[0]}`)).join(' · ') });
    if (!i.ok && i.key === 'production') why = t('ready.why.production', { ids: i.detail.join(', ') });
    return el('li', { class: i.ok ? 'ok' : 'no', 'data-key': i.key },
      el('span', { 'aria-hidden': 'true' }, i.ok ? '✓' : '⚠'),
      el('span', {}, el('span', { class: 'visually-hidden' }, `${t(i.ok ? 'state.ready' : 'state.not_ready')}: `),
        t(`ready.${i.key}`), why ? el('span', { class: 'why' }, why) : null));
  }));
  $('go-plan').href = project.id ? `plan.html?id=${project.id}` : '#';
  $('go-plan').toggleAttribute('aria-disabled', !project.id);
}

function render() {
  $('crumb-name').textContent = project.name || t('setup.newTitle');
  $('status-tag').textContent = t(`pstatus.${project.status}`);
  renderParts();
  renderTestSet();
  renderTargets();
  renderIntake();
  renderReadiness();
}

// ---------------------------------------------------------------- targets dialog
function openTarget(i) {
  editingTarget = i;
  const tg = i >= 0 ? project.targets[i] : { id: `t-${project.targets.length + 1}`, kind: 'web', access_mode: 'black_box', location: '', environment: 'staging', is_production: false, production_approved: false, secret_refs: [] };
  $('t-id').value = tg.id; $('t-kind').value = tg.kind; $('t-access').value = tg.access_mode;
  $('t-env').value = tg.environment || ''; $('t-location').value = tg.location || '';
  $('t-refs').value = (tg.secret_refs || []).join(', ');
  $('t-prod').checked = Boolean(tg.is_production); $('t-prod-ok').checked = Boolean(tg.production_approved);
  $('t-prod-ok').disabled = !tg.is_production;
  $('t-refs-hint').textContent = t('f.refsHint', { project: project.id || '<project_id>' });
  $('t-delete').hidden = i < 0;
  $('target-error').textContent = '';
  $('target-dialog').showModal();
}

function saveTarget(e) {
  e.preventDefault();
  const tg = {
    id: $('t-id').value.trim(), kind: $('t-kind').value, access_mode: $('t-access').value,
    location: $('t-location').value.trim(), environment: $('t-env').value.trim(),
    is_production: $('t-prod').checked, production_approved: $('t-prod').checked && $('t-prod-ok').checked,
    secret_refs: $('t-refs').value.split(',').map((s) => s.trim()).filter(Boolean),
  };
  const next = [...project.targets];
  if (editingTarget >= 0) next[editingTarget] = tg; else next.push(tg);
  const errors = validateTargets(next);
  if (errors.length) {
    $('target-error').textContent = errors.map((er) => t(er.code, { id: er.id })).join(' ');
    return;
  }
  project.targets = next;
  $('target-dialog').close();
  render();
}

// ---------------------------------------------------------------- intake actions (saved at once)
async function persistIntake() {
  if (!project.id) return;
  const { error } = await supabase.from('projects').update({ intake: project.intake }).eq('id', project.id);
  if (error) toast(t('common.error', { msg: error.message }), 'bad');
}

async function setIntake(item, status) {
  const now = new Date().toISOString();
  Object.assign(project.intake.find((i) => i.key === item.key), {
    status, received_at: status === 'received' ? now : null,
    requested_at: status === 'requested' ? item.requested_at || now : item.requested_at,
  });
  await persistIntake();
  render();
}

async function upload(item, file) {
  if (!file) return;
  if (!project.id) { toast(t('setup.saveFirst'), 'bad'); return; }
  const safe = file.name.replace(/[^\w.-]+/g, '_');
  const path = `${project.id}/${item.key}/${Date.now()}_${safe}`;
  const { error } = await supabase.storage.from('intake').upload(path, file, { upsert: false, contentType: file.type || undefined });
  if (error) { toast(t('common.error', { msg: error.message }), 'bad'); return; }
  Object.assign(project.intake.find((i) => i.key === item.key), { status: 'received', received_at: new Date().toISOString(), file_path: path });
  await persistIntake();
  render();
}

async function viewFile(item) {
  const { data, error } = await supabase.storage.from('intake').createSignedUrl(item.file_path, 120);
  if (error) { toast(t('common.error', { msg: error.message }), 'bad'); return; }
  window.open(data.signedUrl, '_blank', 'noopener');
}

async function copyRequest() {
  readForm();
  const intake = buildIntake(project);
  // The message is in the report language, built from a template in code (no AI).
  const lang = project.report_language;
  const strings = lang === currentLang() ? null : await (await fetch(`i18n/${lang}.json`)).json();
  const tr = (k, v = {}) => {
    let s = strings ? strings[k] ?? k : t(k);
    for (const [a, b] of Object.entries(v)) s = s.replaceAll(`{${a}}`, String(b));
    return s;
  };
  const msg = requestMessage(project, intake, tr);
  if (!msg) { toast(t('intake.nothing')); return; }
  try { await navigator.clipboard.writeText(msg); } catch { window.prompt('', msg); }
  const now = new Date().toISOString();
  project.intake = intake.map((i) => (isOpen(i) && !i.requested_at ? { ...i, requested_at: now } : i));
  await persistIntake();
  toast(t('intake.copied', { n: intake.filter(isOpen).length }));
  render();
}

// ---------------------------------------------------------------- save
async function save() {
  readForm();
  $('save-error').textContent = '';
  const errors = validateTargets(project.targets);
  if (errors.length) {
    $('save-error').textContent = errors.map((er) => t(er.code, { id: er.id })).join(' ');
    return;
  }
  project.intake = buildIntake(project);
  const row = {
    name: project.name || t('setup.newTitle'), status: project.status, client: project.client, product_type: project.product_type,
    parts: project.parts, targets: project.targets, report_language: project.report_language, test_set: project.test_set,
    budget: project.budget, intake: project.intake,
  };
  const res = project.id
    ? await supabase.from('projects').update(row).eq('id', project.id).select().single()
    : await supabase.from('projects').insert({ ...row, owner_id: session.user.id }).select().single();
  if (res.error) {
    // the database refuses an unapproved Production target as well (projects_production_needs_approval)
    $('save-error').textContent = t('common.error', { msg: res.error.message });
    return;
  }
  toast(t('setup.saved'));
  if (!project.id) { window.location.replace(`project.html?id=${res.data.id}`); return; }
  project = res.data;
  render();
}

// ---------------------------------------------------------------- boot
async function showSetup() {
  $('setup-view').hidden = false;
  catalog = (await (await fetch('catalog/methodologies.json')).json()).methodologies;
  if (params.get('id')) {
    const { data, error } = await supabase.from('projects').select('*').eq('id', params.get('id')).maybeSingle();
    if (error || !data) { $('save-error').textContent = t('setup.notFound'); return; }
    project = data;
  } else {
    project = blankProject();
  }
  fillForm();
  for (const id of ['f-client', 'f-name', 'f-type', 'f-status', 'f-lang']) {
    $(id).addEventListener('change', () => { readForm(); render(); });
  }
  $('f-name').addEventListener('input', () => { $('crumb-name').textContent = $('f-name').value; });
  $('add-target').addEventListener('click', () => openTarget(-1));
  $('target-form').addEventListener('submit', saveTarget);
  $('t-prod').addEventListener('change', () => { $('t-prod-ok').disabled = !$('t-prod').checked; if (!$('t-prod').checked) $('t-prod-ok').checked = false; });
  $('t-cancel').addEventListener('click', () => $('target-dialog').close());
  $('t-delete').addEventListener('click', () => { project.targets.splice(editingTarget, 1); $('target-dialog').close(); render(); });
  $('copy-request').addEventListener('click', copyRequest);
  $('save').addEventListener('click', save);
  document.addEventListener('langchange', () => { readForm(); render(); });
  render();
  // The runner's Keychain report refreshes with its heartbeat.
  const tick = async () => { keychain = (await loadRunner()).keychain; renderTargets(); renderReadiness(); };
  await tick();
  setInterval(tick, 15000);
}

session = await boot();
if (session) {
  if (params.get('id') || params.get('new')) await showSetup();
  else { await showList(); loadRunner(); document.addEventListener('langchange', showList); }
}
