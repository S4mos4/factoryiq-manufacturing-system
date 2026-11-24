import { useEffect, useState } from 'react';
import { Activity, AlertTriangle, Box, CircleGauge, Factory, Radio, Thermometer, Wrench, Zap } from 'lucide-react';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api, json, label, text, timestamp, type RecordRow } from './api';
import { Badge, Feedback, Fields, Modal, Table, useData } from './components';
import './monitoring.css';

type Device = {id:string; equipment_id:number; equipment_code:string; station_name:string; simulated:boolean;
  connected:boolean; last_heartbeat_at:string|null; maintenance_status:string};
type Reading = RecordRow & {device_id:string; observed_at:string; status:string};
type Alarm = RecordRow & {id:number; device_id:string; code:string; severity:string; acknowledged_at:string|null};
type Snapshot = {devices:Device[]; readings:Reading[]; alarms:Alarm[]};
type DeviceDetail = {history:Reading[]; performance:RecordRow; condition:RecordRow[]; alarms:Alarm[];
  maintenance:RecordRow[]; connections:RecordRow[]; thresholds:RecordRow[]};

const measures = [
  ['temperature_c','Temperature','°C',Thermometer], ['vibration_g','Vibration','g RMS',Activity],
  ['rpm','Motor speed','RPM',CircleGauge], ['current_a','Current','A',Zap],
  ['voltage_v','Voltage','V',Zap], ['power_w','Power','W',Zap],
] as const;
const metrics = [
  ['oee_percent','Observed OEE','%'], ['availability_percent','Availability','%'],
  ['performance_percent','Production performance','%'], ['quality_percent','Quality','%'],
  ['mtbf_seconds','Observed MTBF','s'], ['mttr_seconds','Mean repair time','s'], ['energy_kwh','Energy','kWh'],
  ['units_per_hour','Throughput','units/h'], ['downtime_seconds','Observed downtime','s'], ['coverage_percent','Time coverage','%'],
] as const;
const faults=[['overheat','Motor overheating'],['vibration','Excessive vibration'],['jam','Conveyor jam'],
  ['overcurrent','Abnormal current'],['shutdown','Equipment shutdown'],['sensor_disconnected','Sensor disconnection'],
  ['communication_failure','Communication failure'],['normal','Restore normal operation']] as [string,string][];

function useStream(token:string) {
  const [value,setValue]=useState<Snapshot>();
  const [state,setState]=useState('Connecting');
  useEffect(()=>{
    const controller=new AbortController();
    let reconnect: ReturnType<typeof setTimeout>|undefined;
    async function consume() {
      try {
        const response=await fetch('/api/iot/stream',{headers:token?{Authorization:'Bearer '+token}:{},signal:controller.signal});
        if(!response.ok||!response.body) throw new Error('Stream unavailable.');
        const reader=response.body.pipeThrough(new TextDecoderStream()).getReader();
        let pending='';
        try {
          while(!controller.signal.aborted) {
            const {value,done}=await reader.read();
            if(done)break;
            pending+=value;
            let boundary=pending.indexOf('\n\n');
            while(boundary!==-1) {
              const event=pending.slice(0,boundary);
              pending=pending.slice(boundary+2);
              if(event.startsWith('data:')) {
                setValue(JSON.parse(event.slice(5)) as Snapshot);
                setState('Live');
              }
              boundary=pending.indexOf('\n\n');
            }
          }
        } finally { await reader.cancel().catch(()=>undefined); }
      } catch {
        if(!controller.signal.aborted)setState('Reconnecting');
      }
      if(!controller.signal.aborted) {
        setState('Reconnecting');
        reconnect=setTimeout(consume,2500);
      }
    }
    setValue(undefined);setState('Connecting');
    void consume();
    return ()=>{controller.abort();clearTimeout(reconnect);};
  },[token]);
  return {value,state};
}

function units(value:unknown,unit:string) {
  return value==null || !Number.isFinite(Number(value)) ? 'Unavailable' :
    `${new Intl.NumberFormat('en-CA',{maximumFractionDigits:unit==='kWh'?4:2}).format(Number(value))} ${unit}`;
}

const alarmName=(code:unknown)=>label(String(code).replace(/^fault:|^threshold:|^link:/,''));
const localClock=(value:unknown)=>new Date(String(value)).toLocaleTimeString('en-CA',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
const pct=(value:unknown)=>units(value,'%');

export function Monitoring({token,canWrite,navigate}: {token:string;canWrite:boolean;navigate:(page:string)=>void}) {
  const {value,state}=useStream(token);
  const [chosen,choose]=useState('');
  const [window,setWindow]=useState('30');
  const [revision,refresh]=useState(0);
  const [modal,setModal]=useState<'fault'|'threshold'>();
  const [alarm,setAlarm]=useState<Alarm>();
  const [notice,setNotice]=useState('');
  const devices=value?.devices??[];
  const selected=devices.find(d=>d.id===chosen)??devices[0];
  const readings=new Map(value?.readings.map(r=>[r.device_id,r]));
  const active=value?.alarms.filter(a=>a.device_id===selected?.id)??[];
  const live=selected?readings.get(selected.id):undefined;
  const {data:detail,error}=useData<DeviceDetail>(
    selected?`/iot/devices/${selected.id}?minutes=${window}`:'/iot/snapshot',token,revision,
  );
  useEffect(()=>{
    if(!selected)return;
    const timer=setInterval(()=>refresh(n=>n+1),7500);
    return ()=>clearInterval(timer);
  },[selected?.id]);
  const statusFor=(device:Device)=>{
    if(!device.connected)return 'offline';
    if(value?.alarms.some(a=>a.device_id===device.id&&a.severity==='critical'))return 'fault';
    return readings.get(device.id)?.status??'waiting';
  };
  const moving=devices.some(d=>d.id==='sim-conveyor'&&statusFor(d)==='running')&&state==='Live';
  return <>
    <div className="page-intro workspace-intro"><div><div className="eyebrow"><span/> EQUIPMENT INTELLIGENCE</div>
      <h1>Production line monitoring</h1><p>Monitor equipment, sensor trends and alarms across the line.</p></div>
      <span className={`iot-stream ${state==='Live'?'is-live':''}`} role="status"><Radio size={17}/>{state} telemetry</span></div>
    {!value&&<Feedback loading={state==='Connecting'} empty={state==='Reconnecting'?'Waiting for the telemetry stream to reconnect.':undefined}/>}
    {value&&devices.length===0&&<Feedback empty="No registered devices. Start the MQTT simulator or register a prototype device."/>}
    {devices.length>0&&<section className="card iot-twin" aria-label="Digital twin">
      <div className="iot-card-head"><div><h2>Production line twin</h2><p>Select a station to inspect its sensors and maintenance records.</p></div><Factory size={20}/></div>
      <div className="iot-line">
        {devices.map((device,index)=>{
          const status=statusFor(device);
          return <button key={device.id} type="button" aria-pressed={device.id===selected?.id}
            className={`iot-station ${device.id===selected?.id?'selected':''} iot-${status}`} onClick={()=>{choose(device.id);setNotice('');}}>
            <div className="iot-station-top">
              {index===0?<Box size={19}/>:<CircleGauge size={19}/>}
              <span className="iot-state"><i/>{label(status)}</span>
            </div>
            <strong>{device.station_name}</strong>
            <small>{device.equipment_code} · {device.simulated?'Simulated':'Prototype device'}</small>
            <span className="iot-sensor"><Thermometer size={13}/>{units(readings.get(device.id)?.temperature_c,'°C')}</span>
            {device.maintenance_status==='maintenance'&&<span className="iot-maintenance"><Wrench size={13}/> Maintenance</span>}
          </button>;
        })}
      </div>
      <div className={`iot-flow ${moving?'moving':''}`} aria-label={moving?'Conveyor moving':'Conveyor stopped'}>
        <div className="iot-belt"/><span>Material flow <b>{moving?'In motion':'Stopped'}</b></span>
      </div>
    </section>}
    {selected&&<>
      <div className="section-heading iot-detail-heading"><div><h2>{selected.station_name}</h2><span>{selected.simulated?'Synthetic telemetry':'Prototype telemetry'} · last sample {timestamp(live?.observed_at)} UTC</span></div>
        <div className="iot-actions">
          <label>History <select value={window} onChange={e=>setWindow(e.target.value)}><option value="15">15 minutes</option><option value="30">30 minutes</option><option value="60">1 hour</option><option value="1440">24 hours</option></select></label>
          {canWrite&&selected.simulated&&<button className="button secondary" onClick={()=>setModal('fault')}>Simulate fault</button>}
          {canWrite&&<button className="button secondary" onClick={()=>setModal('threshold')}>Set threshold</button>}
        </div>
      </div>
      {notice&&<div className="notice" role="status">{notice}</div>}
      <Feedback error={error} loading={!detail&&!error}/>
      <div className="iot-metrics" aria-label="Live sensor readings">
        {measures.map(([key,title,unit,Icon])=><article key={key} className="card iot-metric">
          <header><span>{title}</span><Icon size={16}/></header>
          <strong>{selected.connected?units(live?.[key],unit):'Unavailable'}</strong>
          <span>{selected.connected?'Latest sample':'Device offline'}</span>
          <div className="iot-chart" aria-label={title+' history'}>
            {detail?.history.some(r=>r[key]!=null) ? <ResponsiveContainer width="100%" height="100%">
              <LineChart data={detail.history} margin={{top:6,right:8,left:-22,bottom:0}}>
                <CartesianGrid stroke="#e5edf7" vertical={false} strokeDasharray="3 4"/>
                <XAxis dataKey="observed_at" tickFormatter={localClock} tick={{fontSize:9,fill:'#4c6587'}} minTickGap={32}/>
                <YAxis tick={{fontSize:9,fill:'#4c6587'}} domain={['auto','auto']}/>
                <Tooltip labelFormatter={localClock} formatter={value=>units(value,unit)}/>
                <Line type="linear" dataKey={key} name={title} stroke="#2859cf" strokeWidth={2} dot={false}
                  isAnimationActive={false} connectNulls={false}/>
              </LineChart>
            </ResponsiveContainer>:<span className="iot-no-chart">No samples in this window</span>}
          </div>
        </article>)}
      </div>
      {detail?.performance&&<>
        <div className="section-heading"><h2>Manufacturing performance</h2><span>Observed intervals · {pct(detail.performance.coverage_percent)} coverage</span></div>
        <div className="iot-performance">{metrics.slice(0,-1).map(([key,title,unit])=><article key={key} className="card iot-mini"><h3>{title}</h3><strong>{units(detail.performance[key],unit)}</strong></article>)}
          <article className="card iot-mini"><h3>Produced in window</h3><strong>{units(detail.performance.production_count,'units')}</strong></article></div>
        <div className="iot-two">
          <section className="card"><div className="iot-card-head"><div><h2>Active alarms</h2><p>{active.length} open at this station</p></div><AlertTriangle size={19}/></div>
            <Table rows={active} columns={[{key:'code',title:'Signal',render:r=>alarmName(r.code)},{key:'severity',render:r=><Badge value={r.severity}/>},
              {key:'acknowledged_at',title:'Acknowledged',render:r=>r.acknowledged_at?timestamp(r.acknowledged_at):'Pending'}]}
              action={r=><button className="button secondary compact" onClick={()=>setAlarm(r as Alarm)}>Details</button>}/>
          </section>
          <section className="card"><div className="iot-card-head"><div><h2>Condition monitoring</h2><p>Statistical signals for investigation</p></div><Activity size={19}/></div>
            <Table rows={detail.condition} columns={[{key:'metric',render:r=>label(r.metric)},{key:'assessment'},
              {key:'moving_average',title:'Baseline',render:r=>r.moving_average==null?'—':Number(r.moving_average).toFixed(2)},
              {key:'z_score',title:'Z-score',render:r=>r.z_score==null?'—':Number(r.z_score).toFixed(2)}]}/>
          </section>
        </div>
        <div className="iot-two">
          <section className="card"><div className="iot-card-head"><div><h2>Alarm history</h2><p>Threshold, connectivity and equipment events</p></div></div>
            <Table rows={detail.alarms} columns={[{key:'code',render:r=>alarmName(r.code)},{key:'first_at',render:r=>timestamp(r.first_at)},
              {key:'resolved_at',render:r=>r.resolved_at?timestamp(r.resolved_at):'Open'}]}
              action={r=><button className="button secondary compact" onClick={()=>setAlarm(r as Alarm)}>History</button>}/>
          </section>
          <section className="card"><div className="iot-card-head"><div><h2>Maintenance & connectivity</h2>
            <p>{selected.connected?'Online':'Offline'} · last heartbeat {timestamp(selected.last_heartbeat_at)} UTC</p></div><Wrench size={19}/></div>
            <Table rows={detail.maintenance} columns={[{key:'title'},{key:'due_on'},{key:'status',render:r=><Badge value={r.status}/>}]}/>
            <div className="iot-card-head"><div className="iot-actions"><button className="button secondary compact" onClick={()=>navigate('equipment')}>Equipment records</button>
              <button className="button secondary compact" onClick={()=>navigate('maintenance')}>Maintenance queue</button></div></div>
          </section>
        </div>
      </>}
      {modal==='fault'&&<Modal title="Simulate equipment fault" close={()=>setModal(undefined)}>
        <Fields fields={[{key:'fault',title:'Fault',choices:faults,initial:'overheat'},
          {key:'duration',title:'Duration in seconds (15–180)',type:'number',initial:'45'}]}
          button="Apply simulation" close={()=>setModal(undefined)} submit={async form=>{
            await api(`/iot/devices/${selected.id}/simulation`,token,json('POST',{fault:form.get('fault'),duration_seconds:Number(form.get('duration'))}));
            setModal(undefined);setNotice('Simulation command queued.');
          }}/></Modal>}
      {modal==='threshold'&&<Modal title="Set sensor threshold" close={()=>setModal(undefined)}>
        <Fields fields={[{key:'metric',title:'Metric',choices:measures.map(([key,n,u])=>[key,`${n} (${u})`])},
          {key:'warning',title:'Warning threshold',type:'number'},{key:'critical',title:'Critical threshold',type:'number'}]}
          close={()=>setModal(undefined)} submit={async form=>{
            await api(`/iot/devices/${selected.id}/thresholds/${form.get('metric')}`,token,json('PUT',{warning:Number(form.get('warning')),critical:Number(form.get('critical'))}));
            setModal(undefined);setNotice('Threshold saved. New samples use the updated limits.');refresh(n=>n+1);
          }}/></Modal>}
      {alarm&&<AlarmDetail key={alarm.id} alarm={alarm} token={token} canWrite={canWrite} close={()=>setAlarm(undefined)}
        done={()=>{setAlarm(undefined);refresh(n=>n+1);}} navigate={navigate}/>}
    </>}
  </>;
}

function AlarmDetail({alarm,token,canWrite,close,done,navigate}: {
  alarm:Alarm;token:string;canWrite:boolean;close:()=>void;done:()=>void;navigate:(page:string)=>void;
}) {
  const path=`/iot/devices/${alarm.device_id}/alarms/${alarm.id}`;
  const {data,error}=useData<RecordRow[]>(path+'/history',token);
  return <Modal title={alarmName(alarm.code)} close={close}>
    <div className="dialog-body"><p>{label(alarm.severity)} · opened {timestamp(alarm.first_at)} UTC</p>
      {alarm.work_order_id!=null&&<button className="button secondary compact" onClick={()=>navigate('maintenance')}>Maintenance order #{text(alarm.work_order_id)}</button>}
      <Feedback error={error} loading={!data&&!error}/>
      {data&&<Table rows={data} columns={[{key:'action'},{key:'at',render:r=>timestamp(r.at)}]}/>}</div>
    {canWrite&&!alarm.acknowledged_at&&<Fields fields={[]} button="Acknowledge alarm" close={close} submit={async()=>{
      await api(path+'/acknowledge',token,{method:'POST'});done();
    }}/>}
  </Modal>;
}
