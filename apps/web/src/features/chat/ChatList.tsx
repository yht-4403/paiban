import { Avatar, Button } from '@tutti-os/ui-system';
import { MessageSquareTextIcon } from '@tutti-os/ui-system/icons';
import type { State, Thread } from '../../shared/api';
import { timeLabel } from '../../shared/api';
import { Empty } from '../../shared/ui';

export function ChatList({state,selected,query,busy,onMember,onGroup}: {state:State;selected:Thread|undefined;query:string;busy:boolean;onMember:(id:string)=>void;onGroup:(id:string)=>void}) {
  const peer=selected?.kind==='group' ? undefined : selected?.owner_id===state.me ? selected.target_id : selected?.owner_id;
  return <div className="chat-contact-list" aria-label="同事聊天">{(state.groups || []).filter(group=>group.title.includes(query.trim())).map(group=><Button key={group.id} variant="ghost" className={`chat-contact ${selected?.id===group.id ? 'selected' : ''}`} aria-current={selected?.id===group.id ? 'page' : undefined} disabled={busy} onClick={()=>onGroup(group.id)}><Avatar size={32} label={group.title} initial="#" /><span><strong>{group.title}</strong><small>{group.preview || '暂无消息'}</small></span><time>{timeLabel(group.updated_at)}</time></Button>)}{state.members.filter(member=>member.id!==state.me && member.person_name.includes(query.trim())).map(member=> {
    const latest=state.threads.filter(thread=>thread.kind==='peer' && ((thread.owner_id===state.me && thread.target_id===member.id) || (thread.owner_id===member.id && thread.target_id===state.me))).sort((a,b)=>b.updated_at.localeCompare(a.updated_at))[0];
    const waiting=state.threads.some(thread=>thread.owner_id===member.id && thread.target_id===state.me && thread.status==='waiting');
    return <Button key={member.id} variant="ghost" className={`chat-contact ${peer===member.id ? 'selected' : ''}`} aria-current={peer===member.id ? 'page' : undefined} disabled={busy} onClick={()=>onMember(member.id)}><Avatar size={32} label={member.person_name} initial={member.person_name[0]} /><span><strong>{member.person_name}</strong><small>{latest?.preview || member.activity?.label || (member.window==='closed' ? '专注中' : '可协作')}</small></span>{latest && <time>{timeLabel(latest.updated_at)}</time>}{waiting && <span className="notification-dot" />}</Button>;
  })}</div>;
}

export function ChatLobby({state,onMember,onInvite}: {state:State;onMember:(id:string)=>void;onInvite:()=>void}) {
  return <div className="chat-lobby"><Empty icon={<MessageSquareTextIcon size={26} />} title="选择同事">{state.members.length>1 ? null : <Button variant="secondary" onClick={onInvite}>邀请同事</Button>}</Empty><div className="chat-lobby-contacts">{state.members.filter(member=>member.id!==state.me).map(member=><Button variant="secondary" key={member.id} onClick={()=>onMember(member.id)}><Avatar label={member.person_name} initial={member.person_name[0]} size={24} />{member.person_name}</Button>)}</div></div>;
}
