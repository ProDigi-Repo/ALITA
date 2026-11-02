const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1600, height: 950 } });
  const errors = []; page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error' && !/status of (401|403)/.test(m.text())) errors.push(m.text()); });
  await page.addInitScript(() => { window.requestAnimationFrame = () => 0; });
  const state = async label => {
    await page.waitForTimeout(1200);
    return [label, await page.evaluate(() => ({
      dbs: [...DATABASES], account: ACCOUNT && ACCOUNT.user, tabs: [...document.querySelectorAll('[role=tab]')].filter(b => b.id && !b.hidden).map(b => b.id.slice(4)),
      docs: DOCS.length, docDbs: [...new Set(DOCS.flatMap(d => d.db))].sort(), clusters: [...new Set(DOCS.map(d => d.ci))].sort(),
      bar: [...document.querySelectorAll('#dbs .db')].map(b => b.textContent.trim().split(/\d/)[0]),
      userSel: { hidden: document.querySelector('#dbUser').hidden, disabled: document.querySelector('#dbUser').disabled, options: [...document.querySelectorAll('#dbUser option')].map(o => o.textContent) },
      pass: document.querySelector('#dbPass').placeholder, lock: !document.querySelector('#dbLock').hidden && document.querySelector('#dbLock').textContent,
      upload: !document.querySelector('#openUpload').hidden, toast: (document.querySelector('.toast') || {}).textContent }))];
  };
  const login = async (user, pw) => { await page.selectOption('#dbUser', user); await page.fill('#dbPass', pw); await page.press('#dbPass', 'Enter'); };
  const out = [];
  await page.goto('http://127.0.0.1:' + (process.argv[2]||'8703') + '/', { waitUntil: 'networkidle' }); out.push(await state('anonymous'));
  await login('charmander', 'wrong-password'); out.push(await state('wrong password'));
  await login('charmander', 'fire-secret-1'); out.push(await state('charmander'));
  await page.screenshot({ path: (process.env.OUT_DIR || '.') + '/acc-charmander.png' });
  await page.goto('http://127.0.0.1:' + (process.argv[2]||'8703') + '/#docs', { waitUntil: 'networkidle' }); out.push(await state('charmander after reload'));
  await page.screenshot({ path: (process.env.OUT_DIR || '.') + '/acc-charmander-docs.png' });
  await page.click('#dbLock'); out.push(await state('logged out'));
  await login('vulpix', 'fox-secret-22'); out.push(await state('vulpix'));
  await page.click('#dbLock'); await login('admin', 'master-password'); out.push(await state('admin'));
  await page.screenshot({ path: (process.env.OUT_DIR || '.') + '/acc-admin.png' });
  console.log(JSON.stringify({ out, errors }, null, 1)); await browser.close();
})();
