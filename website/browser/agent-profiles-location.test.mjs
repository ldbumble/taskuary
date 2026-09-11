import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdir } from 'node:fs/promises';
import { clickNav, startHarness } from './harness.mjs';
async function clickText(page, text, selector = 'button,p,div') {
  await page.waitForFunction(({ text, selector }) => [...document.querySelectorAll(selector)].some((el) => el.textContent.trim() === text && el.getBoundingClientRect().height), {}, { text, selector });
  await page.evaluate(({ text, selector }) => [...document.querySelectorAll(selector)].find((el) => el.textContent.trim() === text && el.getBoundingClientRect().height).click(), { text, selector });
}
async function selectProvider(page, label) {
  await page.click('[role="dialog"] [role="combobox"]');
  await clickText(page, label, '[role="option"]');
}
async function connectionsPage(page) {
  await clickNav(page, 'Connections');
  await page.waitForSelector('input[placeholder^="Search connectors"]');
  await page.type('input[placeholder^="Search connectors"]', 'AI CLI agents');
  await clickText(page, 'AI CLI agents', 'p');
  await page.waitForSelector('[data-connection="claude"]');
}

test('Connections share CLI commands; Docs profiles choose only provider and model', { timeout: 120000 }, async (t) => {
  const harness = await startHarness(); t.after(() => harness.close());
  const page = await harness.newPage(), errors = [], writes = [], installs = [];
  page.on('pageerror', (e) => errors.push(e.message));
  const profiles = {
    coder: { provider: 'cli:claude', kind: 'coding', rules_doc: 'coder', purpose: 'Edit code' },
    codex: { provider: 'cli:codex', kind: 'coding', rules_doc: 'coder', purpose: 'Edit code' },
    researcher: { provider: 'cli:claude', kind: 'research', purpose: 'Research public information' },
  };
  const clis = [
    { name: 'claude', label: 'Claude Code', config: { cmd: 'claude', args: ['-p'] }, configured: true, installed: true, setup: 'claude', models: { choices: ['sonnet', 'opus'] } },
    { name: 'codex', label: 'OpenAI Codex CLI', config: { cmd: 'codex', args: ['exec'] }, configured: true, installed: true, models: { choices: ['test-codex-model'] } },
    { name: 'devin', label: 'Devin CLI', config: { cmd: 'devin', args: ['-p'] }, installed: false, installable: true, install: 'devin' },
    { name: 'muse', label: 'Meta Muse Code', config: { cmd: 'muse', args: ['exec', '--yolo'] }, installed: false, installable: false, why_not: 'its installer does not run on Windows' },
  ];
  page.off('request', page.fixtureRequestGuard);
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname; let data;
    if (path === '/api/agents') data = { config: profiles, models: {}, default: 'coder',
      data: Object.entries(profiles).map(([Name, config]) => ({ Name, Config: JSON.stringify(config), installed: true })) };
    if (path === '/api/cli/connections') data = { data: clis };
    if (path === '/api/cli/install/terminal' && request.method() === 'POST') {
      installs.push(JSON.parse(request.postData()));
      data = { phase: 'installing', name: 'devin', sid: 'installer-fixture', taskId: 42 };
    }
    if (path === '/api/cli/install/state') {
      clis.find((c) => c.name === 'devin').installed = true;
      data = { phase: 'done', name: 'devin', detail: 'devin is installed', path: 'devin' };
    }
    if (path === '/api/terminals/installer-fixture/browser') data = { open: false };
    if (path === '/api/terminals/installer-fixture/wrap') data = { ok: true };
    if (path === '/api/doc/researcher') data = { content: '# Researcher\nRead public sources and cite findings.' };
    if (path === '/api/doc/scout') data = { content: '# Scout\nCompare vendors and cite public sources.' };
    if (request.method() === 'PUT' && (path.startsWith('/api/agents/') || path.startsWith('/api/cli/connections/'))) {
      const name = decodeURIComponent(path.split('/').at(-1)), update = JSON.parse(request.postData());
      writes.push({ path, name, update });
      if (path.startsWith('/api/agents/')) profiles[name] = { ...profiles[name], ...update };
      else clis.find((c) => c.name === name).config = update;
      data = { ok: true, rules_doc: update.rules_doc };
    }
    if (data) return request.respond({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
    page.fixtureRequestGuard(request);
  });
  await page.goto(harness.ui, { waitUntil: 'domcontentloaded' });
  await connectionsPage(page);
  assert.equal(await page.$$eval('[data-connection="claude"]', (els) => els.length), 1);
  assert.match(await page.$eval('[data-connection="muse"]', (el) => el.innerText), /Cannot install here/);
  assert.doesNotMatch(await page.$eval('[data-connection="muse"]', (el) => el.innerText), /Available/);
  assert.match(await page.$eval('[data-connection="devin"]', (el) => el.innerText), /Not installed/);
  assert.match(await page.$eval('[data-connection="codex"]', (el) => el.innerText), /Installed/);
  assert.doesNotMatch(await page.evaluate(() => document.body.innerText), /researcher|Researcher|Add profile|make default/);
  await page.click('[data-connection="claude"] button');
  await page.waitForSelector('[role="dialog"] textarea');
  await page.focus('[role="dialog"] textarea');
  await page.keyboard.down('Control'); await page.keyboard.press('End'); await page.keyboard.up('Control');
  await page.type('[role="dialog"] textarea', '\n--verbose');
  await clickText(page, 'Save', 'button');
  await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
  assert.equal(writes[0].path, '/api/cli/connections/claude');
  assert.deepEqual(writes[0].update.args, ['-p', '--verbose']);
  await mkdir('../.codex-tmp', { recursive: true });
  await page.screenshot({ path: '../.codex-tmp/cli-connections.png', fullPage: true });
  await page.evaluate(() => [...document.querySelectorAll('[data-connection="devin"] button')].find((el) => el.textContent === 'Install').click());
  await page.waitForSelector('.xterm');
  assert.deepEqual(installs, [{ name: 'devin', terminal: true }]);
  await page.waitForFunction(() => document.querySelector('[data-connection="devin"]').innerText.includes('Installed'));
  await page.screenshot({ path: '../.codex-tmp/cli-installer-pane.png', fullPage: true });
  await clickText(page, 'Close terminal', 'button');
  await page.waitForFunction(() => !document.querySelector('.xterm'));
  await clickText(page, 'Manage profiles in Docs', 'button');
  await page.waitForFunction(() => document.body.innerText.includes('RESEARCHER.md'));
  assert.doesNotMatch(await page.evaluate(() => document.body.innerText), /CODEX\.md/);
  assert.match(await page.evaluate(() => document.body.innerText), /Used by coder, codex/);
  await clickText(page, 'RESEARCHER.md', 'p');
  await page.waitForFunction(() => [...document.querySelectorAll('textarea')].some((el) => el.value.includes('Read public sources')));
  await clickText(page, 'Add profile', 'button');
  await page.waitForSelector('[role="dialog"] input', { visible: true });
  assert.equal(await page.$eval('[role="dialog"]', (el) => {
    const box = el.getBoundingClientRect(); return box.top >= 0 && box.bottom <= window.innerHeight && el.contains(document.activeElement);
  }), true);
  assert.doesNotMatch(await page.$eval('[role="dialog"]', (el) => el.innerText), /Arguments|Timeout|Command|Install|Set it up/);
  await page.type('[role="dialog"] input', 'scout');
  await page.type('[role="dialog"] textarea', 'Compare vendors and cite public sources.');
  await selectProvider(page, 'Claude Code');
  await page.type('[role="dialog"] .MuiAutocomplete-input', 'sonnet');
  await clickText(page, 'Save', 'button');
  await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
  assert.equal(writes[1].name, 'scout');
  assert.equal(writes[1].update.provider, 'cli:claude');
  assert.equal(writes[1].update.model, 'sonnet');
  assert.equal(writes[1].update.triage_enabled, true);
  assert.equal(writes[1].update.cmd, undefined);
  await page.waitForFunction(() => document.body.innerText.includes('SCOUT.md'));
  await clickText(page, 'Manage profiles', 'button');
  await page.waitForSelector('[data-profile="researcher"]');
  assert.doesNotMatch(await page.evaluate(() => document.body.innerText), /Set it up|Edit command|Install|--verbose|Devin CLI/);
  await page.evaluate(() => [...document.querySelectorAll('[data-profile="researcher"] button')].find((el) => el.textContent === 'Edit').click());
  await page.waitForSelector('[role="dialog"]');
  await selectProvider(page, 'OpenAI Codex CLI');
  await page.type('[role="dialog"] .MuiAutocomplete-input', 'test-codex-model');
  await page.screenshot({ path: '../.codex-tmp/profile-editor.png', fullPage: true });
  await clickText(page, 'Save', 'button');
  await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
  assert.equal(writes.length, 3);
  assert.equal(writes[2].name, 'researcher');
  assert.equal(writes[2].update.provider, 'cli:codex');
  assert.equal(writes[2].update.model, 'test-codex-model');
  assert.equal(writes[2].update.purpose, 'Research public information');
  assert.equal(writes[2].update.kind, 'research');
  assert.equal(profiles.coder.provider, 'cli:claude');
  assert.deepEqual(clis[0].config.args, ['-p', '--verbose']);
  await page.screenshot({ path: '../.codex-tmp/docs-profiles.png', fullPage: true });
  assert.deepEqual(errors, []); assert.deepEqual(page.fixtureEscapes, []);
});
