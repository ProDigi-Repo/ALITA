const { chromium } = require('playwright');
(async () => {
  const [port, tag] = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.addInitScript(() => { window.requestAnimationFrame = () => 0; });
  await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  const snap = async step => {
    await page.waitForTimeout(700);
    const s = await page.evaluate(() => ({
      db: [...SEL_DB], dbs: [...DATABASES], sels: [...CV.sels], cg: { sel: CG.sel, proj: CG.proj }, unlocked: DB_UNLOCKED,
      rCluster: (document.querySelector('#rCluster') || {}).value, rOpts: document.querySelectorAll('#rCluster option').length,
      rag: (document.querySelector('#ragPsum') || {}).textContent, graph: (document.querySelector('#graphPsum') || {}).textContent,
      rows: document.querySelectorAll('#docTable tbody tr, table tbody tr').length,
      bar: (document.querySelector('#dbs') || {}).textContent, legend: (document.querySelector('#cgLegend') || {}).textContent,
      clusterList: (document.querySelector('#page-graph .bq-cluster') || {}).textContent?.replace(/\s+/g, ' ').slice(0, 400),
      cviz: (document.querySelector('#cviz') || {}).textContent?.replace(/\s+/g, ' ').slice(0, 300),
      tabs: [...document.querySelectorAll('[role=tab]')].filter(b => !b.hidden).map(b => b.id),
    }));
    await page.screenshot({ path: `${process.env.OUT_DIR || '.'}/i-${tag}-${step}.png` });
    return [step, s];
  };
  const out = [];
  out.push(await snap('0-start'));
  await page.fill('#dbPass', 'password'); await page.press('#dbPass', 'Enter'); out.push(await snap('1-unlock'));
  await page.click('#dbs .db[data-db="WACHTER"]'); out.push(await snap('2-db-wachter'));
  await page.click('#dbs .db[data-db="EUAIA"]'); out.push(await snap('3-db-euaia'));
  await page.evaluate(() => cgPick(3)); out.push(await snap('4-cgpick3'));
  await page.evaluate(() => cgPick(1)); out.push(await snap('5-cgpick1'));
  await page.selectOption('#cgCompare', 'EUAIA|WACHTER'); out.push(await snap('6-compare'));
  await page.evaluate(() => { const l = { a: 1, b: 3 }; xcSelect(l) }); out.push(await snap('7-xcselect'));
  await page.click('#tab-chat'); await page.evaluate(() => { const r = document.querySelector('#rCluster'); r.value = '2'; r.dispatchEvent(new Event('change')); }); out.push(await snap('8-rcluster'));
  await page.evaluate(() => cvClear()); out.push(await snap('9-clear'));
  await page.click('#tab-graph'); await page.evaluate(() => clearAllSel()); out.push(await snap('10-clearall'));
  await page.click('#dbLock'); out.push(await snap('11-lock'));
  console.log(JSON.stringify({ out, errors }));
  await browser.close();
})();
