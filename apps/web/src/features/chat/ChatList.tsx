import { Avatar, Button } from '@tutti-os/ui-system';
import { MessageSquareTextIcon } from '@tutti-os/ui-system/icons';
import type { State, Thread } from '../../shared/api';
import { Empty } from '../../shared/ui';

export function ChatList({state,selected,query,busy,onMember}: {state:State;selected:Thread|undefined;query:string;busy:boolean;onMember:(id:string)=>void}) {
  const peer=selected?.owner_id===state.me ? selected.target_id : selected?.owner_id;
  return <div className="chat-contact-list" aria-label="同事聊天">{state.members.filter(member=>member.id!==state.me && member.person_name.includes(query.trim())).map(member=> {
    const waiting=state.threads.some(thread=>thread.owner_id===member.id && thread.target_id===state.me && thread.status==='waiting');
    return <Button key={member.id} variant="ghost" className={`chat-contact ${peer===member.id ? 'selected' : ''}`} disabled={busy} onClick={()=>onMember(member.id)}><Avatar size={32} label={member.person_name} initial={member.person_name[0]} /><span><strong>{member.person_name}</strong><small>{member.activity?.label || (member.window==='closed' ? '专注中' : '可协作')}</small></span>{waiting && <span className="notification-dot" />}</Button>;
  })}</div>;
}

export function ChatLobby({state,onMember,onInvite}: {state:State;onMember:(id:string)=>void;onInvite:()=>void}) {
  return <div className="chat-lobby"><Empty icon={<MessageSquareTextIcon size={26} />} title="与同事聊一聊">{state.members.length>1 ? 'Agent 先接住，需要时请本人接着处理。' : <Button variant="secondary" onClick={onInvite}>邀请同事</Button>}</Empty><div className="chat-lobby-contacts">{state.members.filter(member=>member.id!==state.me).map(member=><Button variant="secondary" key={member.id} onClick={()=>onMember(member.id)}><Avatar label={member.person_name} initial={member.person_name[0]} size={24} />{member.person_name}</Button>)}</div></div>;
}
