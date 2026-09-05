import { Button, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@tutti-os/ui-system';
import type { Task } from '../../shared/api';
export const priorityLabels={high:'高优先级',normal:'普通',low:'低优先级'};
export function TaskPriority({task,editable,busy,onChange}: {task:Task;editable:boolean;busy:boolean;onChange:(priority:Task['priority'])=>void}) {
  const value=task.priority || 'normal';
  if (!editable) return value==='normal' ? null : <span className={'priority-label priority-'+value}>{priorityLabels[value]}</span>;
  return <DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="xs" className={'priority-'+value} disabled={busy} aria-label={`优先级：${task.title}`}>{priorityLabels[value]}</Button></DropdownMenuTrigger><DropdownMenuContent>{Object.entries(priorityLabels).map(([priority,label])=><DropdownMenuItem key={priority} disabled={priority===value} onSelect={()=>onChange(priority as Task['priority'])}>{label}</DropdownMenuItem>)}</DropdownMenuContent></DropdownMenu>;
}
