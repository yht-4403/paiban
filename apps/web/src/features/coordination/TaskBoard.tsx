import { useState } from 'react';
import { Badge, Button } from '@tutti-os/ui-system';
import { CheckIcon } from '@tutti-os/ui-system/icons';
import type { State, Task } from '../../shared/api';
import { StateSharing } from './Flows';

export function TaskBoard({state,busy,onTask,onThread,onRefresh}:{state:State;busy:boolean;onTask:(task:Task)=>void;onThread:(id:string)=>void;onRefresh:()=>Promise<void>}) {
  const [filter,setFilter]=useState('mine');
  const suggestions=(state.flows||[]).filter(f=>f.pending_action_count&&f.thread_id);
  const tasks=state.tasks.filter(t=>filter==='mine'?t.assignee_id===state.me:t.creator_id===state.me&&t.assignee_id!==state.me);
  return <div className="content-page"><div className="page-intro"><h1>待办</h1></div><StateSharing state={state} onRefresh={onRefresh}/><div className="work-filters"><button className={filter==='mine'?'active':''} onClick={()=>setFilter('mine')}>我负责</button><button className={filter==='created'?'active':''} onClick={()=>setFilter('created')}>我发起</button></div>
    {filter==='mine'&&suggestions.map(f=><button className="flow-pending" key={f.id} onClick={()=>onThread(f.thread_id)}><strong>{f.title}</strong><span>{f.pending_action_count} 条待办建议 →</span></button>)}
    {!tasks.length&&<p className="subtle-message">暂无待办</p>}
    <div className="task-list">{tasks.map(task=><article className={`task-row ${task.status==='done'?'done':''}`} key={task.id}><Button size="icon-sm" variant={task.status==='done'?'secondary':'outline'} aria-label={`${task.status==='done'?'重新打开':'完成'}：${task.title}`} disabled={busy||task.assignee_id!==state.me} onClick={()=>onTask(task)}>{task.status==='done'?<CheckIcon/>:<span/>}</Button><div><button onClick={()=>onThread(task.thread_id)}>{task.title}</button><p>{task.detail}</p><small>{state.members.find(m=>m.id===task.assignee_id)?.person_name} 负责 · {task.assign_reason||'本人确认'}</small></div><Badge variant={task.status==='done'?'success':'secondary'}>{task.status==='done'?'已完成':'待推进'}</Badge></article>)}</div>
  </div>;
}
