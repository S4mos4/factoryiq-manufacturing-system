import { lazy, StrictMode, Suspense, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, ChartNoAxesCombined, ChevronRight, CircleAlert, ClipboardCheck, Database, Factory, FileDown,
  KeyRound, Layers3, LayoutDashboard, Menu, PanelLeftClose, PanelLeftOpen, Radar, Wrench, X } from 'lucide-react';
import { api, type RecordRow, type Session } from './api';
import { Feedback, Fields, Modal, useData } from './components';
import { Workspace } from './Workspace';
import './style.css';

const Dashboard = lazy(() => import('./Dashboard').then(module => ({default:module.Dashboard})));

const Monitoring = lazy(() => import('./Monitoring').then(module => ({default:module.Monitoring})));

const pages = [
  {key:'dashboard',name:'Overview',icon:LayoutDashboard},
  {key:'equipment',name:'Equipment',icon:Factory},
  {key:'inventory',name:'Inventory',icon:Layers3},
  {key:'inspections',name:'Quality inspections',icon:ClipboardCheck},
  {key:'nonconformances',name:'Non-conformances',icon:CircleAlert},
  {key:'maintenance',name:'Maintenance',icon:Wrench},
  {key:'sorter',name:'Sorter events',icon:Radar},
  {key:'analytics',name:'SQL analytics',icon:ChartNoAxesCombined},
  {key:'reports',name:'Reports',icon:FileDown},
  {key:'monitoring',name:'Live monitoring',icon:Activity},
] as const;

function App() {
  const [page,setPage]=useState<string>('dashboard');
  const [token,setToken]=useState('');
  const [version,refresh]=useState(0);
  const [login,setLogin]=useState(false);
  const [collapsed,setCollapsed]=useState(false);
  const [mobile,setMobile]=useState(false);
  const {data:session,error}=useData<Session>('/session',token);
  const current=pages.find(p=>p.key===page)??pages[0];
  function navigate(key:string) {setPage(key);setMobile(false);window.scrollTo({top:0});}
  return <div className={`shell ${collapsed?'is-collapsed':''}`}>
    {mobile&&<button className="mobile-scrim" aria-label="Close navigation" onClick={()=>setMobile(false)}/>}
    <aside className={`sidebar ${mobile?'mobile-open':''}`}>
      <div className="brand"><div className="brand-icon"><Factory size={24} strokeWidth={1.8}/></div>
        <div className="brand-text"><strong>Factory<span>IQ</span></strong><small>Manufacturing intelligence</small></div></div>
      <nav aria-label="Main navigation">
        <div className="nav-group">OPERATIONS</div>
        {pages.map((item,i)=><div key={item.key}>{i===6&&<div className="nav-group secondary-group">INTELLIGENCE</div>}
          <button aria-current={page===item.key?'page':undefined} title={item.name} className={`nav-link ${page===item.key?'selected':''}`}
            onClick={()=>navigate(item.key)}><item.icon size={18}/><span>{item.name}</span></button></div>)}
      </nav>
      <div className="sidebar-bottom"><div className="plant-label"><span className="plant-icon"><Database size={16}/></span>
        <div className="brand-text"><strong>{session?.synthetic?'Demo plant':'Plant workspace'}</strong><small>{session?.synthetic?'Synthetic data':'Local instance'}</small></div></div>
        <button className="collapse-button" aria-label={collapsed?'Expand sidebar':'Collapse sidebar'} onClick={()=>setCollapsed(!collapsed)}>
          {collapsed?<PanelLeftOpen size={18}/>:<PanelLeftClose size={18}/>}<span>Collapse sidebar</span></button></div>
    </aside>
    <div className="main-shell"><header className="topbar">
      <div className="breadcrumbs"><button className="icon-button mobile-menu" aria-label={mobile?'Close menu':'Open menu'} onClick={()=>setMobile(!mobile)}>
        {mobile?<X size={22}/>:<Menu size={22}/>}</button><span>Workspace</span><ChevronRight size={15}/><strong>{current.name}</strong></div>
      <div className="top-actions">{session?.synthetic&&<span className="demo-marker"><span/> Synthetic data</span>}
        {session && (!session.read_only || !session.can_read || token) && <button className="button secondary operator-button" onClick={()=>token?setToken(''):setLogin(true)}>
          <KeyRound size={15}/> {token?'Lock operator':'Operator access'}</button>}</div>
    </header>
    <main id="main-content">
      <Feedback error={error} loading={!session&&!error}/>
      {session&&!session.can_read&&<div className="card restricted"><KeyRound size={25}/><h1>Operator access required</h1>
        <p>Enter the operator token to open this workspace.</p><button className="button primary" onClick={()=>setLogin(true)}>Enter token</button></div>}
      {session?.can_read&&<Content page={page} token={token} session={session} version={version} navigate={navigate} refresh={()=>refresh(v=>v+1)}/>}
    </main>
    <footer><Activity size={15}/> FactoryIQ <span>·</span> Manufacturing intelligence &amp; quality management</footer>
    </div>
    {login&&<Modal title="Operator access" close={()=>setLogin(false)}>
      <Fields close={()=>setLogin(false)} button="Unlock" fields={[{key:'token',title:'Operator token',type:'password'}]} submit={async values=>{
        const next=String(values.get('token')).trim();
        if (!(await api<Session>('/session',next)).operator_authenticated) throw new Error('Invalid operator token.');
        setToken(next);setLogin(false);
      }}/></Modal>}
  </div>;
}

function Content({page,token,session,version,refresh,navigate}: {
  page:string;token:string;session:Session;version:number;refresh:()=>void;navigate:(page:string)=>void;
}) {
  const lookup=useData<Record<string,RecordRow[]>>('/lookups',token,version);
  if(page==='monitoring') return <Suspense fallback={<Feedback loading/>}><Monitoring token={token} canWrite={session.can_write} navigate={navigate}/></Suspense>;
  if(page==='dashboard') return <Suspense fallback={<Feedback loading/>}><Dashboard token={token} machines={lookup.data?.equipment??[]} version={version}/></Suspense>;
  if(!lookup.data) return <Feedback error={lookup.error} loading={!lookup.error}/>;
  return <Workspace key={page} page={page} token={token} lookup={lookup.data} canWrite={session.can_write} version={version} refresh={refresh}/>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><App/></StrictMode>);
