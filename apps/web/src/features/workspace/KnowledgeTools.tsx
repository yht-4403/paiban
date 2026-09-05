import { useRef, useState } from 'react';
import { Button, Input } from '@tutti-os/ui-system';
import { ConnectorLinedIcon, FileTextIcon, RefreshIcon, UploadIcon } from '@tutti-os/ui-system/icons';
import { api, type ContentConnection, type State } from '../../shared/api';
import { useMutation } from '../../shared/useMutation';
import './knowledge.css';

export type ContextSource = {chunk_id?:string;id:string;title:string;source_kind:string;version:number;body?:string;label?:string;updated_at?:string;offset?:number};
type SearchResult = {sources:ContextSource[];has_more:boolean;index_pending:boolean};

export function LarkConnections({state,onRefresh}:{state:State;onRefresh:()=>Promise<void>}) {
  const [adding,setAdding]=useState(false); const [url,setUrl]=useState('');
  const {busy,error,mutate}=useMutation(onRefresh);
  if(state.account.role!=='owner') return null;
  const action=async(path:string,body:Record<string,unknown>)=>{const result=await mutate(path,body);if(result&&path==='/knowledge/connections/lark'){setUrl('');setAdding(false);}};
  return <section className="knowledge-connectors" aria-label="内容连接">
    <div className="knowledge-connector-heading"><strong>内容连接</strong><Button size="sm" variant="secondary" onClick={()=>setAdding(value=>!value)}><ConnectorLinedIcon />连接飞书</Button></div>
    {adding&&<form onSubmit={event=>{event.preventDefault();void action('/knowledge/connections/lark',{url});}}><Input autoFocus aria-label="飞书文档链接" placeholder="粘贴飞书文档链接" value={url} maxLength={1000} onChange={event=>setUrl(event.target.value)} /><Button type="submit" disabled={busy||!url.trim()}>连接</Button></form>}
    {!!state.content_connections?.length&&<div className="knowledge-connection-list">{state.content_connections.map(connection=><ConnectionRow key={connection.id} connection={connection} busy={busy} action={action} />)}</div>}
    {error&&<p className="form-error" role="alert">{error}</p>}
  </section>;
}

function ConnectionRow({connection,busy,action}:{connection:ContentConnection;busy:boolean;action:(path:string,body:Record<string,unknown>)=>Promise<void>}) {
  const base=`/knowledge/connections/${connection.id}`;
  const status=connection.status==='syncing'?'同步中':connection.status==='error'?'同步失败':connection.status==='disconnected'?'已断开':'自动同步';
  return <div className="knowledge-connection-row"><span className="file-tile"><FileTextIcon size={16} /></span><span className="knowledge-connection-name"><strong>{connection.title}</strong><small>飞书 · {status} · {connection.scope==='team'?'团队可读':'仅自己'}</small></span><div className="knowledge-connection-actions">
    {connection.enabled&&<><Button variant="ghost" size="xs" disabled={busy||connection.status==='syncing'} title="立即同步" aria-label={`同步 ${connection.title}`} onClick={()=>void action(base+'/sync',{expected_version:connection.version})}><RefreshIcon /></Button><Button variant="ghost" size="xs" disabled={busy} onClick={()=>void action(base+'/scope',{expected_version:connection.version,scope:connection.scope==='team'?'private':'team'})}>{connection.scope==='team'?'设为仅自己':'团队可读'}</Button><Button variant="ghost" size="xs" disabled={busy} onClick={()=>void action(base+'/disconnect',{expected_version:connection.version})}>断开</Button></>}
    {!connection.enabled&&<Button variant="ghost" size="xs" disabled={busy} onClick={()=>void action('/knowledge/connections/lark',{url:connection.locator})}>重新连接</Button>}
  </div></div>;
}

export function ImportFiles({onRefresh}:{onRefresh:()=>Promise<void>}) {
  const input=useRef<HTMLInputElement>(null);
  const reading=useRef(false);
  const {busy,error,setError,mutate}=useMutation(onRefresh);
  const [loading,setLoading]=useState(false);
  const [receipt,setReceipt]=useState('');
  const load=async(files:File[])=> {
    if (!files.length || reading.current || busy) return;
    reading.current=true;setLoading(true);setError('');setReceipt('');
    try {
      if(files.length>20) throw new Error('一次最多导入 20 个文件。');
      const contents=[];
      for(const file of files) {
        if(!/\.(md|markdown|txt|csv|json)$/i.test(file.name) || file.name.startsWith('.') || file.size>64000) throw new Error(`${file.name}：请选择 64 KB 内的文本文件。`);
        let content:string;
        try {content=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());}
        catch {throw new Error(`${file.name}：请先另存为 UTF-8 文本。`);}
        if(!content.trim() || content.length>16000 || /[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(content)) throw new Error(`${file.name}：内容须为 1 至 16000 字的文本。`);
        contents.push({filename:file.name,content});
      }
      const result=await mutate<{files:{status:string}[]}>('/knowledge/imports',{files:contents});
      if(result) {const saved=result.files.filter(f=>f.status!=='unchanged').length;setReceipt(saved ? `已导入 ${saved} 份 · 仅自己` : '文件已存在');}
    } catch(e) {setError((e as Error).message);}
    finally {reading.current=false;setLoading(false);}
  };
  return <div className="knowledge-import"><input ref={input} type="file" hidden multiple accept=".md,.markdown,.txt,.csv,.json" onChange={e=>{void load(Array.from(e.target.files || []));e.target.value='';}} />
    <Button variant="secondary" disabled={busy||loading} onClick={()=>input.current?.click()}><UploadIcon />{busy||loading?'导入中…':'导入文件'}</Button>
    {receipt&&<span role="status">{receipt}</span>}{error&&<p className="form-error" role="alert">{error}</p>}
  </div>;
}

export function KnowledgeSearch({onSearchChange}:{onSearchChange:(active:boolean)=>void}) {
  const [query,setQuery]=useState(''); const [result,setResult]=useState<SearchResult|null>(null);
  const [busy,setBusy]=useState(false); const [error,setError]=useState('');
  const request=useRef(0);
  const search=async()=> {
    if(!query.trim()) return;
    const id=++request.current;setBusy(true);setError('');setResult(null);
    try {const found=await api<SearchResult>('/knowledge/search?q='+encodeURIComponent(query.trim()));if(id===request.current)setResult(found);}
    catch(e){if(id===request.current)setError((e as Error).message);}
    finally{if(id===request.current)setBusy(false);}
  };
  return <section className="knowledge-search" aria-label="检索我的资料与会话">
    <form onSubmit={e=>{e.preventDefault();void search();}}><Input aria-label="搜索我的资料与历史会话" placeholder="搜索我的资料与历史会话…" value={query} maxLength={200} onChange={e=>{setQuery(e.target.value);onSearchChange(!!e.target.value.trim());request.current++;setResult(null);setBusy(false);setError('');}} /><Button type="submit" variant="secondary" disabled={busy||!query.trim()}>{busy?'搜索中…':'搜索'}</Button></form>
    {error&&<p role="alert" className="form-error">{error}</p>}
    {result&&<div className="knowledge-results">{result.sources.map(source=><Evidence key={source.chunk_id} source={source} />)}
      {!result.sources.length&&<p role="status">没有匹配的内容</p>}{result.has_more&&<small>还有更多结果，试试更具体的关键词。</small>}{result.index_pending&&<small>历史内容正在整理，可稍后再次搜索。</small>}
    </div>}
  </section>;
}

function Evidence({source}:{source:ContextSource}) {
  const [loaded,setLoaded]=useState<ContextSource|null>(null);const [error,setError]=useState('');
  const [loading,setLoading]=useState(false);const request=useRef(0);
  return <details className="knowledge-evidence" onToggle={event=> {
    const id=++request.current;setLoaded(null);setError('');
    if(!event.currentTarget.open || !source.chunk_id) return;
    setLoading(true);
    void api<ContextSource>('/knowledge/chunks/'+source.chunk_id).then(value=>{if(id===request.current)setLoaded(value);}).catch(e=>{if(id===request.current)setError(e.message);}).finally(()=>{if(id===request.current)setLoading(false);});
  }}><summary><FileTextIcon size={13} /><span>{source.title}</span><small>{source.label || (source.source_kind==='conversation'?'历史会话':'资料')}{source.source_kind!=='conversation' ? ` · v${source.version}` : ''}</small></summary>
    {loading&&<p role="status">读取中…</p>}{error&&<p role="alert" className="form-error">{error}</p>}{loaded&&<><pre>{loaded.body}</pre><small>{loaded.updated_at ? new Date(loaded.updated_at).toLocaleString() : ''} · 摘录</small></>}
  </details>;
}

export function EvidenceSources({sources}:{sources:ContextSource[]}) {
  const refs=sources.filter(s=>s.chunk_id).filter((s,i,all)=>all.findIndex(item=>item.chunk_id===s.chunk_id)===i);
  return refs.length ? <details className="knowledge-citations"><summary>依据 · {refs.length}</summary>{refs.map(source=><Evidence key={source.chunk_id} source={source} />)}</details> : null;
}
