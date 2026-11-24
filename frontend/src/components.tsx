import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { ArrowDown, ArrowUp, ChevronsUpDown, CircleAlert, Database, Search, X } from 'lucide-react';
import { api, label, text, type RecordRow } from './api';

export function useData<T>(path: string, token: string, version = 0) {
  const [state,setState] = useState<{data?:T; error?:string}>({});
  const lastRequest = useRef({path,token});
  useEffect(() => {
    const controller = new AbortController();
    if (lastRequest.current.path !== path || lastRequest.current.token !== token) setState({});
    lastRequest.current = {path,token};
    api<T>(path,token,{signal:controller.signal})
      .then(data => setState({data}))
      .catch((error: Error) => { if (!controller.signal.aborted) setState({error:error.message}); });
    return () => controller.abort();
  },[path,token,version]);
  return state;
}

export function Feedback({error,loading,empty}: {error?:string;loading?:boolean;empty?:string}) {
  if (!error && !loading && !empty) return null;
  return <div className={error?'feedback feedback-error':'feedback'} role={error?'alert':'status'}>
    {error?<CircleAlert size={19}/>:loading?<span className="spinner"/>:<Database size={19}/>}
    {error || (loading?'Loading records…':empty)}
  </div>;
}

export function Badge({value}: {value:unknown}) {
  const key = String(value);
  const tone = ['operational','pass','passed','complete','done','imported','closed','consumed'].includes(key) ? 'good'
    : ['failed','fail','critical','overdue','offline','rejected','jam'].includes(key) ? 'bad'
    : ['maintenance','in_progress','investigating','minor','major','active','open'].includes(key)?'warn':'neutral';
  return <span className={`badge ${tone}`}><span/>{label(key)}</span>;
}

export type Column = { key:string; title?:string; render?:(row:RecordRow)=>ReactNode };
export function Table({columns,rows,search=false,action}: {
  columns:Column[];rows:RecordRow[];search?:boolean;action?:(row:RecordRow)=>ReactNode;
}) {
  const [filter,setFilter] = useState('');
  const [sort,setSort] = useState<{key:string;ascending:boolean}>();
  const matching = rows.filter(row => columns.some(({key}) => text(row[key]).toLowerCase().includes(filter.toLowerCase())));
  if (sort) matching.sort((a,b) => {
    const x=a[sort.key], y=b[sort.key];
    const order=typeof x==='number' && typeof y==='number' ? x-y : text(x).localeCompare(text(y),undefined,{numeric:true});
    return sort.ascending?order:-order;
  });
  const [page,setPage] = useState(0);
  const limit = 12, current = Math.min(page,Math.max(0,Math.ceil(matching.length/limit)-1));
  return <div className="table-wrap">
    {search && <div className="table-tools"><label className="search"><Search size={16}/><input aria-label="Search records"
      placeholder="Search records…" value={filter} onChange={e=>{setFilter(e.target.value);setPage(0);}}/></label>
      <span>{matching.length} records</span></div>}
    {matching.length===0 ? <Feedback empty="No matching records."/> : <div className="table-scroll"><table>
      <thead><tr>{columns.map(col => <th key={col.key} aria-sort={sort?.key===col.key?(sort.ascending?'ascending':'descending'):'none'}>
        <button onClick={()=>{setSort({key:col.key,ascending:sort?.key===col.key?!sort.ascending:true});setPage(0);}}>
          {col.title||label(col.key)} {sort?.key===col.key?(sort.ascending?<ArrowUp size={13}/>:<ArrowDown size={13}/>):<ChevronsUpDown size={12}/>}
        </button></th>)}{action && <th scope="col">Actions</th>}</tr></thead>
      <tbody>{matching.slice(current*limit,(current+1)*limit).map((row,i)=><tr key={String(row.id??i)}>
        {columns.map((col,j)=><td key={col.key} className={j===0?'primary-cell':undefined}>{col.render?.(row) ?? text(row[col.key])}</td>)}
        {action && <td><div className="row-actions">{action(row)}</div></td>}
      </tr>)}</tbody>
    </table></div>}
    {matching.length>limit && <div className="pagination"><span>{current*limit+1}–{Math.min((current+1)*limit,matching.length)} of {matching.length}</span>
      <button className="button secondary compact" disabled={current===0} onClick={()=>setPage(current-1)}>Previous</button>
      <button className="button secondary compact" disabled={(current+1)*limit>=matching.length} onClick={()=>setPage(current+1)}>Next</button></div>}
  </div>;
}

export function Modal({title,close,children}: {title:string;close:()=>void;children:ReactNode}) {
  const ref=useRef<HTMLDialogElement>(null);
  const id=useId();
  useEffect(()=>{ref.current?.showModal();},[]);
  return <dialog ref={ref} aria-labelledby={id} onCancel={e=>{e.preventDefault();close();}}>
    <div className="dialog-title"><h2 id={id}>{title}</h2><button className="icon-button" aria-label="Close dialog" onClick={close}><X size={19}/></button></div>
    {children}
  </dialog>;
}

export type Field = { key:string; title:string; type?:string; initial?:string; choices?:[string,string][]; optional?:boolean };
export function Fields({fields,submit,close,button='Save',children}: {
  fields:Field[];submit:(values:FormData)=>Promise<void>;close:()=>void;button?:string;children?:ReactNode;
}) {
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  async function save(e:FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);setError('');
    try { await submit(new FormData(e.currentTarget)); } catch (err) {
      setError(err instanceof Error?err.message:'Unable to save.');setBusy(false);
    }
  }
  return <form className="dialog-body" onSubmit={save}>
    <div className="form-grid">{fields.map(field=><label key={field.key} className={field.type==='textarea'?'full-field':undefined}>
      {field.title}
      {field.choices ? <select name={field.key} defaultValue={field.initial??''} required={!field.optional}>
        <option value="">{field.optional?'None':'Select…'}</option>
        {field.choices.map(([value,title])=><option key={value} value={value}>{title}</option>)}
      </select> : field.type==='textarea' ? <textarea name={field.key} defaultValue={field.initial} required={!field.optional} maxLength={2000}/>
        : <input name={field.key} type={field.type||'text'} defaultValue={field.initial} required={!field.optional}
          maxLength={field.type==='password'?256:120} min={field.type==='number'&&field.key==='quantity'?1:undefined}
          step={field.type==='number'?'any':undefined} /> }
    </label>)}</div>
    {children}
    <Feedback error={error}/>
    <div className="dialog-actions"><button type="button" className="button secondary" onClick={close}>Cancel</button>
      <button className="button primary" type="submit" disabled={busy}>{busy?'Saving…':button}</button></div>
  </form>;
}
