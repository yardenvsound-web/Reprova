// F06 Dashboard, first version: Clients, Active projects and Runs cards, Recent runs, runner status.
import { supabase, boot, loadRunner, pill, el, fmtTime, t } from './ui.js';
import { REFRESH_SECONDS } from './config.js';

async function loadCards() {
  const since = new Date(Date.now() - 30 * 24 * 3600 * 1000).toISOString();
  const [projects, runs] = await Promise.all([
    supabase.from('projects').select('id, status, client'),
    supabase.from('runs').select('id, status').neq('kind', 'runner_heartbeat').gte('created_at', since),
  ]);
  const ps = projects.data || [];
  const rs = runs.data || [];
  const clients = new Set(ps.map((p) => p.client?.name).filter(Boolean));
  const active = ps.filter((p) => p.status === 'active').length;
  const setup = ps.filter((p) => p.status === 'setup').length;
  const running = rs.filter((r) => r.status === 'running' || r.status === 'cancel_requested').length;
  const queued = rs.filter((r) => r.status === 'queued').length;
  document.getElementById('kpi-clients').textContent = clients.size;
  document.getElementById('kpi-active').textContent = active;
  document.getElementById('kpi-active-sub').textContent = t('kpi.activeSub', { n: setup });
  document.getElementById('kpi-runs').textContent = rs.length;
  document.getElementById('kpi-runs-sub').textContent = t('kpi.runsSub', { running, queued });
  document.getElementById('dash-summary').textContent = t('dash.summary', { active, queue: running + queued, setup });
}

async function loadRuns() {
  const body = document.getElementById('runs-body');
  const empty = document.getElementById('runs-empty');
  const { data, error } = await supabase
    .from('runs').select('id, kind, status, summary, created_at, started_at, project_id, projects(name, product_type)')
    .neq('kind', 'runner_heartbeat')
    .order('created_at', { ascending: false })
    .limit(10);
  const rows = error ? [] : data;
  body.replaceChildren();
  empty.hidden = rows.length > 0;
  for (const r of rows) {
    const s = r.summary || {};
    const n = (k) => (r.status === 'queued' ? '–' : String(s[k] ?? 0));
    const tr = el('tr', { class: 'click', tabindex: '0', title: r.projects?.name || '' },
      el('td', { style: 'font-weight:600' }, r.projects?.name ?? '–'),
      el('td', { class: 'muted' }, r.projects ? t(`ptype.${r.projects.product_type}`) : '–'),
      el('td', { class: 'mono' }, r.kind),
      el('td', {}, pill(r.status)),
      el('td', { class: 'num' }, n('passed')),
      el('td', { class: 'num' }, n('failed')),
      el('td', { class: 'num' }, n('error')),
      el('td', { class: 'num' }, n('flaky')),
      el('td', { class: 'muted' }, fmtTime(r.started_at || r.created_at)));
    // A run row opens the project's Test Plan & Run screen.
    const open = () => { window.location.href = `plan.html?id=${r.project_id}&run=${r.id}`; };
    tr.addEventListener('click', open);
    tr.addEventListener('keydown', (e) => { if (e.key === 'Enter') open(); });
    body.append(tr);
  }
}

async function refresh() {
  const runner = await loadRunner();
  document.getElementById('last-seen').textContent =
    runner.heartbeat_at ? t('dash.lastSeen', { when: fmtTime(runner.heartbeat_at, { dateStyle: 'short', timeStyle: 'medium' }) }) : '';
  await Promise.all([loadCards(), loadRuns()]);
}

if (await boot()) {
  document.addEventListener('langchange', refresh);
  await refresh();
  setInterval(refresh, REFRESH_SECONDS * 1000);
}
