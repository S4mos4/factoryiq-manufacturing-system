import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';

const baseURL = process.env.FACTORYIQ_DEMO_URL || 'http://127.0.0.1:8000';
const output = new URL('../docs/screenshots/',import.meta.url).pathname;
const videoDirectory = new URL('../work/demo-video/',import.meta.url).pathname;
await mkdir(output,{recursive:true});
await mkdir(videoDirectory,{recursive:true});

const browser = await chromium.launch();
const context = await browser.newContext({
  baseURL, viewport:{width:1440,height:1000}, reducedMotion:'reduce',
  recordVideo:{dir:videoDirectory,size:{width:1440,height:1000}},
});
const page = await context.newPage();
const errors=[];
page.on('pageerror',error=>errors.push(error.message));
page.on('console',message=>{
  if (message.type()==='error' && !message.text().includes('favicon')) errors.push(message.text());
});
const menu = name=>page.getByRole('navigation').getByRole('button',{name,exact:true}).click();

try {
  await page.goto('/');
  await page.getByRole('heading',{name:'Operational health'}).waitFor();
  await page.locator('.recharts-bar-rectangle').first().waitFor();
  await page.screenshot({path:output+'dashboard.png'});
  await page.waitForTimeout(2300);
  await page.getByLabel('Filter equipment').selectOption('5');
  await page.getByRole('button',{name:'Apply'}).click();
  await page.locator('.kpi strong').first().filter({hasText:/^1$/}).waitFor();
  await page.waitForTimeout(1800);

  await menu('Inventory');
  await page.getByRole('textbox',{name:'Search records'}).fill('PT-1000');
  await page.getByRole('row').filter({hasText:'PT-1000'}).getByRole('button',{name:'View'}).click();
  await page.getByRole('heading',{name:'Movement history'}).waitFor();
  await page.waitForTimeout(1800);
  await page.getByRole('button',{name:'Close dialog'}).click();

  await menu('Quality inspections');
  await page.getByRole('button',{name:'Supplier defects'}).click();
  await page.getByRole('cell',{name:'Alder Precision',exact:true}).waitFor();
  await page.screenshot({path:output+'supplier-quality.png'});
  await page.waitForTimeout(1800);

  await menu('Sorter events');
  await page.getByRole('button',{name:'Faults only'}).click();
  await page.getByRole('cell',{name:'LANE_JAM',exact:true}).first().waitFor();
  await page.waitForTimeout(1800);
  await context.close();
  await page.video().saveAs(videoDirectory+'factoryiq-demo.webm');

  const mobile = await browser.newPage({baseURL,viewport:{width:390,height:844},reducedMotion:'reduce'});
  await mobile.goto('/');
  await mobile.getByRole('heading',{name:'Operational health'}).waitFor();
  await mobile.screenshot({path:output+'dashboard-mobile.png'});
  if (errors.length) throw new Error(errors.join('\n'));
} finally {
  await browser.close();
}
