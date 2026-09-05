import { useState } from 'react';
import { Avatar, Button, Checkbox, Input, Popover, PopoverContent, PopoverTrigger } from '@tutti-os/ui-system';
import { AddIcon } from '@tutti-os/ui-system/icons';
import type { Member } from '../../shared/api';

export function GroupPicker({ members, onChoose, initial=[], adding=false, limit=7 }: {
  members: Member[]; onChoose: (ids: string[]) => Promise<boolean>; initial?: string[]; adding?: boolean; limit?: number;
}) {
  const [open,setOpen]=useState(false), [selected,setSelected]=useState<string[]>(initial), [query,setQuery]=useState(''), [busy,setBusy]=useState(false);
  return <Popover open={open} onOpenChange={value=>{ if (!busy) { setOpen(value); if (value) {setSelected(initial);setQuery('');} } }}>
    <PopoverTrigger asChild><Button variant="ghost" size="icon-sm" aria-label={adding ? '邀请群成员' : '发起群聊'} title={adding ? '邀请群成员' : '发起群聊'} disabled={limit<1}><AddIcon /></Button></PopoverTrigger>
    <PopoverContent align="end" collisionPadding={12} className="group-picker"><strong>{adding ? '邀请成员' : '发起群聊'}</strong><Input aria-label="搜索群成员" placeholder="搜索同事" value={query} onChange={event=>setQuery(event.target.value)} />
      <div className="group-picker-list">{members.filter(member=>member.person_name.includes(query.trim())).map(member=><label key={member.id} className="group-picker-person"><Checkbox checked={selected.includes(member.id)} disabled={busy || (!selected.includes(member.id) && selected.length>=limit)} onCheckedChange={checked=>setSelected(ids=>checked ? [...ids,member.id] : ids.filter(id=>id!==member.id))} /><Avatar size={24} label={member.person_name} initial={member.person_name[0]} /><span>{member.person_name}</span></label>)}</div>
      <small>{adding ? '新成员仅看加入后的消息' : '新群不带入私聊记录'}</small><Button disabled={busy || selected.length<(adding ? 1 : 2)} onClick={()=>{setBusy(true);void onChoose(selected).then(ok=>{if(ok)setOpen(false);}).finally(()=>setBusy(false));}}>{busy ? '正在保存' : adding ? `邀请${selected.length ? ` ${selected.length} 人` : ''}` : `建群${selected.length ? ` ${selected.length+1} 人` : ''}`}</Button>
    </PopoverContent>
  </Popover>;
}
