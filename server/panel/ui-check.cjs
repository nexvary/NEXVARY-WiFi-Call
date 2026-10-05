'use strict';
// Browser checks against an ephemeral local panel and a generated test-only credential.
const assert = require('node:assert/strict');
const { spawn, spawnSync } = require('node:child_process');
const { randomBytes } = require('node:crypto');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { chromium } = require('playwright');

async function startPanel(stateDirectory) {
  const code = [
    'import sys',
    'sys.path.insert(0, sys.argv[1])',
    'from app import PanelServer',
    'server = PanelServer(("127.0.0.1", 0), sys.argv[2])',
    'print(server.server_port, flush=True)',
    'server.serve_forever()'
  ].join('\n');
  const child = spawn('python3', ['-u', '-c', code, __dirname, stateDirectory], { stdio: ['ignore', 'pipe', 'pipe'] });
  try {
    const port = await new Promise((resolve, reject) => {
      let output = '';
      let errors = '';
      const timer = setTimeout(() => reject(new Error(`Panel startup timed out: ${errors}`)), 10000);
      child.stderr.on('data', chunk => { errors += chunk.toString(); });
      child.on('error', error => { clearTimeout(timer); reject(error); });
      child.on('exit', status => { clearTimeout(timer); reject(new Error(`Panel exited (${status}): ${errors}`)); });
      child.stdout.on('data', chunk => {
        output += chunk.toString();
        const match = output.match(/^(\d+)\n/);
        if (match) { clearTimeout(timer); resolve(Number(match[1])); }
      });
    });
    return { child, url: `http://127.0.0.1:${port}` };
  } catch (error) {
    child.kill('SIGTERM');
    throw error;
  }
}

async function waitVisible(locator) { await locator.waitFor({ state: 'visible' }); }
async function assertNoHorizontalOverflow(page) {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true,
    'Panel must fit the viewport without horizontal scrolling');
}

(async () => {
  const stateDirectory = await fs.mkdtemp(path.join(os.tmpdir(), 'nexvary-panel-ui-'));
  const screenshotDirectory = path.resolve('panel-ui-screenshots');
  await fs.mkdir(screenshotDirectory, { recursive: true });
  const password = randomBytes(24).toString('base64url');
  const init = spawnSync('python3', ['-c', [
    'import json, secrets, sys',
    'from pathlib import Path',
    'sys.path.insert(0, sys.argv[1])',
    'from app import password_hash',
    'password = json.load(sys.stdin)["password"]',
    'salt = secrets.token_hex(16)',
    'Path(sys.argv[2], "password.json").write_text(json.dumps(dict(salt=salt, hash=password_hash(password, salt))))'
  ].join('\n'), __dirname, stateDirectory], { input: JSON.stringify({ password }), encoding: 'utf8' });
  if (init.status !== 0) throw new Error(`Unable to initialize test credential: ${init.stderr}`);
  let panel;
  let browser;
  try {
    panel = await startPanel(stateDirectory);
    browser = await chromium.launch({ headless: true });
    for (const [name, viewport] of [['desktop', { width: 1280, height: 900 }], ['mobile', { width: 390, height: 844 }]]) {
      const context = await browser.newContext({ viewport, locale: 'ar-EG' });
      context.setDefaultTimeout(15000);
      context.setDefaultNavigationTimeout(15000);
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(panel.url);
      await waitVisible(page.locator('#login'));
      assert.equal(await page.locator('#dashboard').isVisible(), false);
      await assertNoHorizontalOverflow(page);
      await page.screenshot({ path: path.join(screenshotDirectory, `${name}-login.png`), fullPage: true });
      await page.locator('#password').fill('intentionally-wrong-test-password');
      await page.locator('#submit').click();
      await page.locator('#error').filter({ hasText: 'كلمة المرور غير صحيحة.' }).waitFor();
      assert.equal(await page.locator('#dashboard').isVisible(), false);
      await page.locator('#password').fill(password);
      await page.locator('#submit').click();
      await waitVisible(page.locator('#dashboard'));
      assert.equal(await page.locator('#login').isVisible(), false);
      assert.equal(await page.locator('#password').inputValue(), '', 'Credential must be cleared from the form');
      assert.equal(await page.locator('#metrics > .card').count(), 4);
      assert.equal(await page.locator('#stages > .stage').count(), 8);
      assert.deepEqual(await page.locator('#stages .pill').allTextContents(), Array(8).fill('لم يُختبر'));
      assert.equal(await page.locator('.warning').isVisible(), true);
      const status = await context.request.get(`${panel.url}/api/status`);
      assert.equal(status.status(), 200);
      const data = await status.json();
      assert.equal(data.gateway_installed, false);
      assert(data.stages.every(stage => stage.status === 'not_tested' && stage.evidence === null));
      await assertNoHorizontalOverflow(page);
      await page.screenshot({ path: path.join(screenshotDirectory, `${name}-dashboard.png`), fullPage: true });
      const refreshed = page.waitForResponse(response => response.url().endsWith('/api/status') && response.status() === 200);
      await page.locator('#refresh').click();
      await refreshed;
      await page.locator('#refreshState').filter({ hasText: 'آخر تحديث:' }).waitFor();
      assert.equal(await page.locator('#refresh').isEnabled(), true);
      await page.locator('#logout').click();
      await waitVisible(page.locator('#login'));
      assert.equal(await page.locator('#dashboard').isVisible(), false);
      assert.equal((await context.request.get(`${panel.url}/api/status`)).status(), 401);
      assert.deepEqual(errors, [], 'Browser must not emit script errors');
      await context.close();
      console.log(`PASS ${name}: login, metrics, 8 unverified stages, refresh, logout, viewport fit`);
    }
  } finally {
    if (browser) await browser.close();
    if (panel) panel.child.kill('SIGTERM');
    await fs.rm(stateDirectory, { recursive: true, force: true });
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
