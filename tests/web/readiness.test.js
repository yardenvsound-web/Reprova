// node --test tests/web
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildIntake, readiness, allReady, requestMessage, validateTargets } from '../../assets/js/readiness.js';

const tr = (k, v = {}) => `${k}${Object.keys(v).length ? JSON.stringify(v) : ''}`;

function project(over = {}) {
  return {
    id: 'p1', name: 'Demo Booking Web', product_type: 'web', parts: ['gui'],
    client: { name: 'Demo Hospitality Ltd.' }, test_set: ['smoke'],
    targets: [{ id: 't-web', kind: 'web', access_mode: 'black_box', location: 'http://localhost:8765', secret_refs: ['demo_web_login'] }],
    test_plan: { status: 'approved', cases: [] }, intake: [], ...over,
  };
}
const received = (...keys) => keys.map((key) => ({ key, status: 'received' }));
const keychainOk = { secret_refs: { 'p1/demo_web_login': true } };
const item = (items, key) => items.find((i) => i.key === key);

test('without requirements document and written approval, Readiness is Not ready', () => {
  const p = project({ intake: received('staging_link', 'test_users') });
  const r = readiness(p, keychainOk);
  assert.equal(item(r, 'requirements').ok, false);
  assert.equal(item(r, 'approval').ok, false);
  assert.equal(allReady(r), false);
  const ok = readiness(project({ intake: received('staging_link', 'test_users', 'requirements_doc', 'written_approval') }), keychainOk);
  assert.equal(allReady(ok), true);
});

test('a White Box target adds a read-only repo request, and Copy request lists only missing items', () => {
  const p = project({
    targets: [...project().targets, { id: 'repo', kind: 'repository', access_mode: 'white_box', location: 'github.com/demo/app', secret_refs: [] }],
    intake: received('requirements_doc', 'staging_link'),
  });
  const intake = buildIntake(p);
  assert.ok(intake.some((i) => i.key === 'repo_access:repo'));
  const msg = requestMessage(p, intake, tr);
  assert.match(msg, /intake\.item\.repo_access \(github\.com\/demo\/app\)/);
  assert.doesNotMatch(msg, /intake\.item\.requirements_doc/);
  assert.doesNotMatch(msg, /intake\.item\.staging_link/);
  assert.match(msg, /intake\.item\.written_approval/);
});

test('a credential ref missing from the Keychain marks the keychain item Not ready', () => {
  const p = project({ intake: received('staging_link', 'test_users', 'requirements_doc', 'written_approval') });
  const r = readiness(p, { secret_refs: { 'p1/demo_web_login': false } });
  assert.deepEqual(item(r, 'keychain'), { key: 'keychain', ok: false, detail: ['demo_web_login'] });
  assert.equal(item(readiness(p, null), 'keychain').unknown, true);
});

test('a Production target without approval is invalid and Not ready', () => {
  const prod = { id: 'live', kind: 'web', access_mode: 'black_box', location: 'https://x', is_production: true, production_approved: false };
  assert.deepEqual(validateTargets([prod]).map((e) => e.code), ['target.err.production']);
  assert.deepEqual(validateTargets([{ ...prod, production_approved: true }]), []);
  assert.equal(item(readiness(project({ targets: [prod] }), keychainOk), 'production').ok, false);
  assert.ok(buildIntake(project({ targets: [prod] })).some((i) => i.key === 'production_approval'));
});

test('a draft plan is Not ready', () => {
  const p = project({ test_plan: { status: 'draft' }, intake: received('staging_link', 'test_users', 'requirements_doc', 'written_approval') });
  assert.equal(item(readiness(p, keychainOk), 'plan').ok, false);
});
