import { useState, type ComponentProps } from 'react';
import { Avatar, Button, Input } from '@tutti-os/ui-system';
import { CheckIcon, CloseIcon, UserLinedIcon } from '@tutti-os/ui-system/icons';
import { timeLabel, type Message, type State, type Thread } from '../../shared/api';
import { Composer } from './Composer';
import './conversation-actions.css';

export type ConversationAction = (path: string, body: Record<string, unknown>) => Promise<boolean>;

/** Keep handoff and acceptance beside the existing input, within the same conversation. */
export function ConversationInput({ thread, messages, state, onAction, composer }: {
  thread?: Thread; messages: Message[]; state: State; onAction: ConversationAction;
  composer: ComponentProps<typeof Composer>;
}) {
  const [action, setAction] = useState<'handoff' | 'confirm' | null>(null);
  const [timed, setTimed] = useState(false);
  const [deadline, setDeadline] = useState('');
  const [title, setTitle] = useState(thread?.title || '');
  const [error, setError] = useState('');
  const peer = state.members.find(member => member.id === thread?.target_id);
  const recipient = state.members.find(member => member.id === (thread?.target_id === state.me ? thread.owner_id : thread?.target_id));
  const canHandoff = thread?.kind === 'peer' && thread.owner_id === state.me && thread.status === 'agent' && thread.purpose === 'ordinary';
  const canConfirm = thread?.kind === 'peer' && thread.target_id === state.me && ['waiting', 'human'].includes(thread.status);
  // A phase may change in another tab; never submit a stale inline action.
  const current = action === 'handoff' && canHandoff ? action : action === 'confirm' && canConfirm ? action : null;
  const scheduled = thread?.status === 'scheduled';
  const human = !!thread && ['waiting', 'human', 'resolved'].includes(thread.status);
  const messageDraft = human || scheduled ? `${composer.draftId}.human` : composer.draftId;
  const start = (next: 'handoff' | 'confirm') => { setError(''); setAction(next); };
  const send = async (body: string, sources: string[]) => {
    setError('');
    if (!current || !thread) return composer.onSend(body, sources);
    let values: Record<string, unknown>;
    if (current === 'handoff') {
      const date = timed && deadline ? new Date(deadline) : null;
      if (timed && (!date || !Number.isFinite(date.getTime()) || date.getTime() <= Date.now())) {
        setError('请选择未来的送达时间。'); return false;
      }
      values = { mode: timed ? 'deadline' : 'now', deadline: date?.toISOString() || '', note: body };
    } else {
      values = { conclusion: body, task_title: title.trim(), assignee_id: state.me };
    }
    if (!await onAction(`/threads/${thread.id}/${current}`, values)) {
      setError('尚未发送，输入已保留，请重试。'); return false;
    }
    setAction(null); return true;
  };
  const lastOwnReply = [...messages].reverse().find(message => message.from_kind === 'human' && message.from_unit === state.me)?.body || '';
  const audience = current === 'handoff' ? `发给 ${peer?.person_name} 本人`
    : current === 'confirm' ? '确认并由我负责'
    : scheduled ? '等待送达本人'
    : human ? `发给 ${recipient?.person_name}`
    : thread?.kind === 'peer' ? `${peer?.person_name}的 Agent · 仅你可见` : composer.workspace;
  return <div className="conversation-input" onKeyDown={event => { if (event.key === 'Escape' && current && !composer.busy) { setAction(null); setError(''); } }}>
    {!current && (canHandoff || canConfirm) && <div className="conversation-next-action">
      {canHandoff ? <Button variant="ghost" size="sm" disabled={composer.busy || composer.running || !messages.length} onClick={() => start('handoff')}><UserLinedIcon />请 {peer?.person_name} 本人接入</Button>
        : <Button variant="ghost" size="sm" disabled={composer.busy} onClick={() => start('confirm')}><CheckIcon />确认下一步并由我负责</Button>}
    </div>}
    <Composer {...composer} key={current ? `${composer.draftId}.${current}` : messageDraft} draftId={current ? `${composer.draftId}.${current}` : messageDraft}
      human={!!current || human || scheduled} onSend={send} initialValue={current === 'confirm' ? lastOwnReply : ''}
      allowEmpty={current === 'handoff'} sendDisabled={scheduled || (current === 'confirm' && !title.trim())}
      sendLabel={current === 'handoff' ? '发送给本人' : current === 'confirm' ? '确认并承担' : undefined}
      inputLabel={current === 'handoff' ? '转交补充说明' : current === 'confirm' ? '确认的结论与下一步' : undefined}
      placeholder={current === 'handoff' ? '补充一句需要本人处理的事（可选）…' : current === 'confirm' ? '写下你确认的结论与下一步…' : scheduled ? '可以先写下补充内容，送达后继续发送…' : undefined}
      maxLength={current === 'handoff' ? 1000 : current === 'confirm' ? 4000 : 8000} audience={audience}
      contextLabel={current === 'handoff' ? `包含本段对话 · ${messages.length} 条消息` : current === 'confirm' ? `${recipient?.person_name}可见 · 加入我的待办` : scheduled ? `${timeLabel(thread!.delivery_at)}（北京时间）送达` : undefined}
      accessory={current && <div className="conversation-action-fields">
        <div className="conversation-action-heading"><Avatar label={current === 'handoff' ? peer?.person_name || '本人' : '我'} initial={current === 'handoff' ? peer?.person_name[0] : state.members.find(member => member.id === state.me)?.person_name[0]} size={20} /><strong>{current === 'handoff' ? `请 ${peer?.person_name} 接着处理` : '这件事由我负责'}</strong><Button variant="ghost" size="icon-xs" aria-label="取消当前操作" disabled={composer.busy} onClick={() => { setAction(null); setError(''); }}><CloseIcon /></Button></div>
        {current === 'confirm' ? <Input aria-label="任务名称" value={title} maxLength={160} disabled={composer.busy} onChange={event => setTitle(event.target.value)} />
          : <div className="conversation-delivery"><Button size="xs" variant={timed ? 'ghost' : 'secondary'} disabled={composer.busy} aria-pressed={!timed} onClick={() => { setTimed(false); setError(''); }}>现在发送</Button><Button size="xs" variant={timed ? 'secondary' : 'ghost'} disabled={composer.busy} aria-pressed={timed} onClick={() => { setTimed(true); setError(''); }}>定时发送</Button>{timed && <Input aria-label="送达时间（本机时区）" type="datetime-local" value={deadline} disabled={composer.busy} onChange={event => { setDeadline(event.target.value); setError(''); }} />}</div>}
      </div>}
      error={error}
    />
  </div>;
}

export function ConversationTask({ task, state, busy, onAction }: {
  task: State['tasks'][number]; state: State; busy: boolean; onAction: ConversationAction;
}) {
  const owner = state.members.find(member => member.id === task.assignee_id);
  const done = task.status === 'done';
  return <div className="conversation-task">
    <CheckIcon size={17} /><div><strong>{task.title}</strong><span>{owner?.person_name}负责 · {done ? '已完成' : '进行中'}</span></div>
    {task.assignee_id === state.me && <Button variant="secondary" size="sm" disabled={busy} onClick={() => void onAction(`/tasks/${task.id}/status`, { status: done ? 'open' : 'done' })}>{done ? '重新打开' : '标记完成'}</Button>}
  </div>;
}
