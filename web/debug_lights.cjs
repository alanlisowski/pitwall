const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1400, height: 900 });

  page.on('console', msg => {
    const t = msg.text();
    if (t.includes('error') || t.includes('Error')) process.stdout.write(`[ERR] ${t}\n`);
  });

  await page.route('**/race/**', async route => {
    const url = route.request().url();
    const resp = await route.fetch();
    const body = await resp.json();
    if (url.includes('/start')) {
      process.stdout.write(`[START] state.lap=${body.state?.lap}\n`);
    } else if (url.includes('/advance')) {
      process.stdout.write(`[ADVANCE] lap=${body.lap} events=${JSON.stringify(body.events?.map(e=>e.kind))}\n`);
    }
    await route.fulfill({ json: body });
  });

  await page.goto('http://localhost:5175');
  console.log('Page loaded');
  
  // Wait longer for the app to fully load
  await page.waitForLoadState('networkidle', { timeout: 10000 });
  console.log('Network idle');

  await page.screenshot({ path: '/tmp/pw_loaded.png' });
  
  // Check for select
  const select = await page.$('select');
  if (!select) {
    console.log('No select found, taking screenshot...');
    await page.screenshot({ path: '/tmp/pw_noselect.png' });
    const html = await page.content();
    process.stdout.write(`[HTML] ${html.substring(0, 500)}\n`);
  } else {
    console.log('Select found');
    await page.selectOption('select', { index: 1 });
    await page.waitForTimeout(500);
    await page.click('button:has-text("RACE")');
    await page.waitForTimeout(300);
    await page.click('button:has-text("VER")');
    await page.waitForTimeout(200);
    await page.click('button:has-text("START RACE")');
    console.log('Clicked START RACE');

    await page.waitForSelector('text=FORMATION LAP', { timeout: 10000 });
    console.log('Lights phase started');

    await page.waitForSelector('text=LIGHTS OUT', { timeout: 15000 });
    console.log('Lights went out');
    await page.screenshot({ path: '/tmp/pw_lights_out.png' });

    await page.waitForTimeout(1500);

    const lapDisplay = await page.evaluate(() => {
      const spans = document.querySelectorAll('span');
      for (const span of spans) {
        if (span.textContent?.trim() === 'LAP') {
          const lapNum = span.nextElementSibling?.textContent?.trim();
          const total = span.nextElementSibling?.nextElementSibling?.textContent?.trim();
          return `LAP ${lapNum} ${total}`;
        }
      }
      return 'not found';
    });
    console.log('Lap display after 1.5s:', lapDisplay);
    await page.screenshot({ path: '/tmp/pw_racing.png' });
  }

  await browser.close();
  console.log('Done');
})().catch(e => { console.error(e.message.split('\n')[0]); process.exit(1); });
