import { scopeLabels } from './Materials';
import { LocalizedDialogContent } from '../../shared/ui';
import { useEffect, useState } from 'react';
import { Avatar, Badge, Button, Checkbox, Dialog, DialogDescription, DialogFooter, DialogHeader, DialogTitle, Input, Textarea } from '@tutti-os/ui-system';
import { CheckIcon, FileTextIcon, LoadingIcon } from '@tutti-os/ui-system/icons';
import { reasoningLabels, type Document, type State, type Thread } from '../../shared/api';
import { Markdown } from '../../shared/Markdown';

export type Modal = { kind: 'handoff'; thread: Thread } | { kind: 'confirm'; thread: Thread } | { kind: 'document'; document: Document } | { kind: 'publish' } | { kind: 'settings' };

export function Dialogs({ modal, close, state, busy, submit, theme, setTheme, logout }: { modal: Modal | null; close: () => void; state: State; busy: boolean;
  submit: (path: string, body: Record<string, unknown>) => Promise<boolean>; theme: string; setTheme: (t: string) => void; logout: () => void;
}) {
  const [displayed, setDisplayed] = useState(modal);
  useEffect(() => { if (modal) setDisplayed(modal); }, [modal]);
  const content = modal || displayed;
  return <Dialog open={!!modal} onOpenChange={open => { if (!open && !busy) close(); }}><LocalizedDialogContent className={modal?.kind === 'document' ? 'document-dialog' : 'action-dialog'}>
    {content && <DialogBody key={content.kind} modal={content} close={close} state={state} busy={busy} submit={submit} theme={theme} setTheme={setTheme} logout={logout} />}
  </LocalizedDialogContent></Dialog>;
}

function DialogBody({ modal, close, state, busy, submit, theme, setTheme, logout }: Parameters<typeof Dialogs>[0] & { modal: Modal }) {
  const [body, setBody] = useState('');
  const [title, setTitle] = useState(modal.kind === 'confirm' ? modal.thread.title : '');
  const [mode, setMode] = useState('now');
  const [deadline, setDeadline] = useState('');
  const [error, setError] = useState('');
  const save = async () => {
    let path = ''; let values: Record<string, unknown> = {};
    if (modal.kind === 'handoff') {
      const date = deadline ? new Date(deadline) : null;
      if (mode === 'deadline' && (!date || !Number.isFinite(date.getTime()) || date.getTime() <= Date.now())) { setError('请选择未来的送达时间。'); return; }
      path = `/threads/${modal.thread.id}/handoff`; values = { mode, note: body, deadline: date?.toISOString() || '' };
    } else if (modal.kind === 'confirm') {
      path = `/threads/${modal.thread.id}/confirm`; values = { conclusion: body, task_title: title, assignee_id: state.me };
    } else if (modal.kind === 'publish') { path = '/documents'; values = { title, body }; }
    if (await submit(path, values)) close();
    else setError('没有完成操作，请查看工作台提示并重试。输入已保留。');
  };
  if (modal.kind === 'document') return <><DialogHeader><div className="document-dialog-icon"><FileTextIcon size={22} /></div><DialogTitle>{modal.document.title}</DialogTitle><DialogDescription>{scopeLabels[modal.document.scope] || '团队共享'} · v{modal.document.version || 1}</DialogDescription></DialogHeader><div className="document-body"><Markdown>{modal.document.body}</Markdown></div><DialogFooter><Button variant="secondary" onClick={close}>关闭</Button></DialogFooter></>;
  if (modal.kind === 'settings') return <Settings state={state} theme={theme} setTheme={setTheme} busy={busy} submit={submit} logout={logout} />;
  const labels = modal.kind === 'handoff' ? ['找本人处理', '提交后，对方可以看到这条协作的全部记录与引用资料。'] : modal.kind === 'confirm' ? ['确认结论并承担任务', '确认后，这条协作生成一条由你负责的任务，发起人也能看到。'] : ['发布到共享成果', '发布后，工作空间内所有成员及其 Agent 都可以读取这份资料。'];
  return <><DialogHeader><DialogTitle>{labels[0]}</DialogTitle><DialogDescription>{labels[1]}</DialogDescription></DialogHeader>
    {modal.kind === 'handoff' ? <><div className="theme-options"><Button variant={mode === 'now' ? 'default' : 'secondary'} aria-pressed={mode === 'now'} onClick={() => setMode('now')}>现在送达</Button><Button variant={mode === 'deadline' ? 'default' : 'secondary'} aria-pressed={mode === 'deadline'} onClick={() => setMode('deadline')}>指定时间</Button></div>{mode === 'deadline' && <div className="form-field"><label htmlFor="delivery">送达时间（本机时区）</label><Input id="delivery" type="datetime-local" value={deadline} onChange={e => setDeadline(e.target.value)} /></div>}</> : <div className="form-field"><label htmlFor="title">{modal.kind === 'confirm' ? '任务名称' : '资料标题'}</label><Input id="title" value={title} onChange={e => setTitle(e.target.value)} maxLength={160} /></div>}
    <div className="form-field"><label htmlFor="body">{modal.kind === 'handoff' ? '补充说明（可选）' : modal.kind === 'confirm' ? '你的结论' : '资料正文'}</label><Textarea id="body" value={body} onChange={e => setBody(e.target.value)} placeholder={modal.kind === 'confirm' ? '明确你确认的内容和下一步…' : '补充让对方能够直接理解的信息…'} maxLength={modal.kind === 'publish' ? 16000 : modal.kind === 'confirm' ? 4000 : 1000} /></div>
    {error && <p className="form-error" role="alert">{error}</p>}
    <DialogFooter><Button variant="ghost" onClick={close} disabled={busy}>取消</Button><Button disabled={busy || (modal.kind !== 'handoff' && (!body.trim() || !title.trim()))} aria-busy={busy} onClick={() => void save()}>{busy && <LoadingIcon />}{modal.kind === 'handoff' ? '确认找本人' : modal.kind === 'confirm' ? '确认并生成任务' : '确认发布'}</Button></DialogFooter>
  </>;
}


function Settings({ state, theme, setTheme, busy, submit, logout }: Omit<Parameters<typeof Dialogs>[0], 'modal' | 'close'>) {
  const me = state.members.find(member => member.id === state.me)!;
  const [error, setError] = useState('');
  return <><DialogHeader><DialogTitle>设置</DialogTitle><DialogDescription>{state.project.name}</DialogDescription></DialogHeader>
    <div className="settings-account"><Avatar label={me.person_name} initial={me.person_name[0]} size={32} /><div><strong>{me.person_name}</strong><span>{me.agent_name}</span></div></div>
    <div className="form-field"><label>外观</label><div className="theme-options">{[['dark','暗色'],['light','亮色']].map(([value,label])=><Button key={value} variant={theme===value ? 'default' : 'secondary'} aria-pressed={theme===value} onClick={()=>setTheme(value)}>{label}</Button>)}</div></div>
    <div className="form-field"><label>你的协作状态</label><div className="theme-options">{[['open','可协作'],['closed','专注中']].map(([window,label])=><Button key={window} variant={me.window===window ? 'default' : 'secondary'} aria-pressed={me.window===window} disabled={busy} onClick={()=>void submit('/profile/availability',{window})}>{label}</Button>)}</div><p>状态会展示给成员；目前不会自动拦截找本人请求。</p></div>
    <div className="activity-sharing"><strong>同事可以看到</strong><label><Checkbox checked={state.activity_preferences.automatic} disabled={busy} onCheckedChange={checked=>void submit('/profile/activity',{...state.activity_preferences,automatic:!!checked,work_title:!!checked && state.activity_preferences.work_title,expected_version:state.activity_preferences.version})} /><span>我在拍办聊天或工作的状态</span></label><label><Checkbox checked={state.activity_preferences.work_title} disabled={busy || !state.activity_preferences.automatic} onCheckedChange={checked=>void submit('/profile/activity',{...state.activity_preferences,work_title:!!checked,expected_version:state.activity_preferences.version})} /><span>我正在处理的事项标题</span></label><small>聊天正文仍按每段对话的可见范围共享。</small></div>
    <div className="settings-model"><Badge variant="secondary">{state.model.label}</Badge><p>今日已发起 {state.model.requests_today} / {state.model.daily_limit} 次生成，模型已回报 {state.model.reported_tokens_today.toLocaleString()} tokens。中断时未回传的用量不计入这里。</p></div>
    {!!state.model.reasoning_options?.length && <div className="form-field"><label id="reasoning-label">你的思考强度</label><div className="theme-options" role="group" aria-labelledby="reasoning-label">{state.model.reasoning_options.map(effort => <Button key={effort} variant={state.model.reasoning_effort===effort ? 'default' : 'secondary'} aria-pressed={state.model.reasoning_effort===effort} disabled={busy} onClick={async () => { setError(''); if (!await submit('/profile/reasoning', { reasoning_effort: effort })) setError('思考强度未能保存，请重试。'); }}>{reasoningLabels[effort]}{effort==='max' ? '（默认）' : ''}</Button>)}</div><p>最高档适合复杂问题，等待时间和用量通常更多。仅影响你接下来发起或重试的回答，已在生成的回答保持原设置。</p></div>}
    {error && <p className="form-error" role="alert">{error}</p>}
    <DialogFooter><Button variant="secondary" disabled={busy} onClick={logout}>切换身份</Button></DialogFooter>
  </>;
}
