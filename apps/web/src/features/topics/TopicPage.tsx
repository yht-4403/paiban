import { useEffect, useState } from 'react';
import { Avatar, Badge, Button, Checkbox, Input, Select, SelectContent, SelectItem, SelectTrigger, SelectValue, Textarea } from '@tutti-os/ui-system';
import { AddIcon, ArrowLeftIcon, CheckIcon, MessageSquareTextIcon, ThinkingIcon } from '@tutti-os/ui-system/icons';
import { api, command, timeLabel, type ResourceRef, type State, type ThreadData } from '../../shared/api';
import { Markdown } from '../../shared/Markdown';
import { Pending } from '../../shared/ui';
import { useMutation } from '../../shared/useMutation';
import { useTopic } from './useTopic';
import { SubmissionEditor } from './SubmissionEditor';
import { proposalDraftKey, stageLabels, type Topic } from './types';

function TopicWorkflow({topic}:{topic:Topic}) {
  const allSubmitted=topic.all_submitted ?? (topic.member_ids.length>0 && topic.submitted_count>=topic.member_ids.length);
  const current=topic.stage==='decided'?4:topic.stage==='reviewing'?2:allSubmitted?1:0;
  const directions=topic.direction_count ?? (topic.stage==='exploring'?topic.submitted_count:topic.proposals.length);
  const steps=[
    {label:'各自探索',detail:'过程仅自己可见'},
    {label:'提交封存',detail:`${topic.submitted_count}/${topic.member_ids.length} 人已提交`},
    {label:'公开比较',detail:`${directions} 个方向`},
    {label:'形成决策',detail:topic.decision?'结论与理由已记录':'记录取舍与分歧'},
  ];
  const status=topic.stage==='decided'?'已形成决策':topic.stage==='reviewing'?'方向已公开，可以比较':allSubmitted?'方向已齐，等待主持人公开':'成员正在独立探索';
  return <section className="topic-workflow" aria-labelledby="topic-workflow-title">
    <div className="topic-workflow-heading"><span id="topic-workflow-title"><ThinkingIcon size={16}/>创新探索工作流</span><small>{status}</small></div>
    <ol>{steps.map((step,index)=>{const complete=index<current;const active=index===current;return <li key={step.label} className={`${complete?'is-complete ':''}${active?'is-active':''}`} aria-current={active?'step':undefined}><span className="topic-workflow-marker" aria-hidden="true">{complete?<CheckIcon size={13}/>:index+1}</span><span><strong>{step.label}</strong><small>{step.detail}</small></span></li>;})}</ol>
    <p>共同简报固定本轮标准；统一公开前，每位成员只能看到自己的过程与封存成果。</p>
  </section>;
}

export function TopicPage({id,section,state,onBack,onThread,onRefresh,onResource}: {
  id:string;section:string;state:State;onBack:()=>void;onThread:(id:string)=>void;onRefresh:()=>Promise<void>;onResource:(ref:ResourceRef)=>void;
}) {
  const {topic,error:loadError,refresh}=useTopic(id);
  const reload=async()=> { await refresh(); await onRefresh(); };
  const {busy,error,setError,mutate}=useMutation(reload);
  const [editing,setEditing]=useState(section==='submit'); const [chosen,setChosen]=useState<string[]>([]);
  const [decision,setDecision]=useState(()=>sessionStorage.getItem(`accord.decision.${state.me}.${id}`) || '');
  const [target,setTarget]=useState(''); const [taskTitle,setTaskTitle]=useState('');
  useEffect(()=> { if (section==='submit') setEditing(true); },[section]);
  useEffect(()=> { sessionStorage.setItem(`accord.decision.${state.me}.${id}`,decision); },[decision,id,state.me]);
  if (!topic) return loadError ? <div className="empty-state"><p role="alert">{loadError}</p><Button onClick={()=>void refresh().catch(error=>setError(error.message))}>重新连接</Button></div> : <Pending label="正在打开课题" />;
  const host=topic.owner_id===state.me;
  const assignmentRound=!!topic.task_ids?.length;
  const begin=async()=> { const result=await mutate<{id:string}>(`/topics/${id}/explorations`,{title:topic.title+' · 我的探索'}); if (result) onThread(result.id); };
  const compare=async()=> {
    const result=await mutate<{id:string}>(`/topics/${id}/reviews`);
    if (!result) return;
    try { const data=await api<ThreadData>(`/threads/${result.id}`); if (!data.messages.length) await command(`/threads/${result.id}/messages`,{body:'请先查阅共同简报和本轮全部已公开方案，按假设、过程、发现、风险和下一步逐项比较，注明资料来源。保留尚未验证的问题与分歧，不替人作决定。'}); onThread(result.id); }
    catch (error) { setError((error as Error).message); }
  };
  const withdraw=async()=> {
    if (topic.my_submission) sessionStorage.setItem(proposalDraftKey(state.me,id),JSON.stringify({title:topic.my_submission.title,body:topic.my_submission.body,sources:topic.my_submission.sources.map(ref=>ref.id)}));
    if (await mutate(`/topics/${id}/withdraw`,{expected_version:topic.submission_version})) setEditing(true);
  };
  const decide=async()=> { if (await mutate(`/topics/${id}/decision`,{expected_version:topic.version,body:decision,proposal_ids:chosen})) sessionStorage.removeItem(`accord.decision.${state.me}.${id}`); };
  const handoff=async()=> { const result=await mutate<{id:string}>(`/topics/${id}/handoff`,{target_id:target,task_title:taskTitle}); if (result) onThread(result.id); };
  return <div className="content-page topic-page"><button className="back-link" onClick={onBack}><ArrowLeftIcon size={14} />任务分配</button><div className="page-intro page-intro-actions"><div><h1>{topic.title}</h1><span className="topic-stage"><Badge variant={topic.stage==='decided' ? 'success' : 'secondary'}>{stageLabels[topic.stage]}</Badge>{topic.is_fixture&&<Badge variant="secondary">只读虚拟实例</Badge>}{topic.deadline && <span>{timeLabel(topic.deadline)} 截止</span>}</span></div>{topic.is_fixture ? <Button variant="ghost" size="sm" disabled={busy} onClick={()=>void mutate('/tutorial/exploration/reset')}>重置实例</Button> : topic.stage!=='exploring' && <Button variant="secondary" disabled={busy} onClick={()=>void compare()}>请 Agent 比较</Button>}</div>
    {(error || loadError) && <p className="form-error" role="alert">{error || loadError}</p>}
    <TopicWorkflow topic={topic}/>
    <section className="topic-progress-section"><div className="topic-section-heading"><h2>方向进度</h2><small>{topic.submitted_count}/{topic.member_ids.length} 人已封存</small></div><div className="topic-participants" aria-label="创新探索参与者与进度">{topic.progress.map(progress=> { const member=state.members.find(m=>m.id===progress.member_id); if(!member)return null;return <div key={member.id}><Avatar size={28} label={member.person_name} initial={member.person_name[0]} /><span>{member.person_name}{member.id===state.me ? ' · 你' : ''}<small>{progress.status==='submitted' ? '已封存方向' : progress.status==='exploring' ? '探索中' : '未开始'}</small></span></div>; })}</div></section>
    <details className="topic-brief" open={!topic.explorations.length && topic.stage==='exploring'}><summary>共同简报 <small>v1 · 本轮固定</small></summary><Markdown>{topic.brief.body}</Markdown>{topic.brief.refs.map(ref=><Button key={ref.id} size="xs" variant="ghost" onClick={()=>onResource(ref)}>查阅引用资料</Button>)}</details>
    {topic.stage==='exploring' ? <>
      <section className="topic-section"><div className="topic-section-heading"><h2>我的方向与过程</h2><Button variant="secondary" size="sm" disabled={busy} onClick={()=>void begin()}><AddIcon />{topic.explorations.length ? '新方向' : '开始我的探索'}</Button></div>{topic.explorations.map(thread=><button key={thread.id} className="exploration-row" onClick={()=>onThread(thread.id)}><MessageSquareTextIcon size={15} /><span>{thread.title}</span><small>仅自己</small></button>)}</section>
      <section className="topic-section"><div className="topic-section-heading"><h2>我的提交{topic.my_submission && <small>v{topic.my_submission.version}</small>}</h2>{!editing && <Button variant="secondary" size="sm" onClick={()=>setEditing(true)}>{topic.my_submission ? '替换提交' : '整理提交'}</Button>}</div>
        {editing ? <SubmissionEditor topic={topic} state={state} onRefresh={reload} close={()=>setEditing(false)} /> : topic.my_submission ? <><h3>{topic.my_submission.title}</h3><Markdown>{topic.my_submission.body}</Markdown><div className="submission-status"><span>已保存，等待统一公开</span><Button variant="ghost" size="xs" disabled={busy} onClick={()=>void withdraw()}>撤回提交</Button></div></> : <p className="context-description">只提交准备公开的成果，探索过程保留在自己的聊天里。</p>}
      </section>
      <div className="release-row"><div><strong>{topic.submitted_count} / {topic.member_ids.length} 人已提交</strong><small>{topic.member_ids.length-topic.submitted_count ? `还有 ${topic.member_ids.length-topic.submitted_count} 人未提交` : '本轮方案已齐'}</small></div>{host ? <Button disabled={busy || !topic.submitted_count || assignmentRound&&!topic.all_submitted} onClick={()=>void mutate(`/topics/${id}/release`,{expected_version:topic.version})}>{assignmentRound&&!topic.all_submitted?'等待全员提交':`向本轮成员公开 ${topic.submitted_count} 份方案`}</Button> : <span>等待主持人统一公开</span>}</div>
    </> : <>
      <section className="topic-section"><div className="topic-section-heading"><h2>公开方向</h2><small>{topic.proposals.length} 份</small></div><div className="comparison-guide"><strong>统一比较</strong><span>假设</span><span>过程</span><span>发现</span><span>风险</span><span>下一步</span></div><div className="proposal-comparison">{topic.proposals.map(proposal=><article key={proposal.id}><div className="proposal-byline"><span>{state.members.find(member=>member.id===proposal.author_id)?.person_name} · v{proposal.proposal_version}</span>{host && topic.stage==='reviewing' && <label><Checkbox checked={chosen.includes(proposal.proposal_id)} aria-label={`纳入决策：${proposal.title}`} onCheckedChange={checked=>setChosen(ids=>checked ? [...ids,proposal.proposal_id] : ids.filter(id=>id!==proposal.proposal_id))} />纳入决策</label>}</div><h3>{proposal.title}</h3><Markdown>{proposal.body}</Markdown>{proposal.refs.map(ref=><Button key={ref.id} variant="ghost" size="xs" onClick={()=>onResource(ref)}>查看证据</Button>)}</article>)}</div></section>
      {topic.decision ? <section className="topic-section"><h2>决策与理由</h2><Markdown>{topic.decision.body}</Markdown><div className="decision-sources">{topic.decision.refs.map(ref=><Button key={ref.id} size="xs" variant="secondary" onClick={()=>onResource(ref)}>{topic.proposals.find(p=>p.id===ref.id)?.title || '采用的方案'}</Button>)}</div>
        {host&&!topic.is_fixture && <form className="inline-editor decision-handoff" onSubmit={event=> { event.preventDefault(); void handoff(); }}><strong>安排下一步</strong><Input aria-label="交接任务名称" placeholder="下一步要验证或完成什么" value={taskTitle} maxLength={160} onChange={event=>setTaskTitle(event.target.value)} /><Select value={target} onValueChange={setTarget}><SelectTrigger aria-label="选择承接人"><SelectValue placeholder="交给谁" /></SelectTrigger><SelectContent>{topic.member_ids.filter(uid=>uid!==state.me).map(uid=><SelectItem key={uid} value={uid}>{state.members.find(member=>member.id===uid)?.person_name}</SelectItem>)}</SelectContent></Select><div className="inline-editor-footer"><span>携带决策 · 等待本人承接</span><Button type="submit" disabled={busy || !target || !taskTitle.trim()}>交给本人</Button></div></form>}
        {topic.handoffs.map(item=><div className="topic-handoff-row" key={item.thread_id}><span>{state.members.find(member=>member.id===item.target_id)?.person_name}</span><small>{item.status==='resolved' ? '已承接' : '待本人确认'}</small>{(host || item.target_id===state.me) && <Button variant="ghost" size="xs" onClick={()=>onThread(item.thread_id)}>查看交接</Button>}</div>)}
      </section> : host ? <form className="inline-editor" onSubmit={event=> { event.preventDefault(); void decide(); }}><div className="inline-editor-heading"><strong>比较与决策</strong><span>已选择 {chosen.length} 份方向</span></div><Textarea aria-label="决策结论" placeholder="采用哪些方向、理由与取舍是什么？还存在哪些分歧，下一步由谁验证？" value={decision} maxLength={4000} onChange={event=>setDecision(event.target.value)} /><div className="inline-editor-footer"><span>本轮成员可见</span><Button type="submit" disabled={busy || !chosen.length || !decision.trim()}>确认决策</Button></div></form> : <p className="context-description">主持人确认决策后，会显示在这里。</p>}
    </>}
  </div>;
}
