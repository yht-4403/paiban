import assert from 'node:assert/strict';
import test from 'node:test';
import { contextTaskBuckets } from './contextTasks.ts';

const task=(id,status,taskType='normal')=>({
  id,
  status,
  task_type:taskType,
  title:id,
  detail:'',
  assignee_id:'fixed_trial_1',
  creator_id:'fixed_trial_1',
  thread_id:'thread_1',
  topic_id:taskType==='exploration'?'topic_1':'',
  priority:'normal',
  updated_at:'2026-09-06T08:00:00.000Z',
});

test('已提交的创新探索仍留在主待办，普通完成项进入今日完成',()=>{
  const today=new Date('2026-09-06T08:00:00.000Z').toLocaleDateString();
  const buckets=contextTaskBuckets([
    task('exploration-done','done','exploration'),
    task('normal-open','todo'),
    task('normal-done','done'),
  ],today);

  assert.deepEqual(buckets.primary.map(item=>item.id),['exploration-done','normal-open']);
  assert.deepEqual(buckets.completedToday.map(item=>item.id),['normal-done']);
});
