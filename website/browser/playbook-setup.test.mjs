import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdir } from 'node:fs/promises';
import { startHarness } from './harness.mjs';

test('Deleting a playbook is at once, keeps a failure visible, and Recently deleted brings it back', { timeout: 120000 }, async (t) => {
  const harness = await startHarness(); t.after(() => harness.close());
  const page = await harness.newPage(), deletes = [], restores = [];
  let fail = true;
  const book = { slug: 'item-report', title: 'Prepare item numbers', when: 'a request for numbers', uses: [], enabled: false };
  let books = [book], deleted = [];
  page.off('request', page.fixtureRequestGuard);
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname; let data, status = 200;
    if (path === '/api/playbooks') data = { data: books, deleted, keep_days: 30, template: '# New playbook\nwhen: a request' };
    if (path === '/api/playbooks/item-report') {
      if (request.method() === 'DELETE') {
        deletes.push(path);
        if (fail) { status = 500; data = { detail: 'The playbook file is locked.' }; }
        else { books = []; deleted = [{ slug: book.slug, title: book.title, when: book.when, days_left: 29 }]; data = { ok: true }; }
      } else data = { content: '# Prepare item numbers\nwhen: a request for numbers' };
    }
    if (path === '/api/playbooks/item-report/restore' && request.method() === 'POST') {
      restores.push(path); books = [book]; deleted = []; data = { ok: true, slug: book.slug };
    }
    if (data) return request.respond({ status, contentType: 'application/json', body: JSON.stringify(data) });
    page.fixtureRequestGuard(request);
  });
  await page.goto(`${harness.ui}#playbook=item-report`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => [...document.querySelectorAll('textarea')].some((el) => el.value.includes('# Prepare item numbers')));
  await click(page, 'Remove');
  await page.waitForFunction(() => document.body.innerText.includes('file is locked'));
  assert.equal(deletes.length, 1, 'Delete sends at once - no confirm in between');
  assert.equal(await page.$('[role="dialog"]'), null, 'no "are you sure" dialog');
  assert.equal(await page.$$eval('textarea', (els) => els.some((el) => el.value.includes('# Prepare item numbers'))), true,
    'a failed delete leaves the words open');
  fail = false;
  await click(page, 'Remove');
  await page.waitForSelector('[data-tq-playbook-deleted="item-report"]');
  assert.equal(deletes.length, 2);
  assert.equal(await page.$('[role="dialog"]'), null);
  assert.equal(await page.$('[data-tq-playbook="item-report"]'), null, 'it leaves the list');
  assert.match(await page.evaluate(() => document.body.innerText), /No playbooks yet/, 'the emptied shelf still says so above Recently deleted');
  assert.match(await page.$eval('[data-tq-playbooks-deleted]', (el) => el.innerText), /Recently deleted[\s\S]*Prepare item numbers[\s\S]*29 days/);
  await click(page, 'Restore');
  await page.waitForSelector('[data-tq-playbook="item-report"]');
  assert.deepEqual(restores, ['/api/playbooks/item-report/restore']);
  assert.equal(await page.$('[data-tq-playbooks-deleted]'), null, 'Recently deleted empties when nothing is in it');
  assert.equal(await page.$eval('[data-tq-playbook="item-report"] input[type="checkbox"]', (el) => el.checked), false,
    'it comes back as it was - still switched off');
});

async function click(page, label, exact = true) {
  await page.waitForFunction(({ label, exact }) => [...document.querySelectorAll('button')].some((b) =>
    !b.disabled && (exact ? b.textContent.trim() === label : b.textContent.includes(label))), {}, { label, exact });
  await page.evaluate(({ label, exact }) => [...document.querySelectorAll('button')].find((b) =>
    !b.disabled && (exact ? b.textContent.trim() === label : b.textContent.includes(label))).click(), { label, exact });
}

test('New playbook offers optional historical email, starts AI, and preserves connector context', { timeout: 120000 }, async (t) => {
  const harness = await startHarness(); t.after(() => harness.close());
  const page = await harness.newPage(), writes = [], errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  let unavailable = false;
  const historical = { MessageId: 41, Subject: 'Updated item X numbers', FromName: 'Alex', FromEmail: 'alex@example.test',
    SentAt: '2020-01-01', BodyText: 'Please prepare the new numbers for item X.' };
  const task = { TaskId: 9001, Title: 'Create playbook', Kind: 'general', Status: 'open', SourceRef: 'assistant:playbook' };
  page.off('request', page.fixtureRequestGuard);
  page.on('request', (request) => {
    const url = new URL(request.url()); let data, status = 200;
    if (url.pathname === '/api/playbooks') data = { data: [], template: '# New\nwhen: a request\nuses: sample (read)' };
    if (url.pathname === '/api/playbooks/examples') data = { data: url.searchParams.get('q') === 'missing' ? [] : [historical], next: null };
    if (url.pathname === '/api/playbooks/setup') {
      writes.push(JSON.parse(request.postData()));
      data = unavailable ? { detail: 'Connect an AI provider in Connections first.' } : { taskId: task.TaskId, task };
      status = unavailable ? 422 : 200;
    }
    if (url.pathname === '/api/tasks/9001/assistant') data = { messages: [{ id: 'first', role: 'assistant',
      content: [{ type: 'text', text: 'Which connected system holds the latest numbers?' }] }], providers: [], session: null };
    if (data) return request.respond({ status, contentType: 'application/json', body: JSON.stringify(data) });
    page.fixtureRequestGuard(request);
  });
  // Playbooks live on the Reports page (Reports / Workflows / Playbooks), their own New playbook on the shelf
  await page.goto(`${harness.ui}#report=playbooks`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.body.innerText.includes('No playbooks yet'));
  assert.equal(await page.$('[role="dialog"]'), null, 'Opening the shelf does not start setup');
  await click(page, 'New playbook');
  await page.waitForSelector('[role="dialog"]');
  assert.match(await page.$eval('[role="dialog"]', (el) => el.innerText), /Use a past email/);
  await click(page, 'Use a past email', false);
  await click(page, historical.Subject, false);
  assert.match(await page.$eval('[role="dialog"]', (el) => el.innerText), /Please prepare the new numbers/);
  await mkdir('../.codex-tmp', { recursive: true });
  await page.screenshot({ path: '../.codex-tmp/playbook-email-setup.png', fullPage: true });
  await click(page, 'Set up with AI');
  await page.waitForFunction(() => document.querySelector('[role="dialog"]')?.innerText.includes('Which connected system'));
  assert.deepEqual(writes[0], { text: '', message_id: 41, connector_type: '' });
  await click(page, 'Close'); await page.waitForSelector('[role="dialog"]', { hidden: true });

  await click(page, 'New playbook'); await click(page, 'Use a past email', false);
  await page.type('[role="dialog"] input', 'missing');
  await page.waitForFunction(() => document.body.innerText.includes('No emails match'));
  await click(page, 'Start from scratch', false);
  await page.type('[role="dialog"] textarea', 'Prepare a weekly item report');
  unavailable = true;
  await click(page, 'Set up with AI');
  await page.waitForFunction(() => document.body.innerText.includes('Connect an AI provider'));
  assert.deepEqual(writes[1], { text: 'Prepare a weekly item report', message_id: null, connector_type: '' });
  assert.equal(await page.$eval('[role="dialog"] textarea', (el) => el.value), 'Prepare a weekly item report');
  await click(page, 'Cancel'); await page.waitForSelector('[role="dialog"]', { hidden: true });

  await page.evaluate(() => { window.location.hash = 'playbook=new:quickbooks'; });
  await page.waitForFunction(() => document.querySelector('[role="dialog"]')?.innerText.includes('For your quickbooks connection'));
  await click(page, 'Start from scratch', false);
  await page.type('[role="dialog"] textarea', 'Prepare weekly numbers');
  unavailable = false;
  await click(page, 'Set up with AI');
  await page.waitForFunction(() => document.querySelector('[role="dialog"]')?.innerText.includes('Which connected system'));
  assert.equal(writes[2].connector_type, 'quickbooks');
  await click(page, 'Close'); await page.waitForSelector('[role="dialog"]', { hidden: true });
  await page.setViewport({ width: 390, height: 844 });
  await click(page, 'New playbook'); await click(page, 'Start from scratch', false);
  assert.equal(await page.$eval('[role="dialog"]', (el) => {
    const r = el.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight;
  }), true);
  await page.screenshot({ path: '../.codex-tmp/playbook-setup-mobile.png', fullPage: true });
  await click(page, 'Write manually');
  await page.waitForSelector('[role="dialog"]', { hidden: true });
  assert.equal(writes.length, 3);
  assert.deepEqual(errors, []);
});
