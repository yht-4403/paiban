import { useEffect, useRef } from 'react';
import { Avatar, Badge, Button } from '@tutti-os/ui-system';
import { CheckIcon, FileTextIcon, MessageSquareTextIcon, UserLinedIcon } from '@tutti-os/ui-system/icons';
import { statusLabels, timeLabel, type State, type ThreadData, type Document } from '../../shared/api';
import { Pending } from '../../shared/ui';
import { Composer } from './Composer';

export function Conversation({ state, data, loading, busy, onSend, onHandoff, onConfirm, onDocument, onNew, prompt }: {
  state: State; data: ThreadData | null; loading: boolean; busy: boolean; onSend: (body: string, sourceIds: string[]) => Promise<boolean>;
  onHandoff: () => void; onConfirm: () => void; onDocument: (doc: Document) => void; onNew: () => void; prompt: string;
}) {
  const tail = useRef<HTMLDivElement>(null);
  useEffect(() => { tail.current?.scrollIntoView({ block: 'nearest' }); }, [data?.messages.length]);
  if (loading) return <Pending label="正在打开协作" />;
  const thread = data?.thread;
  const peer = state.members.find(m => m.id === thread?.target_id);
  const human = thread && ['waiting', 'human'].includes(thread.status);
  const displayMember = thread?.target_id === state.me && (human || thread.status === 'resolved') ? state.members.find(m => m.id === thread.owner_id) : peer;
  const isEmpty = !data?.messages.length;
  return <div className={`conversation ${isEmpty ? 'conversation-empty' : ''}`}>
    {thread && <div className="conversation-heading"><div><Avatar label={displayMember?.person_name || '我的 Agent'} initial={displayMember?.person_name[0]} size={28} /><div><strong>{thread.kind === 'workspace' ? '我的 Agent' : human || thread.status === 'resolved' ? displayMember?.person_name : peer?.agent_name}</strong><span>{thread.kind === 'workspace' ? '这段工作记录仅你可见' : statusLabels[thread.status]}</span></div></div>
      {thread.kind === 'peer' && thread.owner_id === state.me && thread.status === 'agent' && <Button variant="secondary" onClick={onHandoff} disabled={!data.messages.length || busy}><UserLinedIcon />找本人</Button>}
      {thread.target_id === state.me && human && <Button onClick={onConfirm} disabled={busy}><CheckIcon />确认并生成任务</Button>}
    </div>}
    {!!thread?.handoff_note && <div className="handoff-note"><strong>转交说明</strong>{thread.handoff_note}</div>}
    {isEmpty ? <div className="workspace-welcome"><div className="welcome-mark"><MessageSquareTextIcon size={26} /></div><p className="eyeline">一起把事情往前推</p><h1>{thread?.kind === 'peer' ? `先问问${peer?.person_name}的 Agent` : '今天，有什么需要一起推进？'}</h1><p className="welcome-description">查一份资料，问一位同事，或把一个想法变成行动。</p>
      <Composer modelMode={state.model.mode} key={prompt} initial={prompt} documents={state.documents} onSend={onSend} busy={busy} />
      <div className="welcome-shortcuts">{['梳理当前演示范围', '查找工作台 UI 资料', '整理联调检查清单'].map(text => <Button key={text} variant="outline" size="sm" disabled={busy} onClick={() => void onSend(text, [])}>{text}<ArrowSmall /></Button>)}</div>
    </div> : <><div className="messages" role="log" aria-label="协作消息">{data.messages.map(message => {
      const member = state.members.find(m => m.id === message.from_unit);
      if (message.from_kind === 'system') return <div className="system-message" key={message.id}><CheckIcon size={12} />{message.body}</div>;
      return <article className={`message message-${message.from_kind}`} key={message.id}>
        <Avatar label={message.from_kind === 'agent' ? `${member?.person_name}的 Agent` : member?.person_name || '成员'} initial={message.from_kind === 'agent' ? 'A' : member?.person_name[0]} size={27} />
        <div className="message-content"><div className="message-byline"><strong>{message.from_kind === 'agent' ? `${member?.person_name}的 Agent` : message.from_unit === state.me ? '你' : member?.person_name}</strong>{message.from_kind === 'agent' && <Badge variant={message.meta.mode === 'error' ? 'destructive' : 'secondary'} size="sm">{message.meta.mode === 'model' ? '模型回答' : message.meta.mode === 'error' ? '调用失败' : '资料检索'}</Badge>}<time>{timeLabel(message.created_at)}</time></div>
          <div className="message-body">{message.body}</div>
          {!!message.sources.length && <div className="citations">{message.sources.map(id => { const doc = state.documents.find(d => d.id === id); return doc && <Button key={id} variant="outline" size="xs" onClick={() => onDocument(doc)}><FileTextIcon />{doc.title}</Button>; })}</div>}
        </div></article>;
    })}<div ref={tail} /></div>
      {thread?.status === 'resolved' ? <div className="resolved-bar"><CheckIcon size={15} /><span>这条协作已确认，任务已进入双方待办。</span><Button variant="secondary" size="sm" onClick={onNew}>新建协作</Button></div> : thread?.status === 'scheduled' ? <div className="resolved-bar"><span>将于 {timeLabel(thread.delivery_at)}（北京时间）送达本人。</span></div> : <Composer modelMode={state.model.mode} documents={state.documents} onSend={onSend} busy={busy} human={!!human} />}
    </>}
  </div>;
}

function ArrowSmall() { return <span aria-hidden="true">↗</span>; }
