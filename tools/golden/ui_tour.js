const { chromium } = require('playwright');
(async () => {
  const [port] = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = []; page.on('pageerror', e => errors.push(String(e)));
  await page.goto(`http://127.0.0.1:${port}/?tour=1`, { waitUntil: 'networkidle' }); await page.waitForTimeout(2000);
  const heads = [];
  for (let i = 0; i < 14; i++) {
    const h = await page.evaluate(() => { const e = document.querySelector('.tour-head'); return e ? e.textContent.replace(/\s+/g, ' ').trim() : null });
    if (!h) break; heads.push(h);
    const next = await page.$('.tour-next'); if (!next) break;
    await next.click(); await page.waitForTimeout(700);
  }
  console.log(JSON.stringify({ steps: heads.length, heads, errors }));
  await browser.close();
})();
