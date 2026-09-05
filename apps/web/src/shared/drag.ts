import type { DragEvent } from 'react';

export type DragItem = { kind: 'thread' | 'resource' | 'folder' | 'member'; id: string };
const mime = 'application/x-accord-item';
let active: DragItem | null = null;
export function dragStart(event: DragEvent, item: DragItem) {
  active=item; event.dataTransfer.setData(mime,JSON.stringify(item)); event.dataTransfer.effectAllowed='copyMove';
}
export function dragEnd() { active=null; }
export function acceptsDrag(event: DragEvent, kinds: DragItem['kind'][]) {
  return !!active && event.dataTransfer.types.includes(mime) && kinds.includes(active.kind);
}
export function receiveDrop(event: DragEvent, kinds: DragItem['kind'][]): DragItem | null {
  event.preventDefault();
  try {
    const item = JSON.parse(event.dataTransfer.getData(mime)) as DragItem;
    return kinds.includes(item.kind) && typeof item.id==='string' && item.id.length<=100 ? item : null;
  } catch { return null; } finally { active=null; }
}
