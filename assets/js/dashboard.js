import { supabase } from './supabase.js';
import { requireOperator, signOut } from './auth.js';
import { initI18n, t, currentLang } from './i18n.js';
import { RUNNER_STALE_SECONDS, REFRESH_SECONDS } from './config.js';

const STATUS_CLASS = {
  queued: 'idle', running: 'info', cancel_requested: 'idle',
  done: 'ok', error: 'err', cancelled: 'idle',
};

function fmtTime(iso) {
  if (!iso) return '–';
  return new Date(iso).toLocaleString(currentLang() === 'he' ? 'he-IL' : 'en-GB', {
    dateStyle: 'short', timeStyle: 'medium',
  });
}

function pill(cls, text) {
  const span = document.createElement('span');
  span.className = `pill ${cls}`;
  const dot = document.createElement('span');
  dot.className = 'dot';
  const label = document.createElement('span');
  label.textContent = text;
  span.append(dot, label);
  return span;
}

// Runner is online when its heartbeat row was updated within RUNNER_STALE_SECONDS.
export function runnerState(heartbeatIso, now = Date.now()) {
  if (!heartbeatIso) return 'unknown';
  const age = (now - new Date(heartbeatIso).getTime()) / 1000;
  return age <= RUNNER_STALE_SECONDS ? 'online' : 'offline';
}

async function loadRunner() {
  const el = document.getElementById('runner-status');
  const seen = document.getElementById('last-seen');
  const { data, error } = await supabase
    .from('runs').select('heartbeat_at, claimed_by')
    .eq('kind', 'runner_heartbeat')
    .order('heartbeat_at', { ascending: false, nullsFirst: false })
    .limit(1);
  const hb = !error && data && data[0] ? data[0].heartbeat_at : null;
  const state = runnerState(hb);
  const map = { online: ['ok', 'runner.online'], offline: ['bad', 'runner.offline'], unknown: ['idle', 'runner.unknown'] };
  const [cls, key] = map[state];
  el.replaceWith(Object.assign(pill(cls, t(key)), { id: 'runner-status' }));
  document.getElementById('runner-status').setAttribute('aria-live', 'polite');
  seen.textContent = hb ? t('dash.lastSeen', { when: fmtTime(hb) }) : '';
}

async function loadRuns() {
  const body = document.getElementById('runs-body');
  const empty = document.getElementById('runs-empty');
  const { data, error } = await supabase
    .from('runs').select('id, kind, status, created_at, projects(name)')
    .neq('kind', 'runner_heartbeat')
    .order('created_at', { ascending: false })
    .limit(10);
  body.replaceChildren();
  const rows = error ? [] : data;
  empty.hidden = rows.length > 0;
  for (const r of rows) {
    const tr = document.createElement('tr');
    const tdP = document.createElement('td'); tdP.textContent = r.projects?.name ?? '–';
    const tdK = document.createElement('td'); tdK.className = 'mono'; tdK.textContent = r.kind;
    const tdS = document.createElement('td'); tdS.append(pill(STATUS_CLASS[r.status] || 'idle', t(`status.${r.status}`)));
    const tdC = document.createElement('td'); tdC.className = 'muted'; tdC.textContent = fmtTime(r.created_at);
    tr.append(tdP, tdK, tdS, tdC);
    body.append(tr);
  }
}

async function refresh() {
  await Promise.all([loadRunner(), loadRuns()]);
}

const session = await requireOperator();
if (session) {
  await initI18n();
  document.getElementById('signout').addEventListener('click', signOut);
  document.addEventListener('langchange', refresh);
  await refresh();
  setInterval(refresh, REFRESH_SECONDS * 1000);
}
