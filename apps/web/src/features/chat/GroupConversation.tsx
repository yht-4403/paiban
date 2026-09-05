import { useState } from 'react';
import { Avatar, Button, Input, Popover, PopoverContent, PopoverTrigger } from '@tutti-os/ui-system';
import { CloseIcon, CheckIcon } from '@tutti-os/ui-system/icons';
import type { ProcessAttachmentInput, State, Thread, ThreadData } from '../../shared/api';
import { Composer } from '../workspace/Composer';
import { GroupPicker } from './GroupPicker';

export function GroupComposer({state,data,busy,onSend,onRun,humanOnly=false}: {
  state:State;data:ThreadData;busy:boolean;humanOnly?:boolean;onSend:(body:string,agentId:string,attachments?:ProcessAttachmentInput[])=>Promise<boolean>;onRun:(id:string,action:'stop'|'retry')=>void;
}) {
  const [agent,setAgent]=useState(''),[open,setOpen]=useState(false);
  const members=state.members.filter(member=>data.thread.member_ids?.includes(member.id));
  const target=members.find(member=>member.id===agent);
  const active=data.messages.find(message=>['queued','running'].includes(message.meta.status || ''));
  return <Composer draftId={`accord.draft.${state.me}.${data.thread.id}.group`} documents={[]} onResource={()=>{}} human busy={busy} allowAttachments
    model={state.model.label} workspace={state.project.name} audience="群成员可见" onSend={async (body,_,attachments)=>{const ok=await onSend(body,humanOnly?'':target?.id || '',attachments);if(ok)setAgent('');return ok;}}
    running={!!agent && !!active && active.meta.actor_id===state.me} onStop={()=>active?.meta.run_id && onRun(active.meta.run_id,'stop')} sendDisabled={!!agent && !!active}
    inputLabel={humanOnly?'会议发言':'群聊消息'} placeholder={humanOnly?'发送给参会人…':'发消息，或 @ Agent'} onMention={humanOnly?undefined:()=>setOpen(true)}
    accessory={!humanOnly&&<div className="group-mentions">{active?.meta.actor_id===state.me && !agent && <Button variant="ghost" size="xs" onClick={()=>active.meta.run_id&&onRun(active.meta.run_id,'stop')}>停止回答</Button>}<Popover open={open} onOpenChange={setOpen}><PopoverTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="提及 Agent" title="提及 Agent">@</Button></PopoverTrigger><PopoverContent align="start" className="group-agent-picker"><strong>选择 Agent</strong>{members.map(member=><Button variant="ghost" key={member.id} onClick={()=>{setAgent(member.id);setOpen(false);}}><Avatar label={member.person_name} initial={member.person_name[0]} size={20} /><span>{member.person_name}</span><small>Agent</small></Button>)}</PopoverContent></Popover>{target && <span className="group-mention-tag">@{target.person_name} <small>Agent</small><Button variant="ghost" size="icon-xs" aria-label="取消提及" onClick={()=>setAgent('')}><CloseIcon /></Button></span>}</div>}
  />;
}

export function GroupMembers({state,thread,busy,onAction}: {state:State;thread:Thread;busy:boolean;onAction:(path:string,body:Record<string,unknown>)=>Promise<boolean>}) {
  const owner=thread.owner_id===state.me;
  const members=state.members.filter(member=>thread.member_ids?.includes(member.id));
  const [editing,setEditing]=useState(false),[title,setTitle]=useState(thread.title);
  return <aside className="context-panel group-members" aria-label="群成员"><div className="context-title"><strong>成员 · {members.length}</strong>{owner && !state.flows?.some(flow=>flow.thread_id===thread.id) && <GroupPicker adding limit={8-members.length} members={state.members.filter(member=>!thread.member_ids?.includes(member.id))} onChoose={ids=>onAction(`/groups/${thread.id}/members`,{member_ids:ids})} />}</div>
    {members.map(member=><div className="group-member" key={member.id}><Avatar label={member.person_name} initial={member.person_name[0]} size={28} /><span className="group-member-name">{member.person_name}<small>{member.id===state.me ? '你' : member.activity?.label || ''}</small></span>{thread.owner_id===member.id && <small>群主</small>}</div>)}
    <div className="group-settings"><span>群名</span>{editing ? <form onSubmit={event=>{event.preventDefault();void onAction(`/groups/${thread.id}/rename`,{title}).then(ok=>ok && setEditing(false));}}><Input value={title} maxLength={80} aria-label="群名" onChange={event=>setTitle(event.target.value)} autoFocus /><Button type="submit" size="icon-sm" variant="ghost" aria-label="保存群名" disabled={busy || !title.trim()}><CheckIcon /></Button><Button type="button" size="icon-sm" variant="ghost" aria-label="取消修改群名" onClick={()=>setEditing(false)}><CloseIcon /></Button></form> : <button disabled={!owner} onClick={()=>{setTitle(thread.title);setEditing(true);}}>{thread.title}</button>}</div>
  </aside>;
}
