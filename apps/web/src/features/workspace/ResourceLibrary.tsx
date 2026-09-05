import { ImportFiles, KnowledgeSearch, LarkConnections } from './KnowledgeTools';
import { useRef, useState } from 'react';
import { Button, Checkbox, Input, Textarea } from '@tutti-os/ui-system';
import { AddIcon, FileTextIcon, FolderIcon, UploadIcon } from '@tutti-os/ui-system/icons';
import type { Document, ResourceRef, State } from '../../shared/api';
import { dragEnd, dragStart } from '../../shared/drag';
import { useMutation } from '../../shared/useMutation';
import { scopeLabels } from './Materials';

export function ResourceLibrary({state,onRefresh,onResource,onUse}: {state:State;onRefresh:()=>Promise<void>;onResource:(resource:ResourceRef)=>void;onUse:(id:string)=>void}) {
  const [editing,setEditing]=useState<Document | 'new' | null>(null); const [filter,setFilter]=useState('all'); const [searching,setSearching]=useState(false);
  const items=state.documents.filter(resource=>(filter==='all' || resource.scope===filter));
  return <div className="content-page resource-library"><div className="page-intro page-intro-actions"><div><h1>资料</h1></div><div className="library-actions"><ImportFiles onRefresh={onRefresh}/><Button onClick={()=>setEditing('new')}><AddIcon />新建资料</Button></div></div>
    <KnowledgeSearch onSearchChange={setSearching} />
    {!searching && <LarkConnections state={state} onRefresh={onRefresh} />}
    {!searching && <div className="library-filters"><div className="work-filters">{[['all','全部'],['private','仅自己'],['team','团队'],['round','课题']].map(([id,label])=><button key={id} className={filter===id ? 'active' : ''} onClick={()=>setFilter(id)}>{label}</button>)}</div></div>}
    {editing && <ResourceEditor key={editing==='new' ? 'new' : editing.id} resource={editing==='new' ? undefined : editing} state={state} onRefresh={onRefresh} close={()=>setEditing(null)} />}
    {!searching && <div className="document-list">{items.map(resource=><article className="resource-row" key={resource.id} draggable onDragStart={event=>dragStart(event,{kind:'resource',id:resource.id})} onDragEnd={dragEnd}>
      <button className="resource-open" onClick={()=>onResource(resource)}><span className="file-tile">{resource.kind==='collection' ? <FolderIcon size={18} /> : <FileTextIcon size={18} />}</span><span><strong>{resource.title}</strong><small>{scopeLabels[resource.scope]} · v{resource.version}{resource.refs.length ? ` · ${resource.refs.length} 份引用` : ''}</small></span></button>
      <div className="resource-row-actions"><Button variant="ghost" size="xs" onClick={()=>onUse(resource.id)}>用于新聊天</Button>{resource.unit_id===state.me && ['note','collection','memory'].includes(resource.kind) && <Button variant="ghost" size="xs" onClick={()=>setEditing(resource)}>编辑</Button>}</div>
    </article>)}</div>}{!searching && !items.length && !editing && <div className="empty-state"><h2>保存工作需要的资料</h2><p>支持正文、Markdown 文件和资料集合。</p></div>}
  </div>;
}

export function ResourceEditor({resource,state,onRefresh,close,initialScope='private'}: {initialScope?:'private'|'team';resource?:Document;state:State;onRefresh:()=>Promise<void>;close:()=>void}) {
  const [title,setTitle]=useState(resource?.title || ''); const [body,setBody]=useState(resource?.body || '');
  const [scope,setScope]=useState(resource ? resource.scope==='team'?'team':'private' : initialScope); const [refs,setRefs]=useState(resource?.refs.map(r=>r.id) || []);
  const [showRefs,setShowRefs]=useState(!!refs.length); const file=useRef<HTMLInputElement>(null);
  const {busy,error,setError,mutate}=useMutation(onRefresh);
  const readFile=async (upload?:File)=> {
    if (!upload) return;
    if (!/\.(md|txt|markdown)$/i.test(upload.name) || upload.size>64000) { setError('请选择不超过 64 KB 的 Markdown 或文本文件。'); return; }
    try { const content=await upload.text(); if (content.length>16000 || content.includes('\u0000')) { setError('正文最多 16000 字，请拆成较小的资料。'); return; } setBody(content); if (!title) setTitle(upload.name.replace(/\.[^.]+$/,'')); setError(''); } catch { setError('文件读取失败，请重试。'); }
  };
  const save=async()=> {
    const result=await mutate(resource ? `/resources/${resource.id}/update` : '/resources',{title,body,scope,resource_ids:refs,...(resource ? {expected_version:resource.version} : {})});
    if (result) close();
  };
  return <form className="inline-editor resource-editor" onSubmit={event=> { event.preventDefault(); void save(); }}>
    <div className="inline-editor-heading"><strong>{resource ? '更新资料' : '新建资料'}</strong><div className="work-filters"><button type="button" className={scope==='private' ? 'active' : ''} onClick={()=>setScope('private')}>仅自己</button><button type="button" className={scope==='team' ? 'active' : ''} onClick={()=>setScope('team')}>团队共享</button></div></div>
    <Input aria-label="资料标题" placeholder="资料标题" value={title} maxLength={160} onChange={event=>setTitle(event.target.value)} autoFocus />
    <Textarea aria-label="资料正文" placeholder="写下需要保留的内容…" value={body} maxLength={16000} onChange={event=>setBody(event.target.value)} />
    <div className="resource-editor-tools"><input ref={file} type="file" accept=".md,.txt,.markdown,text/plain,text/markdown" hidden onChange={event=> { void readFile(event.target.files?.[0]); event.target.value=''; }} /><Button type="button" variant="ghost" size="sm" onClick={()=>file.current?.click()}><UploadIcon />导入文本文件</Button><Button type="button" variant="ghost" size="sm" onClick={()=>setShowRefs(!showRefs)}><FolderIcon />组合资料</Button></div>
    {showRefs && <div className="collection-picker">{state.documents.filter(item=>item.id!==resource?.id).map(item=><label key={item.id} className="source-option"><Checkbox checked={refs.includes(item.id)} disabled={!refs.includes(item.id) && ((scope==='team' && item.scope!=='team') || refs.length>=12)} onCheckedChange={checked=>setRefs(ids=>checked ? [...ids,item.id] : ids.filter(id=>id!==item.id))} /><span>{item.title}<small>{scopeLabels[item.scope]}</small></span></label>)}</div>}
    {error && <p className="form-error" role="alert">{error}</p>}<div className="inline-editor-footer"><span>{scope==='private' ? '仅自己可见' : '工作空间全体成员可见'}</span><Button type="button" variant="ghost" disabled={busy} onClick={close}>取消</Button><Button type="submit" disabled={busy || !title.trim() || (!body.trim() && !refs.length)}>{scope==='team' ? '发布给团队' : '保存资料'}</Button></div>
  </form>;
}
