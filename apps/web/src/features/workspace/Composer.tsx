import { useState } from 'react';
import { Button, Checkbox, Popover, PopoverContent, PopoverTrigger, Textarea } from '@tutti-os/ui-system';
import { AddIcon, ArrowRightIcon, CheckIcon, FileTextIcon, LoadingIcon } from '@tutti-os/ui-system/icons';
import type { Document } from '../../shared/api';

export function Composer({ documents, onSend, busy, human = false, disabled = false, initial = '', modelMode = 'retrieval' }: { documents: Document[]; onSend: (body: string, sourceIds: string[]) => Promise<boolean>; busy: boolean; human?: boolean; disabled?: boolean; initial?: string; modelMode?: string }) {
  const [value, setValue] = useState(initial);
  const [sources, setSources] = useState<string[]>([]);
  const send = async () => { if (!value.trim() || busy || disabled) return; if (await onSend(value.trim(), sources)) { setValue(''); setSources([]); } };
  return <div className="composer-wrap">
    <div className="composer" aria-busy={busy}>
      <Textarea aria-label={human ? '回复本人' : '输入协作请求'} placeholder={human ? '写下你的判断或补充信息…' : '说说你想推进什么，或引用一份共享资料…'} value={value} disabled={disabled || busy}
        onChange={e => setValue(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(); } }} />
      {sources.length > 0 && <div className="composer-sources">{sources.map(id => <span key={id}><FileTextIcon size={12} />{documents.find(d => d.id === id)?.title}</span>)}</div>}
      <div className="composer-toolbar"><div className="inline-actions">
        <Popover><PopoverTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="引用共享资料" disabled={disabled || busy}><AddIcon /></Button></PopoverTrigger>
          <PopoverContent align="start" className="source-picker"><strong>引用共享资料</strong><p>只引用已明确共享的成果。</p>
            {documents.map(doc => <label className="source-option" key={doc.id}><Checkbox checked={sources.includes(doc.id)} onCheckedChange={checked => setSources(s => checked ? [...s, doc.id] : s.filter(id => id !== doc.id))} /><FileTextIcon size={14} /><span>{doc.title}</span></label>)}
          </PopoverContent></Popover>
        <span className="composer-mode">{human ? <CheckIcon size={13} /> : <span className="agent-dot" />}{human ? '本人会话' : modelMode === 'model' ? 'Agent · 已连接模型' : '共享资料检索'}</span>
      </div><Button size="icon" aria-label="发送消息" disabled={!value.trim() || busy || disabled} onClick={() => void send()}>{busy ? <LoadingIcon /> : <ArrowRightIcon className="send-arrow" />}</Button></div>
    </div>
    <div className="composer-hint"><span>{human ? '消息会发送给这条协作的参与者' : 'Agent 先接住请求，需要时再找本人'}</span><span>Enter 发送 · Shift Enter 换行</span></div>
  </div>;
}
