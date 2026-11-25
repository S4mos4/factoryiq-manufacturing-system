import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

const baseURL = process.env.FACTORYIQ_E2E_URL || 'http://127.0.0.1:8000';
const token = process.env.FACTORYIQ_OPERATOR_TOKEN;
if (!token) throw new Error('Set FACTORYIQ_OPERATOR_TOKEN for a disposable synthetic instance.');
const shots = new URL('../docs/screenshots/',import.meta.url).pathname;
const videos = new URL('../work/demo-video/',import.meta.url).pathname;
await mkdir(videos,{recursive:true});

const browser = await chromium.launch();
const context = await browser.newContext({baseURL,viewport:{width:1440,height:1050},reducedMotion:'reduce',
  recordVideo:{dir:videos,size:{width:1440,height:1050}}});
const page = await context.newPage();
const errors = [];
page.on('pageerror',error=>errors.push(error.message));

async function command(fault) {
  const response = await context.request.post('/api/iot/devices/sim-sorter/simulation',{
    headers:{Authorization:'Bearer '+token},data:{fault,duration_seconds:30},
  });
  if (!response.ok()) throw new Error('Synthetic command returned HTTP '+response.status());
}

try {
  await page.goto('/');
  await page.getByRole('navigation').getByRole('button',{name:'Live monitoring'}).click();
  const sorter = page.getByRole('button',{name:/Vision sorter/});
  await sorter.getByText('Running',{exact:true}).waitFor();
  await page.getByRole('heading',{name:'Manufacturing performance'}).waitFor();
  await page.screenshot({path:shots+'v2-live-monitoring.png'});
  await page.waitForTimeout(1500);
  await sorter.click();
  await command('overheat');
  await sorter.getByText('Fault',{exact:true}).waitFor();
  await page.waitForTimeout(1400);
  const alarms = page.getByRole('heading',{name:'Active alarms',exact:true});
  await alarms.scrollIntoViewIfNeeded();
  await page.getByRole('row').filter({hasText:'Overheat'}).first().waitFor();
  await page.screenshot({path:shots+'v2-fault-monitoring.png'});
  await page.waitForTimeout(2000);
  await command('normal');
  const twin = page.getByRole('region',{name:'Digital twin'});
  await twin.scrollIntoViewIfNeeded();
  await sorter.getByText('Running',{exact:true}).waitFor();
  await page.waitForTimeout(1800);
  await context.close();
  await page.video().saveAs(videos+'factoryiq-v2-demo.webm');
  if (errors.length) throw new Error(errors.join('\n'));
} finally {
  await command('normal').catch(()=>undefined);
  await browser.close();
}
