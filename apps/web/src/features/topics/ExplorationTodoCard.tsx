import { ArrowRightIcon, SuccessLinedIcon, ThinkingIcon } from '@tutti-os/ui-system/icons';
import type { Task, TopicSummary } from '../../shared/api';

function statusCopy(task: Task, topic?: TopicSummary) {
  const progress=task.exploration;
  const stage=progress?.stage||topic?.stage||'exploring';
  const completion=progress?.completion_state||topic?.completion_state||'in_progress';
  const allSubmitted=progress?.all_submitted??topic?.all_submitted??false;
  if(stage==='decided'||completion==='decided')return '已形成决策';
  if(stage==='reviewing'||completion==='reviewing')return '方向已公开 · 可比较';
  if(completion==='ready_for_review'||allSubmitted)return '方向已齐 · 待公开';
  return '独立探索中';
}

export function ExplorationTodoCard({task,topic,onOpen}:{task:Task;topic?:TopicSummary;onOpen?:()=>void}) {
  const progress=task.exploration;
  const stage=progress?.stage||topic?.stage||'exploring';
  const completion=progress?.completion_state||topic?.completion_state||'in_progress';
  const submitted=progress?.submitted_count??topic?.submitted_count??0;
  const members=progress?.member_count??topic?.member_ids.length??0;
  const directions=progress?.direction_count??topic?.direction_count??0;
  const allSubmitted=progress?.all_submitted??topic?.all_submitted??false;
  const highlighted=progress?.is_highlighted??topic?.is_highlighted??(stage!=='exploring'||completion!=='in_progress'||allSubmitted);
  const decided=stage==='decided';
  const status=statusCopy(task,topic);
  const directionLabel=stage==='exploring'?'已封存方向':'公开方向';
  return <button type="button" className={`exploration-todo-card${highlighted?' is-highlighted':''}`} data-tour-task={task.id} onClick={onOpen} disabled={!onOpen} aria-label={onOpen?`打开创新探索：${task.title}，${status}`:`创新探索正在准备：${task.title}`}>
    <span className="exploration-todo-icon" aria-hidden="true">{decided?<SuccessLinedIcon size={17}/>:<ThinkingIcon size={17}/>}</span>
    <span className="exploration-todo-content">
      <span className="exploration-todo-eyebrow"><span>创新探索</span><span>{status}</span></span>
      <strong>{task.title}</strong>
      <small>{submitted}/{members} 人已提交{directions>0?` · ${directions} 个${directionLabel}`:''}</small>
    </span>
    <ArrowRightIcon className="exploration-todo-arrow" size={15} aria-hidden="true"/>
  </button>;
}
