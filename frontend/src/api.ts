export type RecordRow = Record<string, unknown>;
export type Session = { operator_authenticated: boolean; can_read: boolean; can_write: boolean; read_only: boolean; synthetic: boolean };

export function text(value: unknown): string {
  return value === null || value === undefined || value === '' ? '—' : String(value);
}

export function label(value: unknown): string {
  return text(value).replaceAll('_',' ').replace(/^./, first => first.toUpperCase());
}

export function timestamp(value: unknown): string {
  return typeof value === 'string' ? new Intl.DateTimeFormat('en-CA',{
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC',
  }).format(new Date(value)) : '—';
}

export function localStamp() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset()*60_000).toISOString().slice(0,16);
}

async function request(path: string, token: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers);
  if (token) headers.set('Authorization', 'Bearer '+token);
  const res = await fetch('/api'+path,{...options,headers});
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const error = Array.isArray(data.detail)
      ? data.detail.map((issue: {msg: string}) => issue.msg.replace('Value error, ','')).join(' ')
      : data.detail;
    throw new Error(error || `Request failed (${res.status}).`);
  }
  return res;
}

export async function api<T>(path: string, token: string, options?: RequestInit): Promise<T> {
  return (await request(path,token,options)).json();
}

export function json(method: string, value: unknown): RequestInit {
  return { method, headers: {'Content-Type':'application/json'}, body: JSON.stringify(value) };
}

export async function download(kind: string, token: string) {
  const res = await request(`/reports/${kind}.csv`,token);
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = `factoryiq-${kind}.csv`;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url),1000);
}
