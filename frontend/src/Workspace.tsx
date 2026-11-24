import { useState, type ReactNode } from 'react';
import { ArrowUpRight, ClipboardList, Download, FileText, Plus, Upload } from 'lucide-react';
import { api, download, json, label, localStamp, text, timestamp, type RecordRow } from './api';
import { Badge, Feedback, Fields, Modal, Table, useData, type Column, type Field } from './components';

type Lookups = Record<string,RecordRow[]>;
type WorkProps = { page:string; token:string; lookup:Lookups; canWrite:boolean; version:number; refresh:()=>void };
type FormSpec = {title:string;fields:Field[];path:string;method?:string;transform?:(data:FormData)=>unknown};

const date = (key:string,title:string,initial?:string):Field=>({key,title,type:'date',initial});
const field = (key:string,title:string,type?:string,initial?:string):Field=>({key,title,type,initial});
const pick = (key:string,title:string,options:string[],initial?:string):Field=>({key,title,initial,choices:options.map(x=>[x,label(x)])});
const lookupField = (key:string,title:string,options:RecordRow[],initial?:unknown,optional=false):Field=>({
  key,title,optional,initial:initial==null?undefined:String(initial),choices:options.map(r=>[
    String(r.id),[r.code??r.sku,r.name??r.username].filter(Boolean).join(' · '),
  ]),
});
const columns=(...keys:string[]):Column[]=>keys.map(key=>({key}));
const status=(key='status'):Column=>({key,render:r=><Badge value={r[key]}/>});
const timeCol=(key:string):Column=>({key,render:r=>timestamp(r[key])});
const match = (r:RecordRow,key:string,value:unknown) => String(r[key])===String(value);

function payload(form:FormData) {
  return Object.fromEntries([...form.entries()].map(([key,value])=>[key,key.endsWith('_id')||key==='quantity'?value?Number(value):null:value]));
}

function Panel({title,children}: {title:string;children:ReactNode}) {
  return <section className="card workspace-panel"><div className="chart-heading"><h3>{title}</h3></div>{children}</section>;
}

function Detail({path,token,version,title,close,children}: {
  path:string;token:string;version:number;title:string;close:()=>void;children:(data:RecordRow)=>ReactNode;
}) {
  const {data,error}=useData<RecordRow>(path,token,version);
  return <Modal title={title} close={close}><div className="dialog-body">
    <Feedback error={error} loading={!error&&!data}/>{data&&children(data)}
  </div></Modal>;
}

function RecordList({path,token,version,cols,action,filter}: {
  path:string;token:string;version:number;cols:Column[];action?:(r:RecordRow)=>ReactNode;filter?:(r:RecordRow)=>boolean;
}) {
  const {data,error}=useData<RecordRow[]>(path,token,version);
  return <><Feedback error={error} loading={!error&&!data}/>{data&&<Table columns={cols} rows={filter?data.filter(filter):data} search action={action}/>}</>;
}

const pages:Record<string,[string,string]>={
  equipment:['Equipment registry','Manage equipment assignments, operating status, and service history.'],
  inventory:['Inventory control','Monitor available and quarantined stock, then trace every movement.'],
  inspections:['Quality inspections','Record dimensional measurements and review supplier outcomes.'],
  nonconformances:['Non-conformance management','Investigate quality issues and assign corrective actions.'],
  maintenance:['Maintenance and calibration','Schedule service, check deadlines, and record calibration results.'],
  sorter:['Sorter events','Review simulation outcomes and import millisecond-resolution traces.'],
  analytics:['SQL analytics','Inspect PostgreSQL reports for quality, reliability, and stock.'],
  reports:['CSV reports','Export operational records for offline analysis.'],
};

export function Workspace({page,token,lookup,canWrite,version,refresh}:WorkProps) {
  const [form,setForm]=useState<FormSpec>();
  const [detail,setDetail]=useState<RecordRow>();
  const [notice,setNotice]=useState('');
  const [error,setError]=useState('');
  const [filter,setFilter]=useState('');
  const [tab,setTab]=useState('');
  const [inspection,setInspection]=useState(false);
  const [importing,setImporting]=useState(false);
  const [confirm,setConfirm]=useState<{title:string;path:string;body?:RecordRow;message:string}>();
  const [title,description]=pages[page];
  const list = (path:string,cols:Column[],action?:(r:RecordRow)=>ReactNode,where?:(r:RecordRow)=>boolean) =>
    <RecordList key={path} path={path} token={token} version={version} cols={cols} action={action} filter={where}/>;
  const view = (r:RecordRow) => <button className="button secondary compact" onClick={()=>setDetail(r)}>View</button>;
  const machine=lookupField('equipment_id','Equipment',lookup.equipment);
  const today=new Date().toISOString().slice(0,10);
  const openForm=(title:string,path:string,fields:Field[],method?:string)=>setForm({title,path,fields,method});
  function equipmentForm(row?:RecordRow) {
    openForm(row?'Edit equipment':'Register equipment',row?`/equipment/${row.id}`:'/equipment',[
      field('code','Equipment code','text',row?String(row.code):undefined),field('name','Equipment name','text',row?String(row.name):undefined),
      lookupField('type_id','Equipment type',lookup.types,row?.type_id),lookupField('location_id','Facility location',lookup.locations,row?.location_id),
      pick('status','Status',['operational','maintenance','offline'],String(row?.status??'operational')),
      date('commissioned_on','Commissioned on',String(row?.commissioned_on??today)),
    ],row?'PUT':'POST');
  }
  function stockForm(operation:string) {
    if(!detail)return;
    const isReserve=operation==='reserve';
    const fields=[field('quantity','Quantity','number','1')];
    fields.push(isReserve?lookupField('batch_id','Production batch',lookup.batches.filter(b=>match(b,'part_id',detail.id)).map(b=>({...b,name:'Batch'})))
      :{key:'notes',title:operation==='reject'?'Rejection reason':'Notes',type:'textarea',optional:operation==='receive'});
    const requestId=crypto.randomUUID();
    setForm({title:label(operation)+' stock',path:`/inventory/${detail.id}/${operation}`,fields,
      transform:isReserve?data=>({...payload(data),request_id:requestId}):undefined});
  }
  function success(message:string) {setNotice(message);setError('');refresh();}
  const tabs=(items:[string,string][],active:string)=><div className="tabs" role="group" aria-label="Record type">{items.map(([key,value])=>
    <button key={key} aria-pressed={active===key} className={active===key?'active':''} onClick={()=>{setTab(key);setFilter('');}}>{value}</button>)}</div>;
  let content:ReactNode;
  let details:ReactNode;
  let create: (()=>void)|undefined;
  let createLabel='';
  if(page==='equipment') {
    create=()=>equipmentForm();createLabel='Register equipment';
    content=<Panel title="Equipment records"><div className="panel-filter"><label>Equipment status <select value={filter} onChange={e=>setFilter(e.target.value)}>
      <option value="">All statuses</option>{['operational','maintenance','offline'].map(x=><option key={x} value={x}>{label(x)}</option>)}</select></label></div>
      {list('/equipment',[...columns('code','name','type','location'),status(),...columns('commissioned_on')],
        r=><>{view(r)}{canWrite&&<button className="button secondary compact" onClick={()=>equipmentForm(r)}>Edit</button>}</>,r=>!filter||r.status===filter)}</Panel>;
    if(detail)details=<Detail title={String(detail.name)} path={'/equipment/'+detail.id} token={token} version={version} close={()=>setDetail(undefined)}>{r=><>
      <h3>Maintenance history</h3><Table columns={[...columns('title','due_on'),status()]} rows={r.maintenance as RecordRow[]}/>
      <h3>Calibration history</h3><Table columns={[...columns('reference','calibrated_on','next_due_on'),status('result')]} rows={r.calibration as RecordRow[]}/>
    </>}</Detail>;
  } else if(page==='inventory') {
    content=<Panel title="Stock by part"><div className="panel-filter"><label><input type="checkbox" checked={filter==='low'} onChange={e=>setFilter(e.target.checked?'low':'')}/> Below reorder point</label></div>
      {list('/inventory',[...columns('sku','name','supplier','usable','reserved','available','rejected','reorder_point'),
        {key:'low_stock',title:'Alert',render:r=>r.low_stock?<Badge value="low_stock"/>:'—'}],view,r=>filter!=='low'||Boolean(r.low_stock))}</Panel>;
    if(detail)details=<Detail title={String(detail.sku)+' · '+String(detail.name)} path={'/inventory/'+detail.id} token={token} version={version} close={()=>setDetail(undefined)}>{r=><>
      <div className="record-summary">{['usable','available','reserved','rejected'].map(key=><span key={key}>{label(key)} <strong>{text((r.part as RecordRow)[key])}</strong></span>)}</div>
      {canWrite&&<div className="inline-actions">{['receive','reserve','reject'].map(op=><button className="button secondary" key={op} onClick={()=>stockForm(op)}>{label(op)} stock</button>)}</div>}
      <h3>Reservations</h3><Table columns={[...columns('batch','quantity'),status()]} rows={r.reservations as RecordRow[]}
        action={canWrite?reservation=>reservation.status==='active'&&['Release','Consume'].map(op=><button key={op} className="button secondary compact"
          onClick={()=>setConfirm({title:op+' reservation',message:`${op} ${reservation.quantity} unit(s) for ${reservation.batch}?`,
          path:`/inventory/${detail.id}/reservations/${reservation.id}/${op.toLowerCase()}`})}>{op}</button>):undefined}/>
      <h3>Movement history</h3><Table columns={[...columns('kind','quantity','notes'),timeCol('occurred_at')]} rows={r.movements as RecordRow[]}/>
    </>}</Detail>;
  } else if(page==='inspections') {
    create=()=>setInspection(true);createLabel='Record inspection';
    const active=tab||'history';
    content=<Panel title="Inspection records">{tabs([['history','Inspection history'],['suppliers','Supplier defects']],active)}
      {active==='history'?list('/inspections',[...columns('batch','sku','equipment'),timeCol('inspected_at'),
        {key:'passed',title:'Result',render:r=><Badge value={r.passed?'passed':'failed'}/>},...columns('rejection_reason')],view)
        :list('/analytics/supplier_defects',columns('supplier','inspections','rejected','defect_rate'))}</Panel>;
    if(detail)details=<Detail title={'Inspection '+String(detail.id)+' · '+String(detail.batch)} path={'/inspections/'+detail.id}
      token={token} version={version} close={()=>setDetail(undefined)}>{r=><>
        <div className="record-summary"><Badge value={r.passed?'passed':'failed'}/><span>{timestamp(r.inspected_at)} UTC</span><span>{text(r.rejection_reason)}</span></div>
        <Table columns={[...columns('characteristic','unit','value','lower_limit','upper_limit'),
          {key:'passed',title:'Result',render:m=><Badge value={m.passed?'passed':'failed'}/>}]} rows={r.measurements as RecordRow[]}/>
      </>}</Detail>;
  } else if(page==='nonconformances') {
    create=()=>openForm('Open non-conformance','/nonconformances',[machine,field('title','Title'),field('description','Description','textarea'),
      pick('severity','Severity',['minor','major','critical'],'major'),{...field('inspection_id','Failed inspection ID','number'),optional:true}]);
    createLabel='Open report';
    content=<Panel title="Non-conformance reports">{list('/nonconformances',[...columns('title','equipment'),status('severity'),status(),...columns('open_actions'),timeCol('opened_at')],view)}</Panel>;
    if(detail)details=<Detail title={String(detail.title)} path={'/nonconformances/'+detail.id} token={token} version={version} close={()=>setDetail(undefined)}>{r=><>
      <div className="record-summary"><Badge value={r.status}/><Badge value={r.severity}/><span>{text(r.equipment)}</span></div>
      <p>{text(r.description)}</p>
      {canWrite&&r.status!=='closed'&&<div className="inline-actions">
        <button className="button secondary" onClick={()=>openForm('Assign corrective action',`/nonconformances/${detail.id}/actions`,[
          field('title','Action title'),lookupField('owner_id','Owner',lookup.users),date('due_on','Due date',today)])}>Assign action</button>
        {r.status==='open'&&<button className="button secondary" onClick={()=>setConfirm({title:'Start investigation',path:`/nonconformances/${detail.id}`,
          body:{status:'investigating'},message:'Move this report to investigating?'})}>Investigate</button>}
        <button className="button secondary" onClick={()=>setConfirm({title:'Close report',path:`/nonconformances/${detail.id}`,
          body:{status:'closed'},message:'Close this report? This requires all corrective actions to be complete.'})}>Close report</button>
      </div>}
      <h3>Corrective actions</h3><Table columns={[...columns('title','owner','due_on'),status(),{key:'overdue',render:a=>a.overdue?<Badge value="overdue"/>:'—'}]}
        rows={r.actions as RecordRow[]} action={canWrite?a=>a.status==='open'&&<button className="button secondary compact"
          onClick={()=>setConfirm({title:'Complete action',message:'Mark this corrective action complete?',
          path:`/nonconformances/${detail.id}/actions/${a.id}`,body:{status:'done'}})}>Complete</button>:undefined}/>
      <h3>Audit trail</h3><Table columns={[...columns('action','entity','username'),timeCol('occurred_at'),
        {key:'details',render:a=>JSON.stringify(a.details)}]} rows={r.history as RecordRow[]}/>
    </>}</Detail>;
  } else if(page==='maintenance') {
    const active=tab||'orders';
    createLabel=active==='orders'?'Schedule work order':'Record calibration';
    create=()=>active==='orders'?openForm(createLabel,'/maintenance',[machine,field('title','Work order title'),
      pick('kind','Work type',['preventive','corrective'],'preventive'),date('scheduled_on','Scheduled date',today),
      date('due_on','Due date',today),{...field('notes','Notes','textarea'),optional:true}]):
      openForm(createLabel,'/calibrations',[machine,field('reference','Calibration reference'),date('calibrated_on','Calibrated on',today),
        date('next_due_on','Next due date'),pick('result','Result',['pass','fail'],'pass')]);
    content=<Panel title="Service records">{tabs([['orders','Work orders'],['calibration','Calibration']],active)}
      {active==='orders'?list('/maintenance',[...columns('equipment','title','kind','scheduled_on','due_on'),
        {key:'status',render:r=><Badge value={r.overdue?'overdue':r.status}/>}],
        canWrite?r=>r.status!=='complete'&&<>{(r.status==='scheduled'?['in_progress','complete']:['complete']).map(next=>
          <button className="button secondary compact" key={next} onClick={()=>setConfirm({title:next==='complete'?'Complete work order':'Start work order',
            message:'Update the status of this work order?',path:`/maintenance/${r.id}`,body:{status:next}})}>{next==='complete'?'Complete':'Start'}</button>)}</>:undefined)
        :list('/calibrations',[...columns('equipment','reference','calibrated_on','next_due_on'),status('result'),
          {key:'overdue',render:r=>r.overdue?<Badge value="overdue"/>:'—'}])}</Panel>;
  } else if(page==='sorter') {
    const active=tab||'events';
    createLabel='Import trace';create=()=>setImporting(true);
    content=<Panel title="Simulation telemetry">{tabs([['events','Recent events'],['faults','Faults only'],['imports','Import history']],active)}
      {active==='imports' ? list('/sorter/imports',[...columns('filename','equipment'),timeCol('anchor_at'),status('outcome'),...columns('row_count','error')]) :
        list('/sorter/events?faults_only='+(active==='faults'),[timeCol('occurred_at'),...columns('equipment'),status('kind'),...columns('lane','fault_code'),
          {key:'synthetic',title:'Source',render:r=>r.synthetic?'Synthetic seed':'Simulation trace'}])}</Panel>;
  } else if(page==='analytics') {
    const queries:Record<string,[string,string[]]>={
      supplier_defects:['Supplier defect rate',['supplier','inspections','rejected','defect_rate']],
      batch_rejections:['Batch rejection rate',['batch','sku','equipment','inspections','rejected','rejection_rate']],
      reliability:['Failure intervals and repair time',['equipment','recorded_failures','avg_start_to_start_hours','avg_repair_minutes']],
      downtime_by_machine:['Downtime by equipment',['equipment','name','downtime_minutes']],
      fault_frequency:['Fault frequency',['equipment','fault_code','occurrences','latest']],
      maintenance_due:['Maintenance queue',['equipment','title','kind','due_on','status','overdue']],
      low_stock:['Insufficient stock',['sku','name','supplier','available','reorder_point','shortage']],
      defect_trend:['Defect trends',['day','inspections','defects','defect_rate','rolling_rate']],
    };
    const active=tab||'supplier_defects';
    content=<Panel title={queries[active][0]}><div className="panel-filter"><label>Query <select value={active} onChange={e=>setTab(e.target.value)}>
      {Object.entries(queries).map(([key,[name]])=><option key={key} value={key}>{name}</option>)}</select></label></div>
      {list('/analytics/'+active,columns(...queries[active][1]))}</Panel>;
  } else {
    const reports=[['equipment','Equipment register'],['inventory','Inventory availability'],['inspections','Inspection history'],
      ['downtime','Downtime events'],['maintenance','Maintenance work orders']];
    content=<div className="report-grid">{reports.map(([key,name])=><article className="card report-card" key={key}>
      <span className="kpi-icon blue"><FileText size={20}/></span><h3>{name}</h3><p>Comma-separated values</p>
      <button className="button secondary" onClick={async()=>{try {await download(key,token);setError('');}catch(err){setError((err as Error).message);}}}>
        <Download size={16}/> Download CSV</button></article>)}</div>;
  }
  return <>
    <div className="page-intro workspace-intro"><div><div className="eyebrow"><span/> PLANT WORKSPACE</div><h1>{title}</h1><p>{description}</p></div>
      {create&&canWrite&&<button className="button primary" onClick={create}>{page==='sorter'?<Upload size={17}/>:<Plus size={17}/>} {createLabel}</button>}</div>
    {notice&&<div role="status" className="notice"><ClipboardList size={17}/><span>{notice}</span><button onClick={()=>setNotice('')} aria-label="Dismiss notice">Dismiss</button></div>}
    <Feedback error={error}/>{content}{details}
    {form&&<Modal title={form.title} close={()=>setForm(undefined)}><Fields fields={form.fields} close={()=>setForm(undefined)} submit={async data=>{
      await api(form.path,token,json(form.method??'POST',form.transform?form.transform(data):payload(data)));
      setForm(undefined);success(form.title+' saved.');
    }}/></Modal>}
    {confirm&&<Modal title={confirm.title} close={()=>setConfirm(undefined)}><Fields fields={[]} button="Confirm" close={()=>setConfirm(undefined)} submit={async()=>{
      await api(confirm.path,token,confirm.body?json('PATCH',confirm.body):{method:'POST'});
      setConfirm(undefined);success('Record updated.');
    }}><p>{confirm.message}</p></Fields></Modal>}
    {inspection&&<InspectionForm lookup={lookup} token={token} close={()=>setInspection(false)} done={()=>success('Inspection recorded.')}/>}
    {importing&&<Modal title="Import sorter trace" close={()=>setImporting(false)}><Fields
      fields={[machine,field('anchor','Run start (local time)','datetime-local',localStamp()),field('file','CSV trace','file')]}
      button="Import" close={()=>setImporting(false)} submit={async data=>{
        const file=data.get('file') as File;
        if(!file.name.toLowerCase().endsWith('.csv'))throw new Error('Select a .csv trace file.');
        const params=new URLSearchParams({equipment_id:String(data.get('equipment_id')),
          anchor:new Date(String(data.get('anchor'))).toISOString(),filename:file.name});
        const result=await api<RecordRow>('/sorter/imports?'+params,token,{method:'POST',headers:{'Content-Type':'text/csv'},body:file});
        setImporting(false);setTab('imports');success(result.outcome==='duplicate'?'Duplicate trace recognized. No events were added.':`${result.row_count} trace rows imported.`);
      }}><p>Expected columns are <code>time_ms,event,lane</code>. Maximum file size is 512 KiB.</p></Fields></Modal>}
  </>;
}

function InspectionForm({lookup,token,close,done}: {lookup:Lookups;token:string;close:()=>void;done:()=>void}) {
  const [count,setCount]=useState(1);
  const readingFields=Array.from({length:count},(_,i)=>[
    field('characteristic'+i,`Measurement ${i+1} characteristic`),
    field('unit'+i,`Measurement ${i+1} unit`,'text','mm'),
    field('value'+i,`Measurement ${i+1} value`,'number'),
    field('lower_limit'+i,`Measurement ${i+1} lower limit`,'number'),
    field('upper_limit'+i,`Measurement ${i+1} upper limit`,'number'),
  ]).flat();
  return <Modal title="Record inspection" close={close}><Fields close={close} button="Record inspection" fields={[
    lookupField('part_id','Part',lookup.parts),
    lookupField('batch_id','Production batch',lookup.batches.map(b=>({...b,name:lookup.parts.find(p=>match(p,'id',b.part_id))?.sku}))),
    field('inspected_at','Inspection time (local)','datetime-local',localStamp()),
    {...field('rejection_reason','Rejection reason (required on failure)','textarea'),optional:true},
    ...readingFields,
  ]} submit={async data=>{
    const readings=Array.from({length:count},(_,i)=>Object.fromEntries(['characteristic','unit','value','lower_limit','upper_limit']
      .map(key=>[key,String(data.get(key+i))])));
    await api('/inspections',token,json('POST',{part_id:Number(data.get('part_id')),batch_id:Number(data.get('batch_id')),
      inspected_at:new Date(String(data.get('inspected_at'))).toISOString(),rejection_reason:String(data.get('rejection_reason')).trim()||null,
      measurements:readings}));
    close();done();
  }}><button className="button secondary" type="button" disabled={count>=25} onClick={()=>setCount(count+1)}><Plus size={16}/> Add measurement</button>
    {count>1&&<button className="button secondary" type="button" onClick={()=>setCount(count-1)}>Remove last</button>}
    <p><ArrowUpRight size={14} className="inline"/> Readings pass when they are within both tolerance limits, including the limits.</p>
  </Fields></Modal>;
}
