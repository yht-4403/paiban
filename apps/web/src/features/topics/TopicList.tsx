import { useState } from 'react';
import { Avatar, Badge, Button, Checkbox, Input, Textarea } from '@tutti-os/ui-system';
import { AddIcon, ArrowRightIcon } from '@tutti-os/ui-system/icons';
import type { State } from '../../shared/api';
import { useMutation } from '../../shared/useMutation';
import { stageLabels } from './types';

export function TopicList({state,onTopic,onRefresh}: {state:State;onTopic:(id:string)=>void;onRefresh:()=>Promise<void>}) {
  const [creating,setCreating]=useState(false);
  return <div className="content-page topic-list"><div className="page-intro page-intro-actions"><h1>课题</h1><Button onClick={()=>setCreating(!creating)}><AddIcon />发起课题</Button></div>
    {creating && <NewTopic state={state} onRefresh={onRefresh} onCreated={onTopic} close={()=>setCreating(false)} />}
    {state.topics.map(topic=><button className="topic-list-row" key={topic.id} onClick={()=>onTopic(topic.id)}><div><strong>{topic.title}</strong><span>{stageLabels[topic.stage]} · {topic.submitted_count}/{topic.member_ids.length} 人已提交</span></div><Badge variant={topic.stage==='decided' ? 'success' : 'secondary'}>{topic.stage==='exploring' ? topic.my_submitted ? '已提交' : '待探索' : stageLabels[topic.stage]}</Badge><ArrowRightIcon size={14} /></button>)}
    {!state.topics.length && !creating && <div className="empty-state"><h2>各自思考，再一起决定</h2><p>用共同简报开始独立探索，提交后统一比较。</p></div>}
  </div>;
}

function NewTopic({state,onCreated,onRefresh,close}: {state:State;onCreated:(id:string)=>void;onRefresh:()=>Promise<void>;close:()=>void}) {
  const [title,setTitle]=useState(''); const [brief,setBrief]=useState(''); const [members,setMembers]=useState<string[]>([]); const [deadline,setDeadline]=useState('');
  const {busy,error,setError,mutate}=useMutation(onRefresh);
  const save=async()=> {
    const date=deadline ? new Date(deadline) : null;
    if (date && (!Number.isFinite(date.getTime()) || date.getTime()<=Date.now())) { setError('请选择未来的截止时间。'); return; }
    const result=await mutate<{id:string}>('/topics',{title,brief,member_ids:members,deadline:date?.toISOString() || ''});
    if (result) onCreated(result.id);
  };
  return <form className="inline-editor" onSubmit={event=> { event.preventDefault(); void save(); }}><div className="inline-editor-heading"><strong>发起课题</strong><span>你主持</span></div>
    <Input aria-label="课题名称" placeholder="这次要解决什么问题" value={title} maxLength={100} onChange={event=>setTitle(event.target.value)} autoFocus />
    <Textarea aria-label="共同简报" placeholder="希望得到什么结果？有哪些共同约束和比较标准？" value={brief} maxLength={8000} onChange={event=>setBrief(event.target.value)} />
    <div className="topic-members-select" aria-label="选择课题参与者">{state.members.filter(member=>member.id!==state.me).map(member=><label key={member.id}><Checkbox checked={members.includes(member.id)} onCheckedChange={checked=>setMembers(ids=>checked ? [...ids,member.id] : ids.filter(id=>id!==member.id))} /><Avatar size={24} label={member.person_name} initial={member.person_name[0]} /><span>{member.person_name}</span></label>)}</div>
    {!state.members.some(member=>member.id!==state.me) && <p className="context-description">请先在工作空间设置中邀请一位同事。</p>}
    <details className="topic-deadline"><summary>设置截止时间</summary><Input type="datetime-local" aria-label="探索截止时间" value={deadline} onChange={event=>setDeadline(event.target.value)} /></details>
    {error && <p role="alert" className="form-error">{error}</p>}<div className="inline-editor-footer"><span>各自探索 · 提交后统一公开</span><Button type="button" variant="ghost" disabled={busy} onClick={close}>取消</Button><Button type="submit" disabled={busy || !title.trim() || !brief.trim() || !members.length}>开始探索</Button></div>
  </form>;
}
