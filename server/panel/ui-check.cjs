'use strict';
// Browser checks against an ephemeral local panel and a generated test-only credential.
const assert = require('node:assert/strict');
const { spawn, spawnSync } = require('node:child_process');
const { randomBytes } = require('node:crypto');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { chromium, request } = require('playwright');
const jsQR = require('jsqr');

async function startPanel(stateDirectory, httpsFixture = false) {
  const code = [
    'import sys',
    'sys.path.insert(0, sys.argv[1])',
    'from app import PanelServer',
    'server = PanelServer(("127.0.0.1", 0), sys.argv[2])',
    'if sys.argv[3] == "https":',
    '    import ssl',
    '    from pathlib import Path',
    '    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)',
    '    context.load_cert_chain(str(Path(sys.argv[2]) / "fixture-cert.pem"), str(Path(sys.argv[2]) / "fixture-key.pem"))',
    '    server.socket = context.wrap_socket(server.socket, server_side=True)',
    '    server.public_origin = "https://127.0.0.1:" + str(server.server_port)',
    'print(server.server_port, flush=True)',
    'server.serve_forever()'
  ].join('\n');
  const child = spawn('python3', ['-u', '-c', code, __dirname, stateDirectory, httpsFixture ? 'https' : 'http'], { stdio: ['ignore', 'pipe', 'pipe'] });
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
    return { child, url: `${httpsFixture ? 'https' : 'http'}://127.0.0.1:${port}` };
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
  let tlsPanel;
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
      // A separate API context imitates the phone: no admin session cookie.
      await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: panel.url });
      const phone = await request.newContext({ baseURL: panel.url });
      try {
        await page.locator('#createPairing').click();
        await waitVisible(page.locator('#pairingBox'));
        const pairingCode = await page.locator('#pairingCode').textContent();
        assert(pairingCode && pairingCode.length > 0);
        assert.equal(await page.locator('#pairingQrArea').isVisible(), false, 'HTTP must not produce a pairing QR');
        assert((await page.locator('#pairingQrNotice').textContent()).includes('HTTPS'));
        await page.locator('#copyPairing').click();
        await page.locator('#pairingMessage').filter({ hasText: 'تم نسخ رمز الربط.' }).waitFor();
        assert.equal(await page.evaluate(() => navigator.clipboard.readText()), pairingCode);
        // Force the fallback clipboard branch as well as native Clipboard API success.
        await page.evaluate(() => { window.ciClipboard = navigator.clipboard; Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined }); });
        await page.locator('#copyPairing').click();
        await page.locator('#pairingMessage').filter({ hasText: 'تم نسخ رمز الربط.' }).waitFor();
        assert.equal(await page.evaluate(() => window.ciClipboard.readText()), pairingCode);
        const paired = await phone.post('/api/phone/pair', { data: { code: pairingCode } });
        assert.equal(paired.status(), 200);
        const auth = await paired.json();
        assert(auth.device_id && auth.token);
        const reuse = await phone.post('/api/phone/pair', { data: { code: pairingCode } });
        assert([401, 403].includes(reuse.status()), 'Pairing code must be one-use');
        await page.locator('#refresh').click();
        await waitVisible(page.locator('#phones .pill[data-status="awaiting"]'));
        const report = { schema_version: 1, sim_count: 2, selected_slot: 0, network: 'WIFI',
          phone_as_sim: 'CARRIER_PRIVILEGE_REQUIRED', app_version: '0.4.0-alpha01', android_api: 35 };
        const sent = await phone.post('/api/phone/report', { data: report, headers: { Authorization: `Bearer ${auth.token}` } });
        assert.equal(sent.status(), 200);
        await page.locator('#refresh').click();
        const card = page.locator('#phones .phone-card');
        await waitVisible(card.locator('.pill[data-status="online"]'));
        assert.equal(await card.count(), 1);
        assert((await card.textContent()).includes('0.4.0-alpha01'));
        assert((await card.textContent()).includes('SIM 1'));
        assert((await card.textContent()).includes('تحتاج إلى صلاحيات من شركة الاتصالات'));
        assert(!(await page.content()).includes(auth.token), 'Phone bearer token must never enter the DOM');
        assert.deepEqual(await page.locator('#stages .pill').allTextContents(), Array(8).fill('لم يُختبر'));
        // Mark the synthetic phone data in the review artifact.
        await page.evaluate(() => { const note = document.createElement('p'); note.id = 'ci-fixture-notice';
          note.textContent = 'بيانات هاتف اختبار CI فقط — ليست نتيجة من هاتف المستخدم';
          document.getElementById('phonesSection').prepend(note); });
        await assertNoHorizontalOverflow(page);
        await page.screenshot({ path: path.join(screenshotDirectory, `${name}-phone-report-ci-fixture.png`), fullPage: true });
        // Exercise receipt-age status without claiming carrier readiness.
        await page.evaluate(() => freshness(document.querySelector('#phones .pill'), Date.now() / 1000 - 121));
        assert.equal(await card.locator('.pill').getAttribute('data-status'), 'stale');
        assert.equal(await card.locator('.pill').textContent(), 'آخر تقرير قديم');
        await card.locator('button[data-action="revoke"]').click();
        await page.locator('#phonesMessage').filter({ hasText: 'أُلغي الربط.' }).waitFor();
        assert.equal(await page.locator('#phones .phone-card').count(), 0);
        const revoked = await phone.post('/api/phone/report', { data: report, headers: { Authorization: `Bearer ${auth.token}` } });
        assert.equal(revoked.status(), 401, 'Revocation must reject further reports');
      } finally { await phone.dispose(); }
      await page.locator('#logout').click();
      await waitVisible(page.locator('#login'));
      assert.equal(await page.locator('#dashboard').isVisible(), false);
      assert.equal((await context.request.get(`${panel.url}/api/status`)).status(), 401);
      assert.deepEqual(errors, [], 'Browser must not emit script errors');
      await context.close();
      console.log(`PASS ${name}: login, metrics, 8 unverified stages, refresh, pairing/report/revocation, logout, viewport fit`);
    }
    // TLS is fixture-only: a generated self-signed certificate and browser bypass
    // never alter production Android verification or production server settings.
    const certificate = spawnSync('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes',
      '-sha256', '-days', '1', '-subj', '/CN=127.0.0.1', '-addext', 'subjectAltName=IP:127.0.0.1',
      '-keyout', path.join(stateDirectory, 'fixture-key.pem'),
      '-out', path.join(stateDirectory, 'fixture-cert.pem')], { encoding: 'utf8' });
    if (certificate.status !== 0) throw new Error('Unable to generate isolated TLS test certificate');
    tlsPanel = await startPanel(stateDirectory, true);
    for (const [name, viewport] of [['desktop', { width: 1280, height: 900 }], ['mobile', { width: 390, height: 844 }]]) {
      const context = await browser.newContext({ viewport, locale: 'ar-EG', ignoreHTTPSErrors: true });
      context.setDefaultTimeout(15000);
      context.setDefaultNavigationTimeout(15000);
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.clock.install({ time: new Date() });
      await page.goto(tlsPanel.url);
      async function login() {
        await waitVisible(page.locator('#login'));
        await page.locator('#password').fill(password);
        await page.locator('#submit').click();
        await waitVisible(page.locator('#dashboard'));
        await page.locator('#refreshState').filter({ hasText: 'آخر تحديث:' }).waitFor();
      }
      async function createQr() {
        await page.locator('#createPairing').click();
        await waitVisible(page.locator('#pairingQrArea'));
      }
      async function assertCleared() {
        assert.equal(await page.locator('#pairingCode').textContent(), '');
        assert.equal(await page.locator('#pairingQrArea').isVisible(), false);
        assert.equal(await page.evaluate(() => [...document.getElementById('pairingQr').getContext('2d')
          .getImageData(0, 0, 256, 256).data].every(value => value === 0)), true, 'Expired QR pixels must be cleared');
      }
      await login();
      await createQr();
      const expected = { type: 'nexvary-pairing', version: 1, url: tlsPanel.url,
        code: await page.locator('#pairingCode').textContent() };
      const canvas = await page.evaluate(() => { const c = document.getElementById('pairingQr');
        return { width: c.width, height: c.height, pixels: [...c.getContext('2d').getImageData(0, 0, c.width, c.height).data] }; });
      assert.equal(canvas.width, 256);
      assert.equal(canvas.height, 256);
      for (let i = 0; i < canvas.pixels.length; i += 4) {
        const [r, g, b, a] = canvas.pixels.slice(i, i + 4);
        assert((r === 0 || r === 255) && r === g && r === b && a === 255, 'QR raster must be opaque black or white');
      }
      const decoded = jsQR(new Uint8ClampedArray(canvas.pixels), canvas.width, canvas.height);
      assert(decoded, 'An independent QR decoder must read the actual rendered canvas');
      assert.deepEqual(JSON.parse(decoded.data), expected);
      const qrSize = await page.evaluate(payload => qrcodegen.QrCode.encodeText(JSON.stringify(payload), qrcodegen.QrCode.Ecc.MEDIUM).size, expected);
      const moduleScale = Math.floor(256 / (qrSize + 8));
      const quietPixels = 4 * moduleScale;
      for (let y = 0; y < 256; y++) for (let x = 0; x < 256; x++) {
        if (x < quietPixels || x >= 256 - quietPixels || y < quietPixels || y >= 256 - quietPixels)
          assert.equal(canvas.pixels[(y * 256 + x) * 4], 255, 'QR requires at least four white quiet-zone modules');
      }
      const phone = await request.newContext({ baseURL: expected.url, ignoreHTTPSErrors: true });
      try {
        // Decode -> actual HTTPS phone pairing, with no admin cookie in this context.
        const paired = await phone.post('/api/phone/pair', { data: { code: JSON.parse(decoded.data).code } });
        assert.equal(paired.status(), 200);
        const auth = await paired.json();
        const report = { schema_version: 1, sim_count: 2, selected_slot: 0, network: 'WIFI',
          phone_as_sim: 'CARRIER_PRIVILEGE_REQUIRED', app_version: '0.4.0-alpha01', android_api: 35 };
        assert.equal((await phone.post('/api/phone/report', { data: report, headers: { Authorization: `Bearer ${auth.token}` } })).status(), 200);
        await page.locator('#refresh').click();
        await waitVisible(page.locator(`#phones [data-device-id="${auth.device_id}"] .pill[data-status="online"]`));
        assert(!(await page.content()).includes(auth.token));
        assert.deepEqual(await page.locator('#stages .pill').allTextContents(), Array(8).fill('لم يُختبر'));
        await page.evaluate(() => { const note = document.createElement('p'); note.id = 'ci-fixture-notice';
          note.textContent = 'اختبار CI فقط: HTTPS محلي بشهادة مؤقتة وبيانات هاتف اصطناعية';
          document.getElementById('phonesSection').prepend(note); });
        await assertNoHorizontalOverflow(page);
        await page.screenshot({ path: path.join(screenshotDirectory, `${name}-pairing-qr-https-ci-fixture.png`), fullPage: true });
        await page.locator(`[data-device-id="${auth.device_id}"] button[data-action="revoke"]`).click();
        await page.locator('#phonesMessage').filter({ hasText: 'أُلغي الربط.' }).waitFor();
      } finally { await phone.dispose(); }
      await page.clock.fastForward(601000);
      await page.locator('#pairingMessage').filter({ hasText: 'انتهت صلاحية رمز الربط.' }).waitFor();
      await assertCleared();
      // Restore the browser wall clock before requesting another server timestamp.
      await page.clock.setSystemTime(new Date());
      await createQr();
      await page.locator('#logout').click();
      await waitVisible(page.locator('#login'));
      await assertCleared();
      await login();
      await createQr();
      await context.clearCookies();
      await page.locator('#refresh').click();
      await waitVisible(page.locator('#login'));
      await assertCleared();
      assert.deepEqual(errors, []);
      await context.close();
      console.log(`PASS ${name} HTTPS: decoded QR -> actual pair/report, quiet zone, expiry, logout and session expiry`);
    }
  } finally {
    if (browser) await browser.close();
    if (panel) panel.child.kill('SIGTERM');
    if (tlsPanel) tlsPanel.child.kill('SIGTERM');
    await fs.rm(stateDirectory, { recursive: true, force: true });
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
