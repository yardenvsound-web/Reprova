// F49 Intake and the F07 Readiness checklist. Pure functions: no DOM, no network,
// so they are tested with `node --test tests/web` and shared by project.js and plan.js.

// ---------------------------------------------------------------- Intake (F49)
// What we need from the client, built in code from the product type and the Targets.
// Stored statuses (requested / received / not_needed) are kept by key when the list is rebuilt.
export function intakeTemplate(project) {
  const items = [
    { key: 'requirements_doc', kind: 'file', required: true },
    { key: 'written_approval', kind: 'file', required: true },
  ];
  const type = project.product_type;
  if (type === 'web') {
    items.push({ key: 'staging_link', kind: 'access', required: true },
      { key: 'test_users', kind: 'access', required: true });
  } else if (type === 'api') {
    items.push({ key: 'api_base_url', kind: 'access', required: true },
      { key: 'api_token', kind: 'access', required: true },
      { key: 'api_docs', kind: 'file', required: false });
  } else if (type === 'desktop_plugin') {
    items.push({ key: 'installer', kind: 'file', required: true },
      { key: 'test_license', kind: 'access', required: false });
  }
  for (const t of project.targets || []) {
    if (t.access_mode === 'white_box') {
      items.push({ key: `repo_access:${t.id}`, kind: 'access', required: true, target_id: t.id },
        { key: `repo_ref:${t.id}`, kind: 'access', required: true, target_id: t.id });
    }
  }
  if ((project.targets || []).some((t) => t.is_production)) {
    items.push({ key: 'production_approval', kind: 'access', required: true });
  }
  return items;
}

export function buildIntake(project) {
  const stored = new Map((project.intake || []).map((i) => [i.key, i]));
  return intakeTemplate(project).map((tpl) => {
    const s = stored.get(tpl.key) || {};
    return {
      ...tpl,
      status: s.status || 'requested',
      requested_at: s.requested_at || null,
      received_at: s.received_at || null,
      file_path: s.file_path || null,
      note: s.note || '',
    };
  });
}

export const isOpen = (item) => item.status !== 'received' && item.status !== 'not_needed';

// The ready-made request: only the items still missing. Built from a template, no AI.
export function requestMessage(project, intake, tr) {
  const missing = intake.filter(isOpen);
  if (!missing.length) return '';
  const target = (key) => (project.targets || []).find((t) => t.id === key.split(':')[1]);
  const lines = missing.map((i) => {
    const base = i.key.split(':')[0];
    const loc = i.target_id ? ` (${target(i.key)?.location || i.target_id})` : '';
    return `- ${tr(`intake.item.${base}`)}${loc}${i.required ? '' : ` ${tr('intake.optional')}`}`;
  });
  return [
    tr('intake.msg.greeting', { client: project.client?.name || '' }),
    '',
    tr('intake.msg.intro', { product: project.name || '' }),
    ...lines,
    '',
    tr('intake.msg.credentials'),
    '',
    tr('intake.msg.thanks'),
  ].join('\n');
}

// ---------------------------------------------------------------- Readiness (F07)
// keychain: the runner's heartbeat report {secret_refs: {"<project_id>/<ref>": bool}} or null.
// Every item: {key, ok, detail}. Run is enabled only when every item is ok.
export function readiness(project, keychain, { includePlan = true } = {}) {
  const intake = buildIntake(project);
  const byKey = Object.fromEntries(intake.map((i) => [i.key, i]));
  const received = (k) => byKey[k]?.status === 'received';
  const targets = project.targets || [];
  const items = [];

  items.push({ key: 'client', ok: Boolean(project.client?.name?.trim() && project.name?.trim()) });
  items.push({ key: 'type', ok: Boolean(project.product_type && (project.parts || []).length) });
  items.push({ key: 'target', ok: targets.length > 0 });
  items.push({ key: 'requirements', ok: received('requirements_doc') });
  items.push({ key: 'approval', ok: received('written_approval') });

  const openAccess = intake.filter((i) => i.required && !['requirements_doc', 'written_approval'].includes(i.key) && isOpen(i));
  items.push({ key: 'access', ok: openAccess.length === 0, detail: openAccess.map((i) => i.key) });

  const refs = targets.flatMap((t) => (t.secret_refs || []).map((ref) => ({ ref, account: `${project.id}/${ref}` })));
  if (!refs.length) {
    items.push({ key: 'keychain', ok: true, detail: [] });
  } else if (!keychain?.secret_refs) {
    items.push({ key: 'keychain', ok: false, unknown: true, detail: refs.map((r) => r.ref) });
  } else {
    const missing = refs.filter((r) => keychain.secret_refs[r.account] !== true).map((r) => r.ref);
    items.push({ key: 'keychain', ok: missing.length === 0, detail: missing });
  }

  const unapproved = targets.filter((t) => t.is_production && t.production_approved !== true).map((t) => t.id);
  items.push({ key: 'production', ok: unapproved.length === 0, detail: unapproved });
  items.push({ key: 'testset', ok: (project.test_set || []).length > 0 });
  if (includePlan) items.push({ key: 'plan', ok: project.test_plan?.status === 'approved' });
  return items;
}

export const allReady = (items) => items.every((i) => i.ok);

// ---------------------------------------------------------------- Targets (F07)
export function validateTargets(targets) {
  const errors = [];
  const ids = new Set();
  for (const t of targets) {
    if (!t.id) errors.push({ code: 'target.err.id' });
    if (ids.has(t.id)) errors.push({ code: 'target.err.duplicate', id: t.id });
    ids.add(t.id);
    if (!t.location?.trim()) errors.push({ code: 'target.err.location', id: t.id });
    if (t.is_production && t.production_approved !== true) errors.push({ code: 'target.err.production', id: t.id });
  }
  return errors;
}

export const ADAPTER_FOR_KIND = { web: 'web_playwright', api: 'api_pytest', installer: 'desktop_plugin' };
