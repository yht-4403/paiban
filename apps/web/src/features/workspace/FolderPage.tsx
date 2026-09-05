import { Button } from '@tutti-os/ui-system';
import { AddIcon, FolderIcon, MessageSquareTextIcon } from '@tutti-os/ui-system/icons';
import type { Folder, ResourceRef, State } from '../../shared/api';
import { dragEnd, dragStart } from '../../shared/drag';
import { Materials } from './Materials';

export function FolderPage({folder,state,busy,onNew,onThread,onBind,onResource}: {
  folder:Folder | undefined; state:State; busy:boolean; onNew:()=>void; onThread:(id:string)=>void;
  onBind:(id:string,selected:boolean)=>void; onResource:(resource:ResourceRef)=>void;
}) {
  if (!folder) return <div className="empty-state"><h2>文件夹不存在</h2></div>;
  const threads=state.threads.filter(thread=>thread.folder_id===folder.id);
  const materials=state.documents.filter(resource=>folder.binding.included.includes(resource.id));
  return <div className="content-page folder-page"><div className="page-intro page-intro-actions"><div><span className="section-eyebrow"><FolderIcon size={14} />我的文件夹</span><h1>{folder.name}</h1></div><Button onClick={onNew} disabled={busy}><AddIcon />新建聊天</Button></div>
    <Materials resources={materials} available={state.documents} busy={busy} onToggle={onBind} onOpen={onResource} />
    <div className="folder-chat-list">{threads.map(thread=><button key={thread.id} className="folder-chat-row" draggable onDragStart={event=>dragStart(event,{kind:'thread',id:thread.id})} onDragEnd={dragEnd} onClick={()=>onThread(thread.id)}><MessageSquareTextIcon size={16} /><span>{thread.title}<small>{thread.purpose==='exploration' ? '独立探索' : thread.purpose==='review' ? '方案比较' : thread.kind==='workspace' ? '仅自己' : thread.status==='agent' ? 'Agent 通道' : '双方协作'}</small></span></button>)}{!threads.length && <div className="empty-state"><h2>暂无聊天</h2></div>}</div>
  </div>;
}
