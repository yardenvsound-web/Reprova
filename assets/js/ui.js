// Shared console helpers: page boot, status pills (always color + icon + word), runner status.
import { supabase } from './supabase.js';
import { requireOperator, signOut } from './auth.js';
import { initI18n, t, currentLang } from './i18n.js';
import { RUNNER_STALE_SECONDS } from './config.js';

// 24px stroke icons (1.75px, rounded), from the design system.
const ICON = {
  check: 'M22 11.1V12a10 10 0 1 1-5.9-9.1M22 4 12 14l-3-3',
  alert: 'M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h16.9a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01',
  wave: 'M22 12h-4l-3 9L9 3l-3 9H2',
  zap: 'M13 2 3 14h9l-1 8 10-12h-9l1-8z',
  slash: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM4.9 4.9l14.2 14.2',
  skip: 'M5 4l10 8-10 8zM19 5v14',
  clock: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 6v6l4 2',
  spin: 'M21 12a9 9 0 1 1-2.6-6.4M21 4v5h-5',
  x: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM15 9l-6 6M9 9l6 6',
  dot: 'M12 12h.01',
  help: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01',
};

// state -> [css class, icon]; the word always comes from i18n
const STATE = {
  passed: ['ok', 'check'], failed: ['bad', 'alert'], flaky: ['flaky', 'wave'], error: ['err', 'zap'],
  blocked: ['idle', 'slash'], skipped: ['idle', 'skip'],
  queued: ['idle', 'clock'], running: ['info', 'spin'], cancel_requested: ['idle', 'x'],
  done: ['ok', 'check'], cancelled: ['idle', 'x'],
  online: ['ok', 'dot'], offline: ['bad', 'dot'], unknown: ['idle', 'dot'],
  ready: ['ok', 'check'], not_ready: ['warn', 'alert'],
  requested: ['warn', 'clock'], received: ['ok', 'check'], not_needed: ['idle', 'slash'],
};

export function icon(name, size = 14) {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('width', size); svg.setAttribute('height', size); svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('fill', 'none'); svg.setAttribute('stroke', 'currentColor'); svg.setAttribute('stroke-width', '2');
  svg.setAttribute('stroke-linecap', 'round'); svg.setAttribute('stroke-linejoin', 'round'); svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS(ns, 'path');
  path.setAttribute('d', ICON[name] || ICON.dot);
  svg.append(path);
  return svg;
}

// A status pill: dot + icon + word. `label` overrides the i18n word.
export function pill(state, label) {
  const [cls, ic] = STATE[state] || ['idle', 'dot'];
  const span = document.createElement('span');
  span.className = `pill ${cls}`;
  const dot = document.createElement('span');
  dot.className = 'dot';
  const text = document.createElement('span');
  text.textContent = label ?? t(`state.${state}`);
  span.append(dot, icon(ic), text);
  return span;
}

// Tiny element builder: el('td', {class: 'mono'}, 'text', child)
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else if (k === 'text') node.textContent = v;
    else node.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) if (c !== null && c !== undefined && c !== false) node.append(c);
  return node;
}

export function fmtTime(iso, opts = { dateStyle: 'short', timeStyle: 'short' }) {
  if (!iso) return '–';
  return new Date(iso).toLocaleString(currentLang() === 'he' ? 'he-IL' : 'en-GB', opts);
}

export function toast(message, kind = 'ok') {
  const box = document.getElementById('toast') || document.body.appendChild(el('div', { id: 'toast', role: 'status', 'aria-live': 'polite' }));
  box.className = `toast ${kind}`;
  box.textContent = message;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { box.className = 'toast'; box.textContent = ''; }, 4000);
}

export const params = new URLSearchParams(window.location.search);

// ---------------------------------------------------------------- runner status
export function runnerState(heartbeatIso, now = Date.now()) {
  if (!heartbeatIso) return 'unknown';
  const age = (now - new Date(heartbeatIso).getTime()) / 1000;
  return age <= RUNNER_STALE_SECONDS ? 'online' : 'offline';
}

// The heartbeat row also carries the runner's Keychain report (names only).
export async function loadRunner() {
  const { data, error } = await supabase
    .from('runs').select('heartbeat_at, claimed_by, output')
    .eq('kind', 'runner_heartbeat')
    .order('heartbeat_at', { ascending: false, nullsFirst: false })
    .limit(1);
  const row = !error && data && data[0] ? data[0] : null;
  const state = runnerState(row?.heartbeat_at);
  const holder = document.getElementById('runner-status');
  if (holder) {
    const p = pill(state, t(`runner.${state}`));
    p.id = 'runner-status';
    p.setAttribute('aria-live', 'polite');
    holder.replaceWith(p);
  }
  // A stale report is not trusted: when the runner is offline, Keychain refs show as unknown.
  return { state, heartbeat_at: row?.heartbeat_at || null, keychain: state === 'online' ? row?.output || null : null };
}

// ---------------------------------------------------------------- boot
export async function boot() {
  const session = await requireOperator();
  if (!session) return null;
  await initI18n();
  document.getElementById('signout')?.addEventListener('click', signOut);
  return session;
}

export { supabase, t };
