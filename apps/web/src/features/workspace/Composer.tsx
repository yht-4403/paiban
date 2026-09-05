import { useEffect, useState, type ReactNode } from 'react';
import { Button, Textarea } from '@tutti-os/ui-system';
import { ArrowRightIcon, LoadingIcon } from '@tutti-os/ui-system/icons';
import type { Document, ThreadContext, ResourceRef } from '../../shared/api';
import { Materials } from './Materials';

export function Composer({ folders, documents, onSend, busy, human=false, running, onStop, draftId, model, workspace, context, onBind, onFolder, onResource, pendingContext, initialValue='', allowEmpty=false, sendDisabled=false, sendLabel, inputLabel, placeholder, maxLength=8000, audience, contextLabel, accessory, error }: {
  folders?: {id:string;name:string}[]; documents: Document[]; onSend: (body: string, sourceIds: string[]) => Promise<boolean>; busy: boolean; human?: boolean;
  context?: ThreadContext; onBind?: (id: string, selected: boolean) => void; onFolder?: (id: string, selected?: boolean) => void; onResource: (resource: ResourceRef) => void; pendingContext?: boolean;
  running?: boolean; onStop: () => void; draftId: string; model: string; workspace: string;
  initialValue?: string; allowEmpty?: boolean; sendDisabled?: boolean; sendLabel?: string; inputLabel?: string; placeholder?: string;
  maxLength?: number; audience?: string; contextLabel?: string; accessory?: ReactNode; error?: string;
}) {
  const [value,setValue] = useState(() => sessionStorage.getItem(draftId) ?? initialValue);
  const [sources,setSources] = useState<string[]>(()=> { try { return JSON.parse(sessionStorage.getItem(draftId+'.sources') || '[]'); } catch { return []; } });
  useEffect(()=> { sessionStorage.setItem(draftId+'.sources',JSON.stringify(sources)); },[sources,draftId]);
  const materials=context?.resources || documents.filter(document=>sources.includes(document.id));
  const toggle=(id:string,selected:boolean)=> { if (context && onBind) onBind(id,selected); else setSources(items=>selected ? [...new Set([...items,id])] : items.filter(item=>item!==id)); };
  useEffect(() => { sessionStorage.setItem(draftId,value); },[draftId,value]);
  const cannotSend = (!allowEmpty && !value.trim()) || value.length > maxLength || busy || !!running || sendDisabled;
  const send = async () => { if (cannotSend) return; if (await onSend(value.trim(),context ? [] : sources)) { sessionStorage.removeItem(draftId); setValue(''); setSources([]); } };
  return <div className="composer-wrap">{!human && <Materials availableFolders={folders} folders={context?.mounted_folders} resources={materials} available={context?.available || documents} busy={busy} pending={pendingContext} onToggle={toggle} onFolder={context ? onFolder : undefined} onOpen={onResource} />}<div className="composer" aria-busy={busy}>
    {accessory}
    <Textarea aria-label={inputLabel || (human ? '回复本人' : '输入协作请求')} placeholder={placeholder || (human ? '回复你的判断或补充信息…' : '输入问题或交代一件事…')} value={value} disabled={busy} maxLength={maxLength}
      onChange={event=>setValue(event.target.value)} onKeyDown={event=> { if (event.key==='Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); } }} />
    {error && <p className="composer-error" role="alert">{error}</p>}
    <div className="composer-toolbar"><span className="composer-audience">{audience || (human ? '本人会话' : workspace)}</span><div className="composer-right">{!human && <span className="composer-mode">{model}</span>}{running ? <Button size="icon" variant="secondary" aria-label="停止生成" onClick={onStop} disabled={busy}><span className="stop-glyph" /></Button> : <Button className={`send-button${sendLabel ? ' send-action' : ''}`} size={sendLabel ? 'sm' : 'icon'} aria-label={sendLabel || '发送消息'} disabled={cannotSend} onClick={()=>void send()}>{busy ? <LoadingIcon /> : sendLabel || <ArrowRightIcon className="send-arrow" />}</Button>}</div></div>
    <div className="composer-context"><span>{contextLabel || (human ? '协作参与者可见' : workspace)}</span>{!contextLabel && <span>{human ? '回复会直接送达对方' : materials.length ? `${materials.length} 份可用资料` : '未附加资料'}</span>}</div>
  </div><div className="composer-hint"><span>{running ? '回答正在生成，关闭页面后仍会继续' : '草稿暂存于当前浏览器标签页'}</span><span>Enter 发送 · Shift Enter 换行</span></div></div>;
}
