import { ChatList } from '../chat/ChatList';
import { useState } from 'react';
import { Avatar, Button, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger, Input } from '@tutti-os/ui-system';
import { AddIcon, ChevronDownIcon, FileTextIcon, FolderIcon, MessageSquareTextIcon, MoreHorizontalIcon, SearchIcon, SettingsIcon, UserLinedIcon } from '@tutti-os/ui-system/icons';
import type { Folder, State, Thread } from '../../shared/api';
import type { View } from '../../shared/routes';
import { acceptsDrag, dragEnd, dragStart, receiveDrop } from '../../shared/drag';
export type { View } from '../../shared/routes';

export function Sidebar({ state, view, setView, selected, selectThread, newThread, query, setQuery, settings, open, collapsed, close, onFolder, onMove, onFolderMaterial, onAction, busy, onMember }: {
  onMember:(id:string)=>void; state: State; view: View; setView: (view: View) => void; selected: string | null; selectThread: (id: string) => void; newThread: () => void;
  query: string; setQuery: (value: string) => void; settings: () => void; open: boolean; collapsed: boolean; close: () => void;
  onFolder: (id: string) => void; onMove: (thread: Thread, folderId: string) => void; onFolderMaterial: (folder: Folder, resourceId: string) => void;
  onAction: (path: string, body: Record<string,unknown>) => Promise<boolean>; busy: boolean;
}) {
  const me=state.members.find(member=>member.id===state.me)!;
  const [creating,setCreating]=useState(false); const [name,setName]=useState('');
  const [expanded,setExpanded]=useState<string[]>([]); const [dropTarget,setDropTarget]=useState<string | null>(null);
  const [renaming,setRenaming]=useState<string | null>(null); const [rename,setRename]=useState('');
  const inbox=state.threads.filter(thread=>thread.target_id===state.me && ['waiting','human'].includes(thread.status)).length;
  const threads=state.threads.filter(thread=>thread.kind==='workspace' && thread.title.toLocaleLowerCase().includes(query.toLocaleLowerCase().trim()));
  const drawThread=(thread:Thread)=><div key={thread.id} className={`thread-entry ${selected===thread.id && view==='workspace' ? 'selected' : ''}`}>
    <Button draggable onDragStart={event=>dragStart(event,{kind:'thread',id:thread.id})} onDragEnd={dragEnd} variant="ghost" className="thread-row" onClick={()=>selectThread(thread.id)} title={thread.title}><MessageSquareTextIcon /><span>{thread.title}</span>{thread.status==='waiting' && <span className="notification-dot" />}</Button>
    <DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon-xs" aria-label={`移动聊天：${thread.title}`} disabled={busy}><MoreHorizontalIcon /></Button></DropdownMenuTrigger><DropdownMenuContent align="start"><DropdownMenuLabel>移动到</DropdownMenuLabel><DropdownMenuItem disabled={!thread.folder_id} onSelect={()=>onMove(thread,'')}>未分类</DropdownMenuItem>{state.folders.map(folder=><DropdownMenuItem key={folder.id} disabled={folder.id===thread.folder_id} onSelect={()=>onMove(thread,folder.id)}><FolderIcon />{folder.name}</DropdownMenuItem>)}</DropdownMenuContent></DropdownMenu>
  </div>;
  const drop=(event:React.DragEvent, folder:Folder | null)=> { const item=receiveDrop(event,folder ? ['thread','resource'] : ['thread']); setDropTarget(null); if (!item || busy) return;
    if (folder) setExpanded(ids=>[...new Set([...ids,folder.id])]);
    if (item.kind==='thread') { const thread=state.threads.find(t=>t.id===item.id); if (thread && thread.folder_id!==(folder?.id || '')) onMove(thread,folder?.id || ''); }
    else if (folder) onFolderMaterial(folder,item.id);
  };
  return <><button className={`sidebar-shade ${open ? 'visible' : ''}`} onClick={close} aria-label="关闭导航" tabIndex={open ? 0 : -1} />
    <aside className={`sidebar ${open ? 'sidebar-open' : ''} ${collapsed ? 'sidebar-collapsed' : ''}`} aria-label="工作区导航">
      <div className="sidebar-brand"><span className="sidebar-wordmark">accord</span><span>{state.project.name}</span></div>
      <div className="workspace-mode" aria-label="选择工作台或聊天"><button className={view!=='chat' ? 'active' : ''} onClick={()=>setView('workspace')}>工作台</button><button className={view==='chat' ? 'active' : ''} onClick={()=>setView('chat')}>聊天{inbox>0 && <span>{inbox}</span>}</button></div>{view==='chat' ? <><div className="sidebar-search"><SearchIcon size={14} /><Input aria-label="搜索同事" placeholder="搜索同事" value={query} onChange={event=>setQuery(event.target.value)} /></div><ChatList state={state} selected={state.threads.find(thread=>thread.id===selected)} query={query} busy={busy} onMember={onMember} /></> : <><Button className="new-button" variant="secondary" onClick={newThread}><AddIcon />新的工作<span className="shortcut">⌘ K</span></Button>
      <div className="sidebar-search"><SearchIcon size={14} /><Input aria-label="搜索协作标题" placeholder="搜索协作…" value={query} onChange={event=>setQuery(event.target.value)} /></div>
      <nav className="primary-nav"><Button variant="ghost" className={`nav-row ${view==='library' ? 'selected' : ''}`} onClick={()=>setView('library')}><FileTextIcon /><span>资料</span></Button></nav>
      <div className="work-filters" aria-label="工作筛选">{([['workspace','全部'],['inbox',inbox ? `需要你 ${inbox}` : '需要你'],['tasks','待办'],['topics','课题']] as [View,string][]).map(([id,label])=><button key={id} className={view===id ? 'active' : ''} aria-current={view===id ? 'page' : undefined} onClick={()=>setView(id)}>{label}</button>)}</div>
      <div className="sidebar-section-title"><span>文件夹</span><Button variant="ghost" size="icon-xs" aria-label="新建文件夹" onClick={()=>setCreating(!creating)}><AddIcon /></Button></div>
      {creating && <form className="folder-create" onSubmit={event=> { event.preventDefault(); if (name.trim()) void onAction('/folders',{name:name.trim()}).then(ok=> { if (ok) { setCreating(false); setName(''); } }); }}><Input aria-label="文件夹名称" autoFocus value={name} maxLength={60} onChange={event=>setName(event.target.value)} onKeyDown={event=> { if (event.key==='Escape') setCreating(false); }} /><Button type="submit" size="sm" disabled={busy || !name.trim()}>创建</Button></form>}
      <div className="sidebar-scroll">{state.folders.map(folder=> { const children=threads.filter(thread=>thread.folder_id===folder.id); const isOpen=expanded.includes(folder.id) || !!query;
        return <section key={folder.id} className="folder-group"><div className={`folder-row ${dropTarget===folder.id ? 'drop-active' : ''}`} onDragOver={event=> { if (!busy && acceptsDrag(event,['thread','resource'])) { event.preventDefault(); setDropTarget(folder.id); } }} onDragLeave={()=>setDropTarget(null)} onDrop={event=>drop(event,folder)}>
          <Button variant="ghost" size="icon-xs" aria-label={`${isOpen ? '收起' : '展开'}文件夹：${folder.name}`} aria-expanded={isOpen} onClick={()=>setExpanded(ids=>isOpen ? ids.filter(id=>id!==folder.id) : [...ids,folder.id])}><ChevronDownIcon className={isOpen ? '' : 'folder-chevron-closed'} /></Button>
          {renaming===folder.id ? <form className="folder-rename" onSubmit={event=> { event.preventDefault(); void onAction(`/folders/${folder.id}/rename`,{name:rename,expected_version:folder.version}).then(ok=>ok && setRenaming(null)); }}><Input autoFocus aria-label="重命名文件夹" value={rename} maxLength={60} onChange={event=>setRename(event.target.value)} onKeyDown={event=> { if (event.key==='Escape') setRenaming(null); }} /><Button type="submit" size="xs" disabled={busy || !rename.trim()}>保存</Button></form> : <button className="folder-name" draggable onDragStart={event=>dragStart(event,{kind:'folder',id:folder.id})} onDragEnd={dragEnd} onClick={()=>onFolder(folder.id)}><FolderIcon size={14} /><span>{folder.name}</span>{folder.binding.included.length>0 && <FileTextIcon size={11} />}</button>}
          <DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon-xs" aria-label={`文件夹操作：${folder.name}`} disabled={busy}><MoreHorizontalIcon /></Button></DropdownMenuTrigger><DropdownMenuContent><DropdownMenuItem onSelect={()=>onFolder(folder.id)}>打开资料与聊天</DropdownMenuItem><DropdownMenuItem onSelect={()=> { setRename(folder.name); setRenaming(folder.id); }}>重命名</DropdownMenuItem><DropdownMenuSeparator /><DropdownMenuItem disabled={state.threads.some(t=>t.folder_id===folder.id)} onSelect={()=>void onAction(`/folders/${folder.id}/remove`,{expected_version:folder.version})}>移除空文件夹</DropdownMenuItem></DropdownMenuContent></DropdownMenu>
        </div>{isOpen && <div className="folder-threads">{children.map(drawThread)}{!children.length && <p className="sidebar-empty">{query ? '没有匹配的聊天' : '拖入聊天'}</p>}</div>}</section>;
      })}<div className={`unfiled-label ${dropTarget==='' ? 'drop-active' : ''}`} onDragOver={event=> { if (!busy && acceptsDrag(event,['thread'])) { event.preventDefault(); setDropTarget(''); } }} onDragLeave={()=>setDropTarget(null)} onDrop={event=>drop(event,null)}>未分类</div>{threads.filter(thread=>!thread.folder_id).map(drawThread)}{!threads.length && <p className="sidebar-empty">{query ? '没有找到相关协作' : '从新的协作开始'}</p>}</div></>}
      <div className="sidebar-bottom"><Button variant="ghost" className="profile-button" onClick={settings}><Avatar label={me.person_name} initial={me.person_name[0]} size={26} /><span><strong>{me.person_name}</strong><small>{me.window==='closed' ? '专注中' : '可协作'}</small></span><SettingsIcon /></Button></div>
    </aside></>;
}
