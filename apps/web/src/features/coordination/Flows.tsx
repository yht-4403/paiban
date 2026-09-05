import { useCallback, useEffect, useState } from 'react';
import { Avatar, Button, Checkbox, Textarea } from '@tutti-os/ui-system';
import { AddIcon, ArrowRightIcon, LoadingIcon, MessageSquareTextIcon, TaskIcon } from '@tutti-os/ui-system/icons';
import { api, type State } from '../../shared/api';
import { Markdown } from '../../shared/Markdown';
import { Empty } from '../../shared/ui';
import { useMutation } from '../../shared/useMutation';
import { useTutorialAction } from '../tutorial/bridge';
import { flowLabels, type FlowData } from './types';
import './flows.css';

function useFlow(id:string) {
  const [data,setData]=useState<FlowData|null>(null),[error,setError]=useState('');
  const refresh=useCallback(async()=>{const result=await api<FlowData>('/flows/'+id);setData(result);setError('');},[id]);
  useEffect(()=>{let alive=true;const controller=new AbortController();let pending=false;
    const poll=async()=>{if(pending)return;pending=true;try{const result=await api<FlowData>('/flows/'+id,undefined,controller.signal);if(alive){setData(result);setError('');}}catch(e){if(alive)setError((e as Error).message);}finally{pending=false;}};
    setData(null);void poll();const timer=setInterval(()=>{if(!document.hidden)void poll();},1500);return()=>{alive=false;controller.abort();clearInterval(timer);};},[id]);
  return {data,error,refresh};
}

function readFlowPrompt(key:string) {
  try {
    const draft=JSON.parse(sessionStorage.getItem(key)||'{}') as {prompt?:unknown;title?:unknown;body?:unknown};
    if(typeof draft.prompt==='string')return draft.prompt;
    return [draft.title,draft.body].filter(value=>typeof value==='string'&&value.trim()).join('\n\n');
  } catch { return ''; }
}

function flowTitle(prompt:string) {
  return (prompt.split(/\r?\n/).map(line=>line.trim()).find(Boolean)||prompt.trim()).slice(0,160);
}

export function FlowList({state,assignment,onOpen,onRefresh}:{state:State;assignment:boolean;onOpen:(id:string)=>void;onRefresh:()=>Promise<void>}) {
  const key=`accord.flow-draft.${state.me}.${assignment?'assignment':'meeting'}`;
  const [open,setOpen]=useState(false),[kind,setKind]=useState('sync');
  const [prompt,setPrompt]=useState(()=>readFlowPrompt(key));
  const [members,setMembers]=useState(state.members.filter(m=>m.id!==state.me).slice(0,7).map(m=>m.id));
  const [tutorialExpected,setTutorialExpected]=useState<{assignment:boolean;kind:'sync'|'decision';prompt:string;memberIds:string[];sourceIds:string[]}|null>(null);
  const {mutate,busy,error}=useMutation(onRefresh);
  const items=(state.flows||[]).filter(f=>assignment ? f.kind==='assignment' : ['sync','decision'].includes(f.kind));
  useEffect(()=>{if(prompt)sessionStorage.setItem(key,JSON.stringify({prompt}));else sessionStorage.removeItem(key);},[key,prompt]);
  useEffect(()=>{const release=()=>setTutorialExpected(null);window.addEventListener('accord:tutorial-release',release);return()=>window.removeEventListener('accord:tutorial-release',release);},[]);
  const submit=async(sourceIds:string[]=[])=>{
    const body=prompt.trim();
    if(!body)throw new Error(assignment?'请先填写任务目标。':'请先填写会议议题。');
    const result=await mutate<{id:string}>('/flows',{kind:assignment?'assignment':kind,title:flowTitle(body),body,member_ids:members,...(sourceIds.length?{source_ids:sourceIds}:{})});
    if(!result)throw new Error('提交没有完成，请查看页面提示后重试。');
    setPrompt('');onOpen(result.id);return result;
  };
  useTutorialAction('flow.fill',payload=>{
    if(payload.assignment!==assignment)throw new Error('演练操作区已经变化，请返回当前步骤重试。');
    setTutorialExpected({...payload,memberIds:[...payload.memberIds],sourceIds:[...payload.sourceIds]});
    setOpen(true);setPrompt(payload.prompt);setKind(payload.kind);setMembers(payload.memberIds.filter(id=>id!==state.me));
    return true;
  });
  useTutorialAction('flow.submit',payload=>{
    if(payload.assignment!==assignment)throw new Error('演练操作区已经变化，请返回当前步骤重试。');
    if(!tutorialExpected||tutorialExpected.assignment!==payload.assignment||tutorialExpected.kind!==(payload.kind==='assignment'?'sync':payload.kind)||tutorialExpected.prompt!==payload.expectedPrompt||tutorialExpected.memberIds.join('\0')!==payload.memberIds.join('\0')||tutorialExpected.sourceIds.join('\0')!==payload.sourceIds.join('\0'))throw new Error('演练表单状态已经变化，请重试当前步骤。');
    if(prompt!==payload.expectedPrompt)throw new Error('演练议题已被修改。请重试当前步骤，恢复预填内容后再提交。');
    const currentKind=assignment?'assignment':kind;
    if(currentKind!==payload.kind)throw new Error('演练类型已被修改。请恢复预填类型后再提交。');
    const actualMembers=[state.me,...members].sort();
    const expectedMembers=[...new Set(payload.memberIds)].sort();
    if(actualMembers.length!==expectedMembers.length||actualMembers.some((id,index)=>id!==expectedMembers[index]))throw new Error('演练成员范围已被修改。请重试当前步骤，恢复三位体验成员后再提交。');
    const sourceIds=[...new Set(payload.sourceIds)];
    if(!sourceIds.length||sourceIds.length!==payload.sourceIds.length||sourceIds.some(id=>!state.documents.some(document=>document.id===id)))throw new Error('演练指定的三份共享资料没有完整载入，请稍后重试。');
    if(busy)throw new Error('Agent 正在处理上一项，请稍后重试。');
    return submit(sourceIds).then(result=>{setTutorialExpected(null);return result;});
  });
  return <div className="content-page flows-page"><div className="page-intro page-intro-actions"><h1>{assignment?'任务分配':'开会'}</h1><Button data-tour={assignment?'flow-open-assignment':'flow-open-meeting'} onClick={()=>setOpen(!open)}><AddIcon />{assignment?'分配任务':'发起会议'}</Button></div>
    {open && <form className="flow-editor" data-tour="flow-editor" onSubmit={event=>{event.preventDefault();if(!tutorialExpected)void submit().catch(()=>undefined);}}>
      {!assignment && <div className="work-filters" aria-label="会议类型"><button type="button" data-tour="flow-kind-sync" className={kind==='sync'?'active':''} onClick={()=>setKind('sync')}>同步会</button><button type="button" data-tour="flow-kind-decision" className={kind==='decision'?'active':''} onClick={()=>setKind('decision')}>决策会</button></div>}
      <Textarea data-tour="flow-prompt" aria-label={assignment?'任务目标与背景':'会议议题与背景'} placeholder={assignment?'写下要完成的事、背景和期望结果…':'写下要讨论的议题、背景和需要解决的问题…'} value={prompt} maxLength={8000} onChange={e=>setPrompt(e.target.value)} rows={5} autoFocus />
      <fieldset className="flow-members" data-tour="flow-members"><legend>{assignment?'候选范围':'相关成员'}</legend>{state.members.map(m=><label key={m.id}><Checkbox checked={m.id===state.me || members.includes(m.id)} disabled={m.id===state.me || (!members.includes(m.id) && members.length>=7)} onCheckedChange={v=>setMembers(ids=>v?[...ids,m.id]:ids.filter(id=>id!==m.id))} /><Avatar label={m.person_name} initial={m.person_name[0]} size={20} /><span>{m.person_name}{m.id===state.me?' · 你':''}</span></label>)}</fieldset>
      <div className="flow-actions"><Button type="button" variant="ghost" onClick={()=>setOpen(false)}>取消</Button><Button data-tour="flow-submit" type="submit" disabled={busy || !prompt.trim() || !!tutorialExpected}>{busy?'正在提交':'让 Agent 收集'}</Button></div>
    </form>}
    {error && <p role="alert" className="form-error">{error}</p>}
    {!items.length && !open && <Empty icon={assignment?<TaskIcon size={24}/>:<MessageSquareTextIcon size={24}/>} title={assignment?'还没有任务分配':'还没有会议'}>{assignment?'从右上角发起，Agent 会先收集依据再推荐负责人。':'从右上角发起，Agent 会先收集成员资料再整理议题。'}</Empty>}
    <div className="flow-list">{items.map(f=><button key={f.id} onClick={()=>onOpen(f.id)}><span><strong>{f.title}</strong><small>{f.kind==='sync'?'同步会':f.kind==='decision'?'决策会':'任务分配'} · {flowLabels[f.status]||f.status}</small></span><ArrowRightIcon size={14}/></button>)}</div>
  </div>;
}

export function FlowResult({data,state,onRefresh}:{data:FlowData;state:State;onRefresh:()=>Promise<void>}) {
  const {mutate,busy,error}=useMutation(onRefresh);
  return <div className="flow-result">
    {data.result.summary && <Markdown>{data.result.summary}</Markdown>}
    {data.actions.length>0 && <div className="flow-suggestions"><strong>待办建议</strong>{data.actions.map(a=><div className="flow-suggestion" key={a.id}><div><strong>{a.title}</strong><small>{state.members.find(m=>m.id===a.assignee_id)?.person_name} · {a.status==='accepted'?(a.task_status==='done'?'已完成':'已加入'):a.status==='dismissed'?'已忽略':'待选择'}</small>{a.detail && <p>{a.detail}</p>}</div>{a.assignee_id===state.me && a.status==='suggested' && <div className="flow-actions"><Button size="xs" variant="ghost" disabled={busy} onClick={()=>void mutate(`/flow-actions/${a.id}/dismiss`)}>忽略</Button><Button size="xs" disabled={busy} onClick={()=>void mutate(`/flow-actions/${a.id}/accept`)}>加入待办</Button></div>}</div>)}</div>}
    {error && <p role="alert" className="form-error">{error}</p>}
  </div>;
}

export function FlowPage({id,state,onBack,onThread,onRefresh}:{id:string;state:State;onBack:()=>void;onThread:(id:string)=>void;onRefresh:()=>Promise<void>}) {
  const {data,error,refresh}=useFlow(id);const [selected,setSelected]=useState<string[]>([]);
  const sync=async()=>{await refresh();await onRefresh();};const {mutate,busy,error:mutationError}=useMutation(sync);
  const suggested=data?.result.candidates?.map(c=>c.person_id).join(',')||'';
  useEffect(()=>{setSelected(suggested ? (data?.kind==='assignment'?[suggested.split(',')[0]]:suggested.split(',')) : []);},[id,suggested,data?.kind]);
  useTutorialAction('flow.choose',async payload=>{
    if(payload.flowId!==id||!data)throw new Error('演练事项已经变化，请返回当前步骤重试。');
    if(data.status!=='ready')throw new Error('Agent 还没有完成推荐，请稍后重试。');
    if(data.kind==='assignment'){
      const candidates=new Set(data.result.candidates?.map(candidate=>candidate.person_id)||[]);
      if(payload.memberIds.length!==1||!candidates.has(payload.memberIds[0]))throw new Error('真实推荐中没有体验者三，当前不会创建任务。');
    }
    const result=await mutate<{thread_id:string;task_id?:string}>(`/flows/${id}/choose`,{member_ids:payload.memberIds});
    if(!result)throw new Error('选择没有完成，请查看页面提示后重试。');
    if(data.kind==='decision')onThread(result.thread_id);
    return result;
  });
  if(!data)return <div className="content-page"><Button variant="ghost" onClick={onBack}>返回</Button><p role="status">{error||'正在打开'}</p></div>;
  const owner=data.owner_id===state.me;const processing=['queued','running','summarizing'].includes(data.status);
  return <div className="content-page flows-page"><Button variant="ghost" size="sm" onClick={onBack}>返回</Button><div className="page-intro"><h1>{data.title}</h1></div><div className="flow-status" data-tour="flow-status" role="status">{processing && <LoadingIcon size={14}/>}<span>{flowLabels[data.status]}</span>{processing && data.evidence.length>0 && <small>已收到 {data.evidence.length}/{data.member_ids.length} 位 Agent 的回复</small>}</div>
    <p className="flow-request">{data.body}</p>
    {(error||data.error||mutationError) && <p className="form-error" role="alert">{error||data.error||mutationError}</p>}
    {owner && (data.status==='error'||data.sources_changed) && <Button variant="secondary" disabled={busy} onClick={()=>void mutate(`/flows/${id}/retry`)}>重新整理</Button>}
    <FlowResult data={data} state={state} onRefresh={sync}/>
    {owner && data.status==='ready' && !data.sources_changed && <section className="flow-candidates" data-tour="flow-candidates"><h2>{data.kind==='assignment'?'推荐人选':'参会人选'}</h2>{(data.kind==='assignment' ? data.result.candidates||[] : data.member_ids.map(person_id=>({person_id,reason:data.result.candidates?.find(c=>c.person_id===person_id)?.reason||'按需要邀请'}))).map(c=><label key={c.person_id} data-tour-person={c.person_id}><Checkbox checked={selected.includes(c.person_id)||data.kind==='decision'&&c.person_id===state.me} disabled={data.kind==='decision'&&c.person_id===state.me} onCheckedChange={checked=>setSelected(ids=>data.kind==='assignment'?(checked?[c.person_id]:[]):checked?[...ids,c.person_id]:ids.filter(id=>id!==c.person_id))}/><span><strong>{state.members.find(m=>m.id===c.person_id)?.person_name}</strong><small>{c.reason}</small></span></label>)}
      {!data.result.candidates?.length && data.kind==='assignment' && <p>证据不足，暂未推荐人选。</p>}
      <Button data-tour="flow-choose" disabled={busy||!selected.length} onClick={()=>void mutate<{thread_id:string}>(`/flows/${id}/choose`,{member_ids:selected}).then(result=>{if(result&&data.kind==='decision')onThread(result.thread_id);})}>{data.kind==='assignment'?'分配给选中成员':'开始会议'}</Button>
    </section>}
    {data.thread_id && ['live','assigned','closed'].includes(data.status) && <div className="flow-actions"><Button variant="secondary" onClick={()=>onThread(data.thread_id)}>{data.kind==='assignment'?'查看任务来源':'打开对话'}</Button>{owner&&data.status==='live'&&<Button disabled={busy} onClick={()=>void mutate(`/flows/${id}/finish`)}>结束会议</Button>}</div>}
    {data.evidence.length>0 && <details className="flow-evidence"><summary>个人 Agent 回复 · {data.evidence.length}</summary>{data.evidence.map(e=><section key={e.person_id}><strong>{state.members.find(m=>m.id===e.person_id)?.person_name} · Agent</strong><Markdown>{e.answer}</Markdown><small>{e.sources.map(s=>s.title).join(' · ')||'暂无获准证据'}</small></section>)}</details>}
  </div>;
}

export function ChatSummary({id,state,onRefresh}:{id:string;state:State;onRefresh:()=>Promise<void>}) {
  const {data,error,refresh}=useFlow(id);const sync=async()=>{await refresh();await onRefresh();};const {mutate,busy,error:mutationError}=useMutation(sync);
  return <section className="chat-summary">{data?<><div className="flow-status"><strong>本轮纪要</strong><small>{flowLabels[data.status]}</small></div><FlowResult data={data} state={state} onRefresh={sync}/>{(data.error||error||mutationError)&&<p className="form-error" role="alert">{data.error||error||mutationError}</p>}{data.status==='error'&&data.owner_id===state.me&&<Button size="xs" disabled={busy} onClick={()=>void mutate(`/flows/${id}/retry`)}>重新整理</Button>}</>:<span>{error||'正在整理'}</span>}</section>;
}

export function StateSharing({state,onRefresh}:{state:State;onRefresh:()=>Promise<void>}) {
  const enabled=!!state.context_sharing?.find(g=>g.source_kind==='state'&&g.enabled);
  const {mutate,busy,error}=useMutation(onRefresh);
  return <div className="state-sharing"><label><Checkbox checked={enabled} disabled={busy} onCheckedChange={value=>void mutate('/context-sharing',{source_kind:'state',source_id:state.me,enabled:!!value})}/><span>向团队共享待办与会议状态</span></label>{error&&<small role="alert">{error}</small>}</div>;
}
