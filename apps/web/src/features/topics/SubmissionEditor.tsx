import { useEffect, useState } from 'react';
import { Button, Checkbox, Input, Textarea } from '@tutti-os/ui-system';
import type { State } from '../../shared/api';
import { useMutation } from '../../shared/useMutation';
import { proposalDraftKey, type Topic } from './types';

export function SubmissionEditor({topic,state,onRefresh,close}: {topic:Topic;state:State;onRefresh:()=>Promise<void>;close:()=>void}) {
  const key=proposalDraftKey(state.me,topic.id);
  const [initial]=useState(()=> { try { return JSON.parse(sessionStorage.getItem(key) || 'null') as {title:string;body:string;sources:string[]} | null; } catch { return null; } });
  const [title,setTitle]=useState(initial?.title || topic.my_submission?.title || '');
  const [body,setBody]=useState(initial?.body || topic.my_submission?.body || '');
  const [sources,setSources]=useState<string[]>(initial?.sources || topic.my_submission?.sources.map(ref=>ref.id) || []);
  const {busy,error,mutate}=useMutation(onRefresh);
  useEffect(()=> { sessionStorage.setItem(key,JSON.stringify({title,body,sources})); },[key,title,body,sources]);
  const save=async()=> {
    const result=await mutate(`/topics/${topic.id}/submit`,{title,body,source_ids:sources,expected_version:topic.submission_version});
    if (result) { sessionStorage.removeItem(key); close(); }
  };
  const available=state.documents.filter(resource=>resource.scope==='team' || resource.round_id===topic.id);
  return <form className="inline-editor submission-editor" onSubmit={event=> { event.preventDefault(); void save(); }}><div className="inline-editor-heading"><strong>{topic.my_submission ? '替换提交' : '提交方案'}</strong><span>等待统一公开</span></div>
    <Input aria-label="方案名称" placeholder="方案名称" value={title} maxLength={160} onChange={event=>setTitle(event.target.value)} autoFocus />
    <Textarea aria-label="方案正文" placeholder="核心主张、证据、限制与下一步…" value={body} maxLength={12000} onChange={event=>setBody(event.target.value)} />
    <details className="submission-evidence"><summary>附上证据{sources.length ? ` · ${sources.length}` : ''}</summary>{available.map(resource=><label key={resource.id} className="source-option"><Checkbox checked={sources.includes(resource.id)} disabled={!sources.includes(resource.id) && sources.length>=10} onCheckedChange={checked=>setSources(ids=>checked ? [...ids,resource.id] : ids.filter(id=>id!==resource.id))} /><span>{resource.title}</span></label>)}</details>
    {error && <p className="form-error" role="alert">{error}</p>}<div className="inline-editor-footer"><span>公开给本轮 {topic.member_ids.length} 人 · 不含私人聊天</span><Button type="button" variant="ghost" disabled={busy} onClick={close}>收起</Button><Button type="submit" disabled={busy || !title.trim() || !body.trim() || topic.stage!=='exploring'}>提交本轮</Button></div>
  </form>;
}
