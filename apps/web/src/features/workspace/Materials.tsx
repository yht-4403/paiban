import { useState } from 'react';
import { Button, Checkbox, Input, Popover, PopoverContent, PopoverTrigger } from '@tutti-os/ui-system';
import { AddIcon, CloseIcon, FileTextIcon, FolderIcon } from '@tutti-os/ui-system/icons';
import type { Material, ResourceRef } from '../../shared/api';
import { acceptsDrag, receiveDrop } from '../../shared/drag';

export const scopeLabels = { private:'仅自己', team:'团队共享', round:'课题成员' };

export function MaterialPicker({ resources, available, onToggle, busy, label='加入资料', availableFolders=[], folders=[], onFolder }: {
  resources: Material[]; available: Material[]; onToggle: (id: string, selected: boolean) => void; busy: boolean; label?: string;
  availableFolders?: {id:string;name:string}[]; folders?: {id:string;name:string}[]; onFolder?: (id:string,selected?:boolean)=>void;
}) {
  const [query,setQuery]=useState('');
  const visible=available.filter(resource=>resource.title.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  return <Popover><PopoverTrigger asChild><Button variant="ghost" size="sm" disabled={busy}><AddIcon />{label}</Button></PopoverTrigger>
    <PopoverContent align="start" className="source-picker material-picker"><Input aria-label="搜索可用资料" placeholder="搜索资料" value={query} onChange={event=>setQuery(event.target.value)} />
      <div className="material-options">{onFolder && availableFolders.filter(folder=>folder.name.includes(query.trim())).map(folder=><label className="source-option" key={folder.id}><Checkbox checked={folders.some(item=>item.id===folder.id)} disabled={busy} onCheckedChange={checked=>onFolder(folder.id,!!checked)} /><FolderIcon size={14} /><span>{folder.name}<small>文件夹资料</small></span></label>)}{visible.map(resource=> { const selected=resources.find(item=>item.id===resource.id); return <label className="source-option" key={resource.id}>
        <Checkbox checked={!!selected} disabled={busy || selected?.origin==='round' || (!selected && resources.length>=20)} onCheckedChange={checked=>onToggle(resource.id,!!checked)} />
        {resource.kind==='collection' ? <FolderIcon size={14} /> : <FileTextIcon size={14} />}<span>{resource.title}<small>{scopeLabels[resource.scope]} · v{resource.version}</small></span>
      </label>; })}{!visible.length && <p className="context-description">{query ? '没有匹配的资料' : '暂无可用资料'}</p>}</div>
    </PopoverContent></Popover>;
}

export function Materials({ folders, availableFolders, resources, available, busy, pending, onToggle, onFolder, onOpen }: {
  resources: Material[]; available: Material[]; busy: boolean; pending?: boolean; folders?: {id: string; name: string}[];
  availableFolders?: {id:string;name:string}[];
  onToggle: (id: string, selected: boolean) => void; onFolder?: (id: string, selected?: boolean) => void; onOpen: (resource: ResourceRef) => void;
}) {
  const [hover,setHover]=useState(false);
  return <div className={`materials-strip ${hover ? 'drop-active' : ''}`} aria-label="当前资料区"
    onDragOver={event=> { if (!busy && acceptsDrag(event,onFolder ? ['resource','folder'] : ['resource'])) { event.preventDefault(); event.dataTransfer.dropEffect='copy'; setHover(true); } }}
    onDragLeave={event=> { if (!event.currentTarget.contains(event.relatedTarget as Node)) setHover(false); }}
    onDrop={event=> { setHover(false); const item=receiveDrop(event,onFolder ? ['resource','folder'] : ['resource']); if (!item || busy) return; if (item.kind==='folder') onFolder?.(item.id); else onToggle(item.id,true); }}>
    <div className="materials-label"><span>资料{pending && <small>下次使用</small>}</span><MaterialPicker resources={resources} available={available} onToggle={onToggle} busy={busy} availableFolders={availableFolders} folders={folders} onFolder={onFolder} /></div>
    <div className="material-tags">{folders?.map(folder=><div className="material-tag folder-reference" key={folder.id}><span><FolderIcon size={12} />{folder.name}</span><Button variant="ghost" size="icon-xs" disabled={busy} aria-label={`移除文件夹资料：${folder.name}`} onClick={()=>onFolder?.(folder.id,false)}><CloseIcon /></Button></div>)}{resources.map(resource=><div className="material-tag" key={resource.id}>
      <button onClick={()=>onOpen(resource)} title={`${resource.title} · v${resource.version}`}><FileTextIcon size={12} /><span>{resource.title}</span>{resource.origin==='folder' && <FolderIcon size={11} />}</button>
      {resource.origin==='round' ? <small>本轮</small> : <Button variant="ghost" size="icon-xs" aria-label={`移除资料：${resource.title}`} disabled={busy} onClick={()=>onToggle(resource.id,false)}><CloseIcon /></Button>}
    </div>)}{!resources.length && <span className="material-empty">{hover ? '松开加入资料' : onFolder ? '拖入资料或文件夹' : '拖入资料'}</span>}</div>
  </div>;
}
