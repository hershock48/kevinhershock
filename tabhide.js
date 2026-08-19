const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1200, height: 780 } });
  const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push('ERR ' + e.message));
  await p.goto('file:///home/claude/kevinhershock/index.html');
  await p.evaluate(() => { sizeGoo(); showDot(); });
  await p.waitForTimeout(300);
  await p.evaluate(() => { pool = [you]; poolDone = true; });
  await p.waitForTimeout(2600);
  await p.evaluate(() => { valveFlow = 1; wFlow = 1; });
  await p.waitForTimeout(9000);
  await p.evaluate(() => { chestOpen = true; });
  await p.evaluate(() => { if (typeof startScrew === 'function') startScrew(); });
  await p.waitForTimeout(8000);
  await p.evaluate(() => { extractDeg = 720; });
  // wait for the drain, then simulate the tab going away mid-transition by
  // stopping requestAnimationFrame entirely
  await p.waitForFunction(() => gooHanded, null, { timeout: 40000 }).catch(()=>console.log('never handed'));
  await p.evaluate(() => { window.__raf = requestAnimationFrame; window.requestAnimationFrame = () => 0; });
  console.log('rAF killed at hand-off');
  await p.waitForTimeout(12000);
  console.log(JSON.stringify(await p.evaluate(() => ({
    gooActive, travelOnly,
    finDisp: getComputedStyle(finCanvas).display,
    gooDisp: getComputedStyle(document.getElementById('goo')).display,
  }))));
  console.log('errors:', errs.length ? errs : 'none');
  await b.close();
})();
