import { useState } from 'react';
import { Activity, ArrowDownRight, ArrowUpRight, CalendarDays, ChartNoAxesCombined, CircleAlert,
  Clock3, Factory, Filter, Layers3, ShieldCheck, Wrench } from 'lucide-react';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { type RecordRow, text } from './api';
import { Feedback, Table, useData } from './components';

type DashboardData = {
  period:{start:string;end:string};current:RecordRow;previous:RecordRow;
  trend:RecordRow[];downtime:RecordRow[];faults:RecordRow[];
};
const number = new Intl.NumberFormat('en-CA',{maximumFractionDigits:1});
function format(value:unknown,unit='') { return value==null?'—':number.format(Number(value))+unit; }
function shortDate(day:string) {
  return new Date(day+'T00:00:00Z').toLocaleDateString('en-CA',{month:'short',day:'numeric',timeZone:'UTC'});
}

export function Dashboard({token,machines,version}: {token:string;machines:RecordRow[];version:number}) {
  const [range,setRange]=useState({start:'',end:'',machine:''});
  const [draft,setDraft]=useState(range);
  const params=new URLSearchParams(Object.entries(range).filter(([,value])=>value));
  const {data,error}=useData<DashboardData>('/dashboard?'+params,token,version);
  const current=data?.current, previous=data?.previous;
  const cards=[
    {key:'equipment_total',title:'Total equipment',icon:Factory,tone:'blue',value:format(current?.equipment_total),
      note:`${current?.equipment_operational} operational · ${current?.equipment_maintenance} in maintenance`},
    {key:'availability',title:'Machine availability',icon:Activity,tone:'teal',value:format(current?.availability,'%'),unit:' pp'},
    {key:'downtime_minutes',title:'Total downtime',icon:Clock3,tone:'amber',value:current?format(Number(current.downtime_minutes)/60,' h'):'—',unit:' h',scale:60,invert:true},
    {key:'defect_rate',title:'Defect rate',icon:ShieldCheck,tone:'violet',value:format(current?.defect_rate,'%'),unit:' pp',invert:true},
  ];
  const stats=[
    {title:'Inspection pass rate',icon:ShieldCheck,value:format(current?.pass_rate,'%'),detail:`${current?.inspections} inspections in period`},
    {title:'Inventory availability',icon:Layers3,value:current?`${current.stocked_parts} / ${current.total_parts}`:'—',detail:`${current?.low_stock} below reorder point`},
    {title:'Open non-conformances',icon:CircleAlert,value:format(current?.open_reports),detail:'Current unresolved reports'},
    {title:'Overdue work orders',icon:Wrench,value:format(current?.overdue_orders),detail:'Current maintenance queue'},
  ];
  const trend=data?.trend.map(row=>({day:shortDate(String(row.day)),daily:row.defect_rate==null?null:Number(row.defect_rate),
    rolling:row.rolling_rate==null?null:Number(row.rolling_rate)}));
  const downtime=data?.downtime.slice(0,5).map(row=>({...row,hours:Number((Number(row.downtime_minutes)/60).toFixed(2))}));
  return <>
    <div className="page-intro"><div className="eyebrow"><span/> PLANT WORKSPACE</div>
      <h1>Operations overview</h1><p>Track equipment performance, quality outcomes, and plant reliability.</p></div>
    <form className="filter-bar" onSubmit={e=>{e.preventDefault();setRange({start:draft.start||data?.period.start||'',end:draft.end||data?.period.end||'',machine:draft.machine});}}>
      <div className="filter-caption"><CalendarDays size={17}/><span>{data?`${shortDate(data.period.start)} – ${shortDate(data.period.end)}`:'Reporting period'}<small> UTC</small></span></div>
      <div className="filter-controls">
        <label><span>Start date</span><input aria-label="Start date" type="date" value={draft.start || (range.start===draft.start?data?.period.start||'':'')} onChange={e=>setDraft({...draft,start:e.target.value})}/></label>
        <label><span>End date</span><input aria-label="End date" type="date" value={draft.end || (range.end===draft.end?data?.period.end||'':'')} onChange={e=>setDraft({...draft,end:e.target.value})}/></label>
        <label><span>Equipment</span><select aria-label="Filter equipment" value={draft.machine} onChange={e=>setDraft({...draft,machine:e.target.value})}>
          <option value="">All equipment</option>{machines.map(m=><option key={String(m.id)} value={String(m.id)}>{text(m.code)} · {text(m.name)}</option>)}
        </select></label>
        <button className="button primary apply" type="submit"><Filter size={15}/> Apply</button>
      </div>
    </form>
    <Feedback error={error} loading={!error&&!data}/>
    {data && <>
      <section className="kpi-grid" aria-label="Key performance indicators">{cards.map(card=>{
        const prior=previous?.[card.key], now=current?.[card.key];
        const delta=prior==null||now==null?null:(Number(now)-Number(prior))/(card.scale||1);
        const positive=delta!=null && (card.invert?delta<0:delta>0);
        return <article className="card kpi" key={card.key}><div className="kpi-head"><span>{card.title}</span>
          <span className={`kpi-icon ${card.tone}`}><card.icon size={19}/></span></div>
          <strong>{card.value}</strong>
          <div className="kpi-foot">{card.note || (delta!=null?<>
            <span className={`delta ${delta===0?'flat':positive?'positive':'negative'}`}>{delta===0?null:delta>0?<ArrowUpRight size={13}/>:<ArrowDownRight size={13}/>}
              {delta>0?'+':''}{format(delta,card.unit)}</span> vs. previous period</>:'No prior-period comparison')}</div>
        </article>;
      })}</section>
      <div className="section-heading"><h2>Performance trends</h2><span>Selected reporting period</span></div>
      <section className="chart-grid" aria-label="Performance charts">
        <article className="card chart-card">
          <div className="chart-heading"><div><h3>Quality trend</h3><p>Daily defect rate and 7-day weighted average</p></div><ChartNoAxesCombined size={20}/></div>
          <div className="chart-body"><ResponsiveContainer width="100%" height="100%"><AreaChart data={trend} margin={{top:9,bottom:0,left:-14,right:12}}>
            <CartesianGrid stroke="#e7edf4" vertical={false} strokeDasharray="4 4"/>
            <XAxis dataKey="day" minTickGap={25} tick={{fill:'#52637c',fontSize:12}} tickLine={false} axisLine={false}/>
            <YAxis tickFormatter={v=>v+'%'} tick={{fill:'#52637c',fontSize:12}} tickLine={false} axisLine={false} domain={[0,'auto']}/>
            <Tooltip formatter={(value,name)=>[value+'%',name==='daily'?'Daily defect rate':'7-day weighted rate']}/>
            <Area isAnimationActive={false} type="monotone" dataKey="daily" stroke="#94a9ce" fill="#edf2fc" strokeWidth={1.5}/>
            <Area isAnimationActive={false} type="monotone" dataKey="rolling" stroke="#285cdb" fill="#dbe7ff" fillOpacity={0.58} strokeWidth={2.5}/>
          </AreaChart></ResponsiveContainer></div>
          <div className="chart-legend"><span><i/>7-day weighted rate</span><span><i/>Daily defect rate</span></div>
        </article>
        <article className="card chart-card">
          <div className="chart-heading"><div><h3>Downtime by equipment</h3><p>Top machines by recorded stop duration</p></div><Clock3 size={20}/></div>
          {downtime?.length?<div className="chart-body"><ResponsiveContainer width="100%" height="100%"><BarChart data={downtime} layout="vertical" margin={{top:3,bottom:0,left:0,right:18}}>
            <CartesianGrid stroke="#e7edf4" horizontal={false} strokeDasharray="4 4"/>
            <XAxis type="number" tickFormatter={v=>v+' h'} tick={{fill:'#52637c',fontSize:12}} tickLine={false} axisLine={false}/>
            <YAxis type="category" dataKey="equipment" tick={{fill:'#41536f',fontSize:12}} tickLine={false} axisLine={false} width={58}/>
            <Tooltip formatter={value=>[value+' h','Downtime']} labelFormatter={(value,payload)=>String(payload?.[0]?.payload.name??value)}/>
            <Bar isAnimationActive={false} dataKey="hours" fill="#3967d7" radius={[0,5,5,0]} barSize={16}/>
          </BarChart></ResponsiveContainer></div>:<Feedback empty="No downtime was recorded for this period."/>}
          <div className="chart-legend"><span><i/>Recorded downtime (hours)</span></div>
        </article>
      </section>
      <div className="section-heading"><h2>Operational health</h2><span>Quality and current alerts</span></div>
      <section className="health-grid">{stats.map(stat=><article className="card health" key={stat.title}>
        <stat.icon size={17}/><div><h3>{stat.title}</h3><strong>{stat.value}</strong><p>{stat.detail}</p></div></article>)}</section>
      <section className="card fault-card"><div className="chart-heading"><div><h3>Recurring machine faults</h3>
        <p>{format(current?.fault_events)} recorded fault events in the selected period</p></div><CircleAlert size={19}/></div>
        <Table rows={data.faults} columns={[{key:'equipment'},{key:'fault_code'},{key:'occurrences'},{key:'latest',render:r=>shortDate(String(r.latest).slice(0,10))}]}/>
      </section>
    </>}
  </>;
}
