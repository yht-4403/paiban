import type { Task } from '../../shared/api';

export function isExplorationTask(task: Task) {
  return task.task_type === 'exploration';
}

export function contextTaskBuckets(tasks: Task[], today=new Date().toLocaleDateString()) {
  return {
    primary: tasks.filter(task=>isExplorationTask(task) || task.status !== 'done'),
    completedToday: tasks.filter(task=>!isExplorationTask(task) && task.status === 'done' && !!task.updated_at && new Date(task.updated_at).toLocaleDateString() === today),
  };
}
