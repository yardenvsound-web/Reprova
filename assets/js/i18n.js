// UI language: English by default, Hebrew (RTL) on request.
// The choice is a display preference, so localStorage is fine; it may be unavailable.
const KEY = 'reprova-lang';
let strings = {};
let lang = 'en';

function readPref() {
  try { return localStorage.getItem(KEY); } catch { return null; }
}
function writePref(value) {
  try { localStorage.setItem(KEY, value); } catch { /* ignore */ }
}

export function currentLang() { return lang; }

export function t(key, vars = {}) {
  let s = strings[key] ?? key;
  for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, String(v));
  return s;
}

export function apply(root = document) {
  root.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
  root.querySelectorAll('[data-i18n-placeholder]').forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
}

export async function setLang(next) {
  lang = next === 'he' ? 'he' : 'en';
  const res = await fetch(`i18n/${lang}.json`);
  strings = await res.json();
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === 'he' ? 'rtl' : 'ltr';
  writePref(lang);
  apply();
  document.querySelectorAll('[data-lang-option]').forEach((el) => {
    el.setAttribute('aria-pressed', String(el.dataset.langOption === lang));
  });
  document.dispatchEvent(new CustomEvent('langchange', { detail: lang }));
}

export async function initI18n() {
  await setLang(readPref() || 'en');
  document.querySelectorAll('[data-lang-option]').forEach((el) => {
    el.addEventListener('click', () => setLang(el.dataset.langOption));
  });
}
