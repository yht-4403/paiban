import { useEffect, useRef, useState } from 'react';
import { Button, Checkbox, Input } from '@tutti-os/ui-system';
import { AddIcon, CheckIcon, ChevronDownIcon, CloseIcon, FileTextIcon, LoadingIcon, UploadIcon } from '@tutti-os/ui-system/icons';
import { api, command, type Document, type Material, type ResourceRef, type State, type Task, type ThreadData } from '../../shared/api';
import { dragEnd, dragStart } from '../../shared/drag';
import { Markdown } from '../../shared/Markdown';
import { scopeLabels } from './Materials';
import './context-tree.css';

export function ContextPanel({ state, data, busy, onUse, onTask, onDeleteTask, onRefresh, onThread, onFlow }: {
  state: State; data: ThreadData | null; busy: boolean; onDocument: (doc: ResourceRef) => void;
  onUse: (id: string) => void; onTask:(task:Task)=>void;onDeleteTask:(task:Task)=>void;onRefresh:()=>Promise<void>;onThread:(id:string)=>void;onFlow:(id:string)=>void;
}) {
  const [query,setQuery]=useState(''),[dropping,setDropping]=useState(false),[uploading,setUploading]=useState(false);
  const [preview,setPreview]=useState<Document|null>(null),[error,setError]=useState(''),[reading,setReading]=useState(false);
  const [receipt,setReceipt]=useState(''); const upload=useRef<HTMLInputElement>(null);
  const [menu,setMenu]=useState<{x:number;y:number;kind:'task'|'file';item:Task|Material}|null>(null);
  useEffect(()=>{const close=()=>setMenu(null);window.addEventListener('pointerdown',close);window.addEventListener('blur',close);return()=>{window.removeEventListener('pointerdown',close);window.removeEventListener('blur',close);};},[]);
  const available=data?.context.available??state.documents;
  const docs=available.filter(doc=>doc.scope==='team'&&doc.title.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  const canSelect=!busy&&(!data||(data.thread.owner_id===state.me&&data.thread.status==='agent'));
  const selected=new Set(data?.context.resources.map(doc=>doc.id));
  const tasks=state.tasks.filter(t=>t.assignee_id===state.me);
  const unfinished=tasks.filter(t=>t.status!=='done');
  const today=new Date().toLocaleDateString();
  const done=tasks.filter(t=>t.status==='done'&&t.updated_at&&new Date(t.updated_at).toLocaleDateString()===today);
  const summaries=state.flows?.filter(f=>f.kind==='task_summary')||[];
  const open=async(doc:Material)=>{setError('');setReading(true);try{setPreview(await api<Document>(`/resources/${doc.id}`));}catch(e){setError((e as Error).message);}finally{setReading(false);}};
  const publishFiles=async(files:File[])=>{if(!files.length||uploading)return;setError('');setReceipt('');setUploading(true);let saved=0;try{for(const file of files.slice(0,10)){const ext=file.name.split('.').pop()?.toLowerCase()||'';if(file.size>256000)throw new Error(`${file.name} 超过 256 KB。`);if(!file.type.startsWith('text/')&&!['md','markdown','txt','csv','json','yaml','yml','log','ts','tsx','js','jsx','py','html','css'].includes(ext))throw new Error(`${file.name} 暂不支持读取。`);const body=await file.text();if(!body.trim())throw new Error(`${file.name} 没有可读取的文字。`);if(body.length>16000)throw new Error(`${file.name} 超过 16,000 个字符。`);await command('/resources',{title:file.name.replace(/\.[^.]+$/,''),body,scope:'team',resource_ids:[]});saved++;}await onRefresh();setReceipt(`已放入 ${saved} 份`);}catch(e){setError((e as Error).message);}finally{setUploading(false);}};
  const saveDownload=(doc:Document)=>{const url=URL.createObjectURL(new Blob([doc.body],{type:'text/markdown;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=doc.title.replace(/[\\/:*?"<>|]/g,'_')+'.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  const download=()=>{if(preview)saveDownload(preview);};
  const downloadFile=async(doc:Material)=>{setError('');try{saveDownload(await api<Document>(`/resources/${doc.id}`));}catch(e){setError((e as Error).message);}};
  const taskRow=(task:Task)=>{const flow=summaries.find(f=>f.task_id===task.id);const working=flow&&['queued','running'].includes(flow.status);return <div className={`workbench-todo ${task.status==='done'?'is-done':''}`} data-tour-task={task.id} key={task.id} onContextMenu={event=>{event.preventDefault();setMenu({x:event.clientX,y:event.clientY,kind:'task',item:task});}}>{working?<LoadingIcon size={16}/>:<Checkbox data-tour-task-checkbox={task.id} checked={task.status==='done'} disabled={busy} aria-label={`${task.status==='done'?'重新打开':'整理完成'}：${task.title}`} onCheckedChange={()=>onTask(task)}/>}<button className="workbench-todo-main" onClick={()=>onThread(flow?.thread_id||task.thread_id)}><strong>{task.title}</strong>{working?<small>正在整理</small>:flow?.status==='needs_input'?<small>补充一句进展</small>:flow?.status==='error'?<small>整理未完成</small>:task.detail&&task.status!=='done'?<small>{task.detail}</small>:null}</button><Button className="workbench-todo-delete" variant="ghost" size="icon-xs" disabled={busy} aria-label={`删除待办：${task.title}`} title="删除待办" onClick={()=>onDeleteTask(task)}><CloseIcon /></Button></div>;};
  const file=(doc:Material)=><div className="resource-tree-file" key={doc.id} onContextMenu={event=>{event.preventDefault();setMenu({x:event.clientX,y:event.clientY,kind:'file',item:doc});}}><button draggable={canSelect} onDragStart={e=>dragStart(e,{kind:'resource',id:doc.id})} onDragEnd={dragEnd} onClick={()=>void open(doc)} title={`${doc.title} · ${scopeLabels[doc.scope]}`}><FileTextIcon size={16}/><span><strong>{doc.title}</strong></span></button><Button variant="ghost" size="icon-xs" disabled={!canSelect||selected.has(doc.id)} aria-label={`${selected.has(doc.id)?'已引用':'引用'}：${doc.title}`} onClick={()=>onUse(doc.id)}>{selected.has(doc.id)?<CheckIcon/>:<AddIcon/>}</Button></div>;
  return <aside className="context-panel resource-tree-panel workbench-context" aria-label="待办与工作池">
    <details className="workbench-todos" data-tour="todo-list" open><summary><ChevronDownIcon size={14}/><strong>待办</strong><small>{unfinished.length} 项</small></summary><div className="workbench-todo-list">{unfinished.map(taskRow)}{!unfinished.length&&<p className="context-description">暂无待办</p>}{(state.flows||[]).filter(f=>f.pending_action_count&&f.thread_id).map(f=><button className="todo-suggestion-link" key={f.id} onClick={()=>onThread(f.thread_id)}>{f.pending_action_count} 条待办建议 · {f.title}</button>)}{!!done.length&&<details className="today-completed"><summary>今日完成 · {done.length}</summary>{done.map(taskRow)}</details>}</div></details>
    <section className="workbench-pool" data-tour="work-pool" aria-label="工作池"><div className="context-title"><strong>工作池</strong></div>
      {preview ? <>
        <div className="pool-preview-toolbar"><Button size="xs" variant="ghost" onClick={()=>setPreview(null)}>返回</Button><Button size="xs" variant="ghost" onClick={download}>下载</Button><Button size="xs" variant="secondary" disabled={!canSelect} onClick={()=>onUse(preview.id)}>引用</Button></div>
        <div className="pool-preview"><strong>{preview.title}</strong><Markdown>{preview.body}</Markdown></div>
      </> : <>
        <input ref={upload} className="visually-hidden" type="file" multiple accept="text/*,.md,.markdown,.txt,.csv,.json,.yaml,.yml,.log,.ts,.tsx,.js,.jsx,.py,.html,.css" onChange={event=>{void publishFiles(Array.from(event.target.files||[]));event.currentTarget.value='';}}/>
        <button type="button" className={`pool-drop${dropping?' is-dropping':''}`} disabled={uploading} onClick={()=>upload.current?.click()} onDragOver={event=>{if(event.dataTransfer.types.includes('Files')){event.preventDefault();setDropping(true);}}} onDragLeave={()=>setDropping(false)} onDrop={event=>{if(event.dataTransfer.files.length){event.preventDefault();setDropping(false);void publishFiles(Array.from(event.dataTransfer.files));}}}>
          <UploadIcon size={15}/><span>{uploading?'正在放入…':'拖入成品'}</span>
        </button>
        {receipt&&<span className="pool-receipt" role="status">{receipt}</span>}
        <Input aria-label="筛选工作池文件" placeholder="搜索" value={query} onChange={e=>setQuery(e.target.value)}/>
        <div className="resource-tree">{docs.map(file)}{!docs.length&&<p className="context-description">{query?'没有找到':'暂无内容'}</p>}</div>
      </>}
      {reading&&<span role="status">正在打开…</span>}{error&&<p role="alert" className="form-error">{error}</p>}
    </section>
    {state.flows?.filter(flow=>flow.owner_id===state.me&&flow.follow_up_ready).map(flow=><button className="todo-suggestion-link follow-up-link" key={flow.id} onClick={()=>onFlow(flow.id)}>下一次同步已就绪 · {flow.title}</button>)}
    {menu&&<div className="context-quick-menu" role="menu" style={{left:Math.min(menu.x,window.innerWidth-180),top:Math.min(menu.y,window.innerHeight-150)}} onPointerDown={event=>event.stopPropagation()}>{menu.kind==='file'?<>{<button role="menuitem" onClick={()=>{void open(menu.item as Material);setMenu(null);}}>打开</button>}<button role="menuitem" onClick={()=>{void downloadFile(menu.item as Material);setMenu(null);}}>下载</button><button role="menuitem" disabled={!canSelect} onClick={()=>{onUse((menu.item as Material).id);setMenu(null);}}>引用到对话</button></>:<><button role="menuitem" onClick={()=>{const task=menu.item as Task;const flow=summaries.find(item=>item.task_id===task.id);onThread(flow?.thread_id||task.thread_id);setMenu(null);}}>打开</button><button role="menuitem" onClick={()=>{const task=menu.item as Task;window.dispatchEvent(new CustomEvent('accord:insert-text',{detail:`待办：${task.title}${task.detail?`\n${task.detail}`:''}`}));setMenu(null);}}>引用到对话</button>{(menu.item as Task).status!=='done'&&<button role="menuitem" disabled={busy} onClick={()=>{onTask(menu.item as Task);setMenu(null);}}>整理完成</button>}</>}</div>}
  </aside>;
}
