import { EvidenceSources } from './KnowledgeTools';
import { ChatSummary } from '../coordination/Flows';
import { GroupComposer, GroupMembers } from '../chat/GroupConversation';
import { GroupPicker } from '../chat/GroupPicker';
import { copyText } from '../../shared/browser';
import { Fragment, useEffect, useRef, useState } from 'react';
import { Avatar, Badge, Button, Popover, PopoverContent, PopoverTrigger } from '@tutti-os/ui-system';
import { CheckIcon, FileTextIcon, LoadingIcon, MessageSquareTextIcon, UserLinedIcon } from '@tutti-os/ui-system/icons';
import { api, reasoningLabels, statusLabels, timeLabel, type State, type ThreadData, type Document, type ProcessAttachment, type ProcessAttachmentInput, type ResourceRef } from '../../shared/api';
import { Pending } from '../../shared/ui';
import { Markdown } from '../../shared/Markdown';
import { ConversationInput, ConversationTask, type ConversationAction } from './ConversationInput';
import { useMutation } from '../../shared/useMutation';
import { InlineCollaboration } from './InlineCollaboration';
import { acceptsDrag, receiveDrop } from '../../shared/drag';

export function Conversation({ state, data, loading, busy, onSend, onHandoff, onConfirm, onDocument, onNew, draftKey, onRun, onResource, onBind, onFolder, onRefresh, onOpen, onTopic, onSubmission, onNewChatItem, onCreateGroup, onGroupSend }: {
  state: State; data: ThreadData | null; loading: boolean; busy: boolean; onSend: (body: string, sourceIds: string[], attachments?: ProcessAttachmentInput[]) => Promise<boolean>;
  onHandoff: () => void; onConfirm: () => void; onDocument: (doc: Document) => void; onNew: () => void; draftKey: number;
  onCreateGroup:(ids:string[])=>Promise<boolean>; onGroupSend:(body:string,agentId:string,attachments?:ProcessAttachmentInput[])=>Promise<boolean>; onNewChatItem:(peerId:string)=>void; onRun: (id: string, action: 'stop' | 'retry') => void;
  onResource: (resource:ResourceRef)=>void; onBind:(id:string,selected:boolean)=>void; onFolder:(id:string,selected?:boolean)=>void; onRefresh:()=>Promise<void>; onOpen:(id:string)=>void; onTopic:(id:string)=>void; onSubmission:(roundId:string,body:string)=>void;
}) {
  const [action,setAction]=useState<{kind:'handoff'|'confirm'|'share';target?:string} | null>(null);
  const [attachmentMenu,setAttachmentMenu]=useState<{x:number;y:number;item:ProcessAttachment}|null>(null);
  const [attachmentError,setAttachmentError]=useState('');
  const [dropHover,setDropHover]=useState(false);
  const actionMutation=useMutation(onRefresh);
  const performAction: ConversationAction=async(path,body)=> {
    if (/^\/tasks\/[^/]+\/status$/.test(path)&&body.status==='done') {
      const privateWorkspace=data?.thread.kind==='workspace'&&data.thread.purpose==='ordinary'&&!state.context_sharing?.some(g=>g.source_kind==='conversation'&&g.source_id===data.thread.id&&g.enabled);
      const result=await actionMutation.mutate<{thread_id:string}>(path.replace('/status','/tick'),{thread_id:privateWorkspace?data!.thread.id:''});
      if(result?.thread_id)onOpen(result.thread_id);return !!result;
    }
    return (await actionMutation.mutate(path,body)) !== undefined;
  };
  useEffect(()=>setAction(null),[data?.thread.id]);
  useEffect(()=>{const close=()=>setAttachmentMenu(null);window.addEventListener('pointerdown',close);window.addEventListener('blur',close);return()=>{window.removeEventListener('pointerdown',close);window.removeEventListener('blur',close);};},[]);
  const readableAttachment=(item:ProcessAttachment)=>item.mime_type.startsWith('text/')||['md','markdown','txt','csv','json','yaml','yml','log','ts','tsx','js','jsx','py','html','css'].includes(item.filename.split('.').pop()?.toLowerCase()||'');
  const openAttachment=async(item:ProcessAttachment,download=false)=>{
    setAttachmentError('');
    try{
      const payload=await api<{filename:string;mime_type:string;content:string}>(`/attachments/${item.id}`);
      const blob=payload.content.startsWith('data:')?await (await fetch(payload.content)).blob():new Blob([payload.content],{type:payload.mime_type||'text/plain;charset=utf-8'});
      const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=download?payload.filename:'';if(!download)link.target='_blank';link.rel='noopener';link.click();window.setTimeout(()=>URL.revokeObjectURL(url),10000);
    }catch(error){setAttachmentError((error as Error).message);}
  };
  const scroll = useRef<HTMLDivElement>(null); const pinned = useRef(true);
  const [unread,setUnread] = useState(false); const [copied,setCopied] = useState('');
  const revision = data?.messages.map(m=>m.id+m.body.length+m.meta.status).join();
  const bottom = () => { if (scroll.current) scroll.current.scrollTop=scroll.current.scrollHeight; pinned.current=true; setUnread(false); };
  useEffect(() => { if (pinned.current) bottom(); else setUnread(true); },[revision,loading]);
  useEffect(() => { pinned.current=true; bottom(); },[data?.thread.id]);
  if (loading) return <Pending label="正在打开协作" />;
  const thread = data?.thread;
  const canSubmit=thread?.purpose==='exploration' && state.topics.some(topic=>topic.id===thread.round_id && topic.stage==='exploring');
  const peer = state.members.find(m=>m.id===thread?.target_id);
  const human = !!thread && ['waiting','human','resolved','closed'].includes(thread.status);
  const displayMember = thread?.target_id===state.me && (human || thread.status==='resolved') ? state.members.find(m=>m.id===thread.owner_id) : peer;
  const peerChat=thread?.kind==='peer';
  const groupChat=thread?.kind==='group';
  const currentMessages=data?.messages.filter(message=>message.conversation_id===thread?.id) || [];
  const isEmpty = !data?.messages.length;
  const active = currentMessages.find(m=>['queued','running'].includes(m.meta.status || ''));
  const composerId = `accord.draft.${state.me}.${thread?.id || 'new'}`;
  const modelLabel = state.model.label + (state.model.reasoning_options?.length ? ` · ${reasoningLabels[state.model.reasoning_effort]}思考` : '');
  const completion=state.flows?.find(f=>f.kind==='task_summary'&&f.thread_id===thread?.id&&['queued','running','needs_input','error'].includes(f.status));
  const closed=thread?.status==='closed';
  const sharedConversation=!!state.context_sharing?.some(g=>g.source_kind==='conversation'&&g.source_id===thread?.id&&g.enabled);
  const flow=state.flows?.find(f=>f.thread_id===thread?.id && ['chat_summary','decision'].includes(f.kind));
  const composer = closed ? <div className="chat-closed"><span>本轮已结束</span>{peerChat&&displayMember&&<Button variant="secondary" onClick={()=>onNewChatItem(displayMember.id)}>新的事项</Button>}</div> : groupChat && data ? <GroupComposer key={thread.id} state={state} data={data} busy={busy} humanOnly={flow?.kind==='decision'} onSend={onGroupSend} onRun={onRun} /> : <ConversationInput key={composerId+draftKey} thread={thread} messages={currentMessages} state={state} onAction={performAction} composer={{draftId: composerId, documents: state.documents, folders: state.folders, context: data?.context, onBind: onBind, onFolder: onFolder, onResource: onResource, pendingContext: !!data?.active_context.some(snapshot=>snapshot.binding_version!==data.context.binding.version || snapshot.folder_id!==data.context.folder_id || snapshot.folder_version!==data.context.folder_version || JSON.stringify((snapshot.roots || snapshot.resources).map(r=>[r.id,r.version]))!==JSON.stringify(data.context.resources.map(r=>[r.id,r.version]))), onSend: async (body,sources,attachments)=> { pinned.current=true; return onSend(body,sources,attachments); }, busy: busy || actionMutation.busy, human: human, model: modelLabel, workspace: state.project.name, running: !!active, allowAttachments:!completion&&(!thread||thread.purpose==='ordinary'), onStop: ()=>active?.meta.completion_id ? void performAction(`/task-summaries/${active.meta.completion_id}/cancel`,{}) : active?.meta.run_id && onRun(active.meta.run_id,'stop')}} />;
  return <div className={`conversation ${peerChat || groupChat ? 'person-conversation' : ''} ${groupChat ? 'group-conversation' : ''} ${isEmpty ? 'conversation-empty' : ''}`}>
    {thread && <div className={`conversation-heading phase-${thread.status}`}><div><Avatar label={displayMember?.person_name || '我的 Agent'} initial={groupChat ? '#' : thread.kind==='workspace' ? 'A' : displayMember?.person_name[0]} size={24} /><div><strong>{thread.kind==='workspace' ? '我的 Agent' : groupChat ? thread.title : displayMember?.person_name}</strong><span>{groupChat ? <Popover><PopoverTrigger asChild><button className="group-member-trigger" aria-label="查看群成员">{thread.member_ids?.length || 0} 位成员</button></PopoverTrigger><PopoverContent className="group-member-popover" align="start"><GroupMembers state={state} thread={thread} busy={busy} onAction={performAction} /></PopoverContent></Popover> : thread.kind==='workspace' ? sharedConversation ? '团队可读' : '仅你可见' : thread.status==='agent' ? `${peer?.person_name}的 Agent 代答` : statusLabels[thread.status]}</span></div></div>
      {peerChat && displayMember && <div className="person-chat-presence"><span title={displayMember.activity?.source}>{displayMember.activity?.label || '可协作'}</span>{displayMember.activity?.agent_working && <small>Agent 正在工作</small>}{displayMember.activity?.work && <small>{displayMember.activity.work.title}</small>}</div>}
      {peerChat && <GroupPicker initial={displayMember ? [displayMember.id] : []} members={state.members.filter(member=>member.id!==state.me)} onChoose={onCreateGroup} />}
      {peerChat && ['resolved','closed'].includes(thread.status) && <Button variant="ghost" size="xs" disabled={busy} onClick={()=>onNewChatItem(displayMember!.id)}>新的事项</Button>}
    </div>}
    {peerChat && displayMember?.activity && displayMember.activity.progress.total>0 && <details className="chat-shared-progress"><summary>共享待办 · {displayMember.activity.progress.completed}/{displayMember.activity.progress.total} 已完成</summary>{displayMember.activity.shared_tasks.map(task=><button key={task.id} onClick={()=>onOpen(task.thread_id)}><span>{task.title}</span><small>{task.priority==='high' ? '高优先级 · ' : ''}{task.status==='done' ? '已完成' : '进行中'}</small></button>)}</details>}
    {thread?.round_id && <div className="topic-chat-band"><button onClick={()=>onTopic(thread.round_id)}>{state.topics.find(topic=>topic.id===thread.round_id)?.title || '课题'}</button><span>{thread.purpose==='exploration' ? '独立探索 · 仅自己' : thread.purpose==='review' ? '我的方案比较' : '决策交接'}</span>{canSubmit && <Button size="xs" variant="ghost" disabled={busy || !!active || !data?.messages.length} onClick={()=>void onSend('请根据共同简报和本段探索，整理一份可提交的方案，包含主张、证据、限制和下一步。保留未验证事项，不提交或公开。',[])}>整理方案</Button>}</div>}
    {thread?.kind==='workspace' && thread.purpose==='ordinary' && <div className={`participants-target ${dropHover ? 'drop-active' : ''}`} aria-label="参与者区域" onDragOver={event=> { if (acceptsDrag(event,['thread','member'])) { event.preventDefault(); setDropHover(true); } }} onDragLeave={()=>setDropHover(false)} onDrop={event=> { const item=receiveDrop(event,['thread','member']); setDropHover(false); if (item?.kind==='member' && item.id!==state.me && state.members.some(m=>m.id===item.id)) setAction({kind:'share',target:item.id}); else if (item?.kind==='thread' && item.id===thread.id) setAction({kind:'share'}); }}><span>{sharedConversation?'团队可读':'仅自己可见'}</span><Button size="xs" variant="ghost" disabled={busy||actionMutation.busy} onClick={()=>void performAction('/context-sharing',{source_kind:'conversation',source_id:thread.id,enabled:!sharedConversation})}>{sharedConversation?'取消共享':'共享会话'}</Button><Button size="xs" variant="ghost" disabled={busy || !data?.messages.length} onClick={()=>setAction({kind:'share'})}><UserLinedIcon />交给同事</Button></div>}
    {thread && ((peerChat && human && !closed) || (flow?.kind==='decision' && flow.owner_id===state.me && flow.status==='live')) && <div className="flow-toolbar"><span>{flow?.kind==='decision'?'文字会议':'本人通道'}</span><Button data-tour={flow?.kind==='decision'?'meeting-finish':undefined} size="xs" variant="ghost" disabled={busy||!!active||actionMutation.busy} onClick={()=>void performAction(flow?.kind==='decision'?`/flows/${flow.id}/finish`:`/threads/${thread.id}/close`,{})}>{flow?.kind==='decision'?'结束会议':'结束本轮'}</Button></div>}
    {completion && <div className="flow-toolbar"><span>{completion.status==='needs_input'?'补充进展：':'整理待办：'}{completion.title}</span><Button variant="ghost" size="xs" disabled={busy||actionMutation.busy} onClick={()=>void performAction(`/task-summaries/${completion.id}/cancel`,{})}>取消整理</Button></div>}
    {(actionMutation.error||attachmentError) && <p role="alert" className="form-error">{actionMutation.error||attachmentError}</p>}
    {action && data && <InlineCollaboration key={action.kind+(action.target || '')} kind={action.kind} initialTarget={action.target} state={state} data={data} close={()=>setAction(null)} onRefresh={onRefresh} onOpen={onOpen} />}
    {isEmpty ? <div className="workspace-welcome"><div className="welcome-mark"><MessageSquareTextIcon size={25} /></div><h1>{thread?.kind==='peer' ? `与${peer?.person_name}的 Agent 协作` : '开始工作'}</h1>{composer}</div> : <>
      <div className="messages" data-tour="conversation-log" ref={scroll} role="log" aria-label="协作消息" aria-live="off" onScroll={()=> { const box=scroll.current; if (box) { pinned.current=box.scrollHeight-box.scrollTop-box.clientHeight<100; if (pinned.current) setUnread(false); } }}>{data.messages.map((message,index)=> {
        const messageThread=data.segments?.find(item=>item.id===message.conversation_id) || thread;
        const member=state.members.find(m=>m.id===message.from_unit);
        if (message.from_kind==='system') return <div key={message.id}><div className="system-message"><CheckIcon size={12} />{message.body}</div>{messageThread?.handoff_note && (message.body==='已请本人处理。' || message.body==='已安排在指定时间送达本人。') && <div className="handoff-note"><strong>转交摘要</strong>{messageThread.handoff_note}</div>}</div>;
        const generating=['queued','running'].includes(message.meta.status || '');
        const failed=['error','cancelled'].includes(message.meta.status || '');
        const segment=data.segments?.find(item=>item.id===message.conversation_id);
        const firstInSegment=index===0 || data.messages[index-1].conversation_id!==message.conversation_id;
        return <Fragment key={message.id}>{peerChat && segment && firstInSegment && <div className="chat-segment"><span>{segment.title==='新的协作' ? '新的事项' : segment.title}</span><small>{['agent','scheduled'].includes(segment.status) ? '仅你可见' : '双方可见'}</small>{segment.id!==thread.id ? <Button variant="ghost" size="xs" disabled={busy || !!active} onClick={()=>onOpen(segment.id)}>继续</Button> : <small>当前</small>}</div>}<article data-tour={message.from_kind==='agent'&&message.meta.status==='done'?'agent-result':undefined} className={`message message-${message.from_kind} ${message.from_kind==='human' && message.from_unit===state.me ? 'message-own' : ''}`} key={message.id}>
          <Avatar label={message.from_kind==='agent' ? 'Agent' : member?.person_name || '成员'} initial={message.from_kind==='agent' ? 'A' : member?.person_name[0]} size={24} />
          <div className="message-content"><div className="message-byline"><strong>{message.from_kind==='agent' ? thread?.kind==='workspace' ? 'Accord' : member?.person_name || 'Accord' : message.from_unit===state.me ? '你' : member?.person_name}</strong>{message.from_kind==='agent' && <span className="message-agent-label">Agent</span>}{message.meta.model && <span className="message-model">{message.meta.model}</span>}<time>{timeLabel(message.created_at)}</time></div>
            {!!message.body && (message.from_kind==='agent' ? <Markdown>{message.body}</Markdown> : <div className="message-body">{message.meta.agent_id && <span className="message-mention">@{state.members.find(member=>member.id===message.meta.agent_id)?.person_name} <small>Agent</small></span>}{message.body}</div>)}
            {!!data.attachments?.filter(item=>item.message_id===message.id).length&&<div className="message-attachments">{data.attachments.filter(item=>item.message_id===message.id).map(item=><div key={item.id} onContextMenu={event=>{event.preventDefault();setAttachmentMenu({x:event.clientX,y:event.clientY,item});}}><FileTextIcon size={14}/><button className="attachment-name" onClick={()=>void openAttachment(item)}>{item.filename}</button>{item.published_resource_id?<Button variant="ghost" size="xs" onClick={()=>onResource({id:item.published_resource_id,version:1,title:item.filename})}>已入工作池</Button>:item.owner_id===state.me&&readableAttachment(item)?<Button variant="secondary" size="xs" disabled={busy||actionMutation.busy} onClick={()=>void performAction(`/attachments/${item.id}/publish`,{})}>入工作池</Button>:null}</div>)}</div>}
            {generating && <div className="generation-status" role="status"><LoadingIcon size={13} />{message.meta.status==='queued' ? '等待生成' : message.meta.phase==='thinking' ? `正在思考${message.meta.reasoning_effort ? ` · ${reasoningLabels[message.meta.reasoning_effort]}` : ''}` : message.meta.phase==='reading' ? '正在查阅资料' : message.meta.phase==='connecting' ? '正在连接模型' : '正在生成'}</div>}
            {failed && <div className="generation-error" role="status"><span>{message.meta.error || '回答没有完成'}</span>{message.meta.completion_id && message.meta.status==='error' && <Button size="xs" variant="secondary" disabled={busy||!!active} onClick={()=>void performAction(`/task-summaries/${message.meta.completion_id}/retry`,{})}>重新整理</Button>}{thread?.status==='agent' && (!groupChat || message.meta.actor_id===state.me) && message.meta.run_id && <Button variant="secondary" size="xs" disabled={busy || !!active} onClick={()=>onRun(message.meta.run_id!,'retry')}>重新生成</Button>}</div>}
            {message.meta.finish_reason==='length' && <p className="subtle-message">回答已到本次长度上限，可以继续提问。</p>}
            {!!data.tool_calls.filter(call=>call.run_id===message.meta.run_id).length && <details className="tool-trace"><summary>已查阅 · {data.tool_calls.filter(call=>call.run_id===message.meta.run_id).length} 步</summary>{data.tool_calls.filter(call=>call.run_id===message.meta.run_id).map(call=><div key={call.id}><FileTextIcon size={12} /><span>{call.name==='person_context' ? '查阅个人上下文' : call.name==='colleague_status' ? '查看工作状态' : call.name==='context_read' ? '查阅资料' : call.name==='context_search' ? '检索资料' : '查看目录'}{call.resource_id && state.documents.find(d=>d.id===call.resource_id) ? ` · ${state.documents.find(d=>d.id===call.resource_id)?.title}` : ''}</span><small>{call.status==='done' ? '完成' : '未读取'}</small></div>)}</details>}
            {!!message.meta.context_sources?.length && <EvidenceSources sources={message.meta.context_sources} />}
            {!!message.sources.length && <div className="citations">{message.sources.map(id=> { const ref=message.meta.citations?.find(item=>item.id===id) || state.documents.find(d=>d.id===id); return ref && <Button key={id} variant="outline" size="xs" onClick={()=>onResource(ref)}><FileTextIcon />{ref.title || '引用资料'} · v{ref.version}</Button>; })}</div>}
            {!!message.body && !generating && <div className="message-actions">{canSubmit && thread && message.from_kind==='agent' && message.meta.status==='done' && <Button variant="ghost" size="xs" onClick={()=>onSubmission(thread.round_id,message.body)}>作为提交稿</Button>}<Button variant="ghost" size="xs" onClick={()=> { void copyText(message.body).then(()=>setCopied(message.id)).catch(()=>setCopied('error')); }}>{copied===message.id ? '已复制' : '复制'}</Button>{copied==='error' && <span>复制失败，请选择正文复制</span>}{message.meta.usage?.total_tokens !== undefined && <span>{message.meta.usage.total_tokens.toLocaleString()} tokens · {((message.meta.duration_ms || 0)/1000).toFixed(1)} 秒</span>}{message.meta.status==='cancelled' && <Badge size="sm" variant="ghost">已停止</Badge>}</div>}
          </div></article></Fragment>;
      })}{state.tasks.filter(task=>data.segments?.some(segment=>segment.id===task.thread_id) || task.thread_id===thread?.id).map(task=><ConversationTask key={task.id} task={task} state={state} busy={busy || actionMutation.busy} onAction={performAction} />)}{actionMutation.error && <p role="alert" className="form-error">{actionMutation.error}</p>}</div>
      {unread && <div className="jump-latest"><Button size="sm" variant="secondary" onClick={bottom}>最新消息 ↓</Button></div>}
      {closed && flow && <ChatSummary key={flow.id} id={flow.id} state={state} onRefresh={onRefresh}/>}
      {composer}
    </>}
    {attachmentMenu&&<div className="context-quick-menu" role="menu" style={{left:Math.min(attachmentMenu.x,window.innerWidth-180),top:Math.min(attachmentMenu.y,window.innerHeight-150)}} onPointerDown={event=>event.stopPropagation()}><button role="menuitem" onClick={()=>{void openAttachment(attachmentMenu.item);setAttachmentMenu(null);}}>打开</button><button role="menuitem" onClick={()=>{void openAttachment(attachmentMenu.item,true);setAttachmentMenu(null);}}>下载</button>{attachmentMenu.item.owner_id===state.me&&readableAttachment(attachmentMenu.item)&&!attachmentMenu.item.published_resource_id&&<button role="menuitem" disabled={busy||actionMutation.busy} onClick={()=>{void performAction(`/attachments/${attachmentMenu.item.id}/publish`,{});setAttachmentMenu(null);}}>入工作池</button>}</div>}
  </div>;
}
