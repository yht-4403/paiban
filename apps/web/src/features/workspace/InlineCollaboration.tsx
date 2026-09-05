import { useState } from 'react';
import { Avatar, Button, Input, Select, SelectContent, SelectItem, SelectTrigger, SelectValue, Textarea } from '@tutti-os/ui-system';
import type { State, ThreadData } from '../../shared/api';
import { useMutation } from '../../shared/useMutation';

export function InlineCollaboration({kind,state,data,initialTarget,close,onRefresh,onOpen}: {
  kind:'handoff'|'confirm'|'share';state:State;data:ThreadData;initialTarget?:string;close:()=>void;onRefresh:()=>Promise<void>;onOpen:(id:string)=>void;
}) {
  const [target,setTarget]=useState(initialTarget || '');
  const [title,setTitle]=useState(data.thread.title);
  const [body,setBody]=useState(kind==='share' ? [...data.messages].reverse().find(message=>message.from_kind==='agent' && message.meta.status==='done')?.body.slice(0,8000) || '' : '');
  const [scheduled,setScheduled]=useState(false); const [deadline,setDeadline]=useState('');
  const {busy,error,setError,mutate}=useMutation(onRefresh);
  const recipient=state.members.find(member=>member.id===(kind==='share' ? target : kind==='handoff' ? data.thread.target_id : data.thread.owner_id));
  const save=async()=> {
    let path=`/threads/${data.thread.id}/${kind}`;
    let values:Record<string,unknown>;
    if (kind==='handoff') {
      const date=new Date(deadline);
      if (scheduled && (!deadline || !Number.isFinite(date.getTime()) || date.getTime()<=Date.now())) { setError('请选择未来的送达时间。'); return; }
      values={mode:scheduled ? 'deadline' : 'now',deadline:scheduled ? date.toISOString() : '',note:body};
    } else if (kind==='confirm') values={conclusion:body,task_title:title,assignee_id:state.me};
    else values={target_id:target,title,body,source_ids:[]};
    const result=await mutate<{id?:string}>(path,values);
    if (result) { close(); if (result.id) onOpen(result.id); }
  };
  return <form className="inline-editor collaboration-editor" onSubmit={event=> { event.preventDefault(); void save(); }}>
    <div className="inline-editor-heading"><strong>{kind==='confirm' ? '确认并承接' : kind==='share' ? '交给同事' : '找本人'}</strong>{recipient && <span className="inline-recipient"><Avatar size={22} label={recipient.person_name} initial={recipient.person_name[0]} />{recipient.person_name}</span>}</div>
    {kind==='share' && <Select value={target} onValueChange={setTarget}><SelectTrigger aria-label="选择接收者"><SelectValue placeholder="交给谁" /></SelectTrigger><SelectContent>{state.members.filter(member=>member.id!==state.me).map(member=><SelectItem key={member.id} value={member.id}>{member.person_name}</SelectItem>)}</SelectContent></Select>}
    {kind!=='handoff' && <Input aria-label={kind==='share' ? '分享标题' : '任务名称'} placeholder={kind==='share' ? '分享标题' : '下一步任务'} maxLength={160} value={title} onChange={event=>setTitle(event.target.value)} />}
    {kind==='handoff' && <div className="handoff-scope"><span>本段聊天 · {data.messages.filter(message=>message.from_kind!=='system').length} 条消息</span><Button type="button" size="xs" variant="ghost" onClick={()=>setScheduled(!scheduled)}>{scheduled ? '改为现在送达' : '安排送达时间'}</Button>{scheduled && <Input type="datetime-local" aria-label="送达时间" value={deadline} onChange={event=>setDeadline(event.target.value)} />}</div>}
    <Textarea aria-label={kind==='confirm' ? '承接结论' : kind==='share' ? '分享内容' : '转交补充'} placeholder={kind==='confirm' ? '你的判断与下一步…' : kind==='share' ? '对方需要知道的内容…' : '可补充一句（可选）'} value={body} maxLength={kind==='handoff' ? 1000 : kind==='confirm' ? 4000 : 8000} onChange={event=>setBody(event.target.value)} />
    {error && <p role="alert" className="form-error">{error}</p>}<div className="inline-editor-footer"><span>{kind==='confirm' ? '双方可见 · 由你负责' : kind==='share' ? '仅发送上方内容' : '系统自动整理本段聊天'}</span><Button type="button" variant="ghost" disabled={busy} onClick={close}>取消</Button><Button type="submit" disabled={busy || (kind!=='handoff' && (!title.trim() || !body.trim())) || (kind==='share' && !target)}>{kind==='confirm' ? '确认承接' : kind==='share' ? '发送给本人' : scheduled ? '安排送达' : '发送给本人'}</Button></div>
  </form>;
}
