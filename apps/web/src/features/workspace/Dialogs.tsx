import { LocalizedDialogContent } from '../../shared/ui';
import { useState } from 'react';
import { Avatar, Badge, Button, Dialog, DialogDescription, DialogFooter, DialogHeader, DialogTitle, Input, Textarea } from '@tutti-os/ui-system';
import { CheckIcon, FileTextIcon, LoadingIcon } from '@tutti-os/ui-system/icons';
import type { Document, State, Thread } from '../../shared/api';

export type Modal = { kind: 'handoff'; thread: Thread } | { kind: 'confirm'; thread: Thread } | { kind: 'document'; document: Document } | { kind: 'publish' } | { kind: 'settings' };

export function Dialogs({ modal, close, state, busy, submit, theme, setTheme, login }: { modal: Modal | null; close: () => void; state: State; busy: boolean;
  submit: (path: string, body: Record<string, unknown>) => Promise<boolean>; theme: string; setTheme: (t: string) => void; login: (id: string) => void;
}) {
  return <Dialog open={!!modal} onOpenChange={open => { if (!open && !busy) close(); }}><LocalizedDialogContent className={modal?.kind === 'document' ? 'document-dialog' : 'action-dialog'}>
    {modal && <DialogBody key={modal.kind} modal={modal} close={close} state={state} busy={busy} submit={submit} theme={theme} setTheme={setTheme} login={login} />}
  </LocalizedDialogContent></Dialog>;
}

function DialogBody({ modal, close, state, busy, submit, theme, setTheme, login }: Parameters<typeof Dialogs>[0] & { modal: Modal }) {
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
  if (modal.kind === 'document') return <><DialogHeader><div className="document-dialog-icon"><FileTextIcon size={22} /></div><DialogTitle>{modal.document.title}</DialogTitle><DialogDescription>团队共享资料 · Agent 可引用</DialogDescription></DialogHeader><div className="document-body">{modal.document.body}</div><DialogFooter><Button variant="secondary" onClick={close}>关闭</Button></DialogFooter></>;
  if (modal.kind === 'settings') return <><DialogHeader><DialogTitle>工作空间设置</DialogTitle><DialogDescription>当前为本地演示，成员、资料与初始请求均为合成数据。</DialogDescription></DialogHeader><div className="form-field"><label>外观</label><div className="theme-options">{[['dark','暗色'],['light','亮色']].map(([value,label]) => <Button key={value} variant={theme === value ? 'default' : 'secondary'} aria-pressed={theme === value} onClick={() => setTheme(value)}>{label}</Button>)}</div></div><div className="form-field"><label>切换演示成员</label><p>每个浏览器标签页可保留不同成员，用于核对双方视角。</p>{state.members.map(m => <Button key={m.id} variant="ghost" className="member-option" disabled={busy} onClick={() => login(m.id)}><Avatar label={m.person_name} initial={m.person_name[0]} size={26} /><span>{m.person_name}<small>{m.tags[0]}</small></span>{state.me === m.id && <CheckIcon />}</Button>)}</div><div className="settings-model"><Badge variant="secondary">{state.model.mode === 'model' ? '模型已配置' : '资料检索演示'}</Badge><p>未接模型时只返回已共享资料摘录。演示身份切换不用于生产账号认证。</p></div></>;
  const labels = modal.kind === 'handoff' ? ['找本人处理', '提交后，对方可以看到这条协作的全部记录与引用资料。'] : modal.kind === 'confirm' ? ['确认结论并承担任务', '确认后，这条协作生成一条由你负责的任务，发起人也能看到。'] : ['发布到共享成果', '发布后，所有演示成员及其 Agent 都可以读取这份资料。'];
  return <><DialogHeader><DialogTitle>{labels[0]}</DialogTitle><DialogDescription>{labels[1]}</DialogDescription></DialogHeader>
    {modal.kind === 'handoff' ? <><div className="theme-options"><Button variant={mode === 'now' ? 'default' : 'secondary'} aria-pressed={mode === 'now'} onClick={() => setMode('now')}>现在送达</Button><Button variant={mode === 'deadline' ? 'default' : 'secondary'} aria-pressed={mode === 'deadline'} onClick={() => setMode('deadline')}>指定时间</Button></div>{mode === 'deadline' && <div className="form-field"><label htmlFor="delivery">送达时间（本机时区）</label><Input id="delivery" type="datetime-local" value={deadline} onChange={e => setDeadline(e.target.value)} /></div>}</> : <div className="form-field"><label htmlFor="title">{modal.kind === 'confirm' ? '任务名称' : '资料标题'}</label><Input id="title" value={title} onChange={e => setTitle(e.target.value)} maxLength={160} /></div>}
    <div className="form-field"><label htmlFor="body">{modal.kind === 'handoff' ? '补充说明（可选）' : modal.kind === 'confirm' ? '你的结论' : '资料正文'}</label><Textarea id="body" value={body} onChange={e => setBody(e.target.value)} placeholder={modal.kind === 'confirm' ? '明确你确认的内容和下一步…' : '补充让对方能够直接理解的信息…'} maxLength={modal.kind === 'publish' ? 16000 : modal.kind === 'confirm' ? 4000 : 1000} /></div>
    {error && <p className="form-error" role="alert">{error}</p>}
    <DialogFooter><Button variant="ghost" onClick={close} disabled={busy}>取消</Button><Button disabled={busy || (modal.kind !== 'handoff' && (!body.trim() || !title.trim()))} aria-busy={busy} onClick={() => void save()}>{busy && <LoadingIcon />}{modal.kind === 'handoff' ? '确认找本人' : modal.kind === 'confirm' ? '确认并生成任务' : '确认发布'}</Button></DialogFooter>
  </>;
}
