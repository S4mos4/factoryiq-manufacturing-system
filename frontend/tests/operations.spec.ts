import { expect, test, type Page } from '@playwright/test';
import { randomUUID } from 'node:crypto';

const runId = randomUUID().slice(0,8);

async function unlock(page:Page) {
  const token=process.env.FACTORYIQ_OPERATOR_TOKEN;
  if (!token) throw new Error('Set FACTORYIQ_OPERATOR_TOKEN for the dedicated end-to-end instance.');
  await page.goto('/');
  await page.getByRole('button',{name:'Operator access'}).click();
  await page.getByLabel('Operator token').fill(token);
  await page.getByRole('button',{name:'Unlock'}).click();
  await expect(page.getByRole('button',{name:'Lock operator'})).toBeVisible();
}

function nav(page:Page,name:string) {
  return page.getByRole('navigation').getByRole('button',{name,exact:true}).click();
}

test('overview uses equipment and date filters, and mobile navigation is usable', async ({page})=>{
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'Operational health'})).toBeVisible();
  await expect(page.getByText('Synthetic data',{exact:true}).first()).toBeVisible();
  await page.getByLabel('Filter equipment').selectOption('1');
  await page.getByRole('button',{name:'Apply'}).click();
  await expect(page.locator('.kpi').first().locator('strong')).toHaveText('1');
  await page.getByRole('button',{name:'Collapse sidebar'}).click();
  await expect(page.getByRole('button',{name:'Expand sidebar'})).toBeVisible();
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:'Open menu'}).click();
  await nav(page,'Equipment');
  await expect(page.getByRole('heading',{name:'Equipment registry'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('register and edit equipment, then search for the saved record', async ({page})=>{
  await unlock(page);
  await nav(page,'Equipment');
  await page.getByRole('button',{name:'Register equipment'}).click();
  let dialog=page.getByRole('dialog');
  const code='E2E-'+runId;
  await dialog.getByLabel('Equipment code').fill(code);
  await dialog.getByLabel('Equipment name').fill('E2E inspection cell');
  await dialog.getByLabel('Equipment type').selectOption('2');
  await dialog.getByLabel('Facility location').selectOption('1');
  await dialog.getByRole('button',{name:'Save'}).click();
  await expect(page.getByText('Register equipment saved.',{exact:true})).toBeVisible();
  await page.getByRole('textbox',{name:'Search records'}).fill(code);
  const row=page.getByRole('row').filter({hasText:code});
  await expect(row).toContainText('Operational');
  await row.getByRole('button',{name:'Edit'}).click();
  dialog=page.getByRole('dialog');
  await dialog.getByLabel('Status').selectOption('maintenance');
  await dialog.getByRole('button',{name:'Save'}).click();
  await expect(row).toContainText('Maintenance');
});

test('receive, reserve, and consume stock with confirmation and ledger history', async ({page})=>{
  await unlock(page);
  await nav(page,'Inventory');
  await page.getByRole('textbox',{name:'Search records'}).fill('PT-1000');
  await page.getByRole('row').filter({hasText:'PT-1000'}).getByRole('button',{name:'View'}).click();
  const detail=page.getByRole('dialog',{name:/PT-1000/});
  await detail.getByRole('button',{name:'Receive stock'}).click();
  let dialog=page.getByRole('dialog',{name:'Receive stock'});
  await dialog.getByLabel('Quantity').fill('2');
  await dialog.getByLabel('Notes').fill('E2E receipt '+runId);
  await dialog.getByRole('button',{name:'Save'}).click();
  await expect(detail.getByText('E2E receipt '+runId)).toBeVisible();
  await detail.getByRole('button',{name:'Reserve stock'}).click();
  dialog=page.getByRole('dialog',{name:'Reserve stock'});
  await dialog.getByLabel('Production batch').selectOption('1');
  await dialog.getByRole('button',{name:'Save'}).click();
  await detail.getByRole('button',{name:'Consume',exact:true}).first().click();
  await page.getByRole('dialog',{name:'Consume reservation'}).getByRole('button',{name:'Confirm'}).click();
  await expect(detail.getByRole('row').filter({hasText:'consume'}).first()).toBeVisible();
  await expect(detail.getByRole('button',{name:'Consume',exact:true})).toHaveCount(0);
});

test('record a passing inspection and schedule preventive maintenance', async ({page})=>{
  await unlock(page);
  await nav(page,'Quality inspections');
  await page.getByRole('button',{name:'Record inspection'}).click();
  const inspection=page.getByRole('dialog',{name:'Record inspection'});
  await inspection.getByLabel('Part',{exact:true}).selectOption('1');
  await inspection.getByLabel('Production batch').selectOption('1');
  await inspection.getByLabel('Measurement 1 characteristic').fill('E2E bore');
  await inspection.getByLabel('Measurement 1 value').fill('10');
  await inspection.getByLabel('Measurement 1 lower limit').fill('9.9');
  await inspection.getByLabel('Measurement 1 upper limit').fill('10.1');
  await inspection.getByRole('button',{name:'Record inspection'}).click();
  await expect(page.getByText('Inspection recorded.',{exact:true})).toBeVisible();
  await expect(page.getByRole('row').filter({hasText:'LOT-2400'}).first()).toContainText('Passed');
  await nav(page,'Maintenance');
  await page.getByRole('button',{name:'Schedule work order'}).click();
  const work=page.getByRole('dialog',{name:'Schedule work order'});
  await work.getByLabel('Equipment',{exact:true}).selectOption('1');
  await work.getByLabel('Work order title').fill('E2E preventive service '+runId);
  await work.getByRole('button',{name:'Save'}).click();
  await expect(page.getByText('Schedule work order saved.',{exact:true})).toBeVisible();
  await page.getByRole('textbox',{name:'Search records'}).fill('E2E preventive service '+runId);
  await expect(page.getByRole('row').filter({hasText:'E2E preventive service '+runId})).toContainText('Scheduled');
});

test('import a trace, recognize a repeat, and download a CSV report', async ({page})=>{
  await unlock(page);
  await nav(page,'Sorter events');
  const stamp = new Date().toISOString().slice(0,16);
  for(const expected of ['trace rows imported','Duplicate trace recognized']){
    await page.getByRole('button',{name:'Import trace'}).click();
    const dialog=page.getByRole('dialog',{name:'Import sorter trace'});
    await dialog.getByLabel('Equipment',{exact:true}).selectOption('5');
    await dialog.getByLabel('Run start (local time)').fill(stamp);
    await dialog.getByLabel('CSV trace').setInputFiles({name:'e2e-'+runId+'.csv',mimeType:'text/csv',
      buffer:Buffer.from('time_ms,event,lane\n0,ENTRY,A\n1000,TICK,\n2000,EXIT,A\n'+(2001+parseInt(runId.slice(0,6),16))+',TICK,\n')});
    await dialog.getByRole('button',{name:'Import',exact:true}).click();
    await expect(page.getByText(expected,{exact:false})).toBeVisible();
  }
  await nav(page,'Reports');
  const pending=page.waitForEvent('download');
  await page.getByRole('article').filter({hasText:'Equipment register'}).getByRole('button',{name:'Download CSV'}).click();
  expect((await pending).suggestedFilename()).toBe('factoryiq-equipment.csv');
});

test('assign and complete a corrective action, then close the report', async ({page})=>{
  await unlock(page);
  await nav(page,'Non-conformances');
  await page.getByRole('button',{name:'Open report'}).click();
  const title='E2E issue '+runId;
  let form=page.getByRole('dialog',{name:'Open non-conformance'});
  await form.getByLabel('Equipment',{exact:true}).selectOption('1');
  await form.getByLabel('Title',{exact:true}).fill(title);
  await form.getByLabel('Description').fill('Perform first-article verification.');
  await form.getByRole('button',{name:'Save'}).click();
  await expect(page.getByText('Open non-conformance saved.',{exact:true})).toBeVisible();
  await page.getByRole('textbox',{name:'Search records'}).fill(title);
  await page.getByRole('row').filter({hasText:title}).getByRole('button',{name:'View'}).click();
  const detail=page.getByRole('dialog',{name:title});
  await detail.getByRole('button',{name:'Assign action'}).click();
  form=page.getByRole('dialog',{name:'Assign corrective action'});
  await form.getByLabel('Action title').fill('Verify fixture setting');
  await form.getByLabel('Owner',{exact:true}).selectOption('1');
  await form.getByRole('button',{name:'Save'}).click();
  await detail.getByRole('button',{name:'Complete',exact:true}).click();
  await page.getByRole('dialog',{name:'Complete action'}).getByRole('button',{name:'Confirm'}).click();
  await expect(detail.getByText('Done',{exact:true})).toBeVisible();
  await detail.getByRole('button',{name:'Close report'}).click();
  await page.getByRole('dialog',{name:'Close report'}).getByRole('button',{name:'Confirm'}).click();
  await expect(detail.getByText('Closed',{exact:true})).toBeVisible();
  await expect(detail.getByText('status_changed',{exact:true})).toBeVisible();
});
