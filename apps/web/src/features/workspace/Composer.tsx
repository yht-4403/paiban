import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Button, Textarea } from '@tutti-os/ui-system';
import { ArrowRightIcon, CloseIcon, FileTextIcon, LoadingIcon, UploadIcon } from '@tutti-os/ui-system/icons';
import type { Document, ThreadContext, ResourceRef, ProcessAttachmentInput } from '../../shared/api';
import { Materials } from './Materials';
import { useTutorialAction } from '../tutorial/bridge';

export function Composer({ folders, documents, onSend, busy, human=false, running, onStop, draftId, model, workspace, context, onBind, onFolder, onResource, pendingContext, initialValue='', allowEmpty=false, sendDisabled=false, sendLabel, inputLabel, placeholder, maxLength=8000, audience, contextLabel, accessory, error, onMention, allowAttachments=false }: {
  folders?: {id:string;name:string}[]; documents: Document[]; onSend: (body: string, sourceIds: string[], attachments?: ProcessAttachmentInput[]) => Promise<boolean>; busy: boolean; human?: boolean;
  context?: ThreadContext; onBind?: (id: string, selected: boolean) => void; onFolder?: (id: string, selected?: boolean) => void; onResource: (resource: ResourceRef) => void; pendingContext?: boolean;
  running?: boolean; onStop: () => void; draftId: string; model: string; workspace: string;
  initialValue?: string; allowEmpty?: boolean; sendDisabled?: boolean; sendLabel?: string; inputLabel?: string; placeholder?: string;
  maxLength?: number; audience?: string; contextLabel?: string; accessory?: ReactNode; error?: string; onMention?: () => void; allowAttachments?: boolean;
}) {
  const [value,setValue] = useState(() => sessionStorage.getItem(draftId) ?? initialValue);
  const [sources,setSources] = useState<string[]>(()=> { try { return JSON.parse(sessionStorage.getItem(draftId+'.sources') || '[]'); } catch { return []; } });
  const [attachments,setAttachments] = useState<ProcessAttachmentInput[]>(()=> { try { return JSON.parse(sessionStorage.getItem(draftId+'.attachments') || '[]'); } catch { return []; } });
  const [tutorialExpected,setTutorialExpected]=useState<{value:string;sourceIds:string[]}|null>(null);
  const [attachmentError,setAttachmentError]=useState(''); const [dragging,setDragging]=useState(false); const fileInput=useRef<HTMLInputElement>(null);
  useEffect(()=> { if(sources.length)sessionStorage.setItem(draftId+'.sources',JSON.stringify(sources));else sessionStorage.removeItem(draftId+'.sources'); },[sources,draftId]);
  useEffect(()=> { try { if(attachments.length)sessionStorage.setItem(draftId+'.attachments',JSON.stringify(attachments));else sessionStorage.removeItem(draftId+'.attachments'); } catch { setAttachmentError('附件草稿无法在浏览器中继续保存。'); } },[attachments,draftId]);
  const materials=context?.resources || documents.filter(document=>sources.includes(document.id));
  const toggle=(id:string,selected:boolean)=> { if (context && onBind) onBind(id,selected); else setSources(items=>selected ? [...new Set([...items,id])] : items.filter(item=>item!==id)); };
  useEffect(() => { if(value)sessionStorage.setItem(draftId,value);else sessionStorage.removeItem(draftId); },[draftId,value]);
  useEffect(() => {
    const insert = (event: Event) => {
      const text = (event as CustomEvent<string>).detail;
      if (typeof text === 'string' && text.trim()) setValue(current => current ? `${current}\n\n${text}` : text);
    };
    window.addEventListener('accord:insert-text', insert);
    return () => window.removeEventListener('accord:insert-text', insert);
  }, []);
  useEffect(() => {
    if (context || human) return;
    const select = (event: Event) => {
      const id = (event as CustomEvent<string>).detail;
      if (documents.some(document=>document.id===id)) setSources(items=>[...new Set([...items,id])].slice(0,20));
    };
    window.addEventListener('accord:select-resource',select);
    return () => window.removeEventListener('accord:select-resource',select);
  },[context,human,documents]);
  useEffect(()=>{const release=()=>setTutorialExpected(null);window.addEventListener('accord:tutorial-release',release);return()=>window.removeEventListener('accord:tutorial-release',release);},[]);
  const addFiles=async(files:File[])=>{
    setAttachmentError('');if(!allowAttachments||!files.length)return;
    const next=[...attachments];
    const textExtensions=new Set(['md','markdown','txt','csv','json','yaml','yml','log','ts','tsx','js','jsx','py','html','css']);
    const binaryExtensions=new Set(['png','jpg','jpeg','gif','webp','pdf','doc','docx','ppt','pptx','xls','xlsx']);
    const asDataUrl=(file:File)=>new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>typeof reader.result==='string'?resolve(reader.result):reject(new Error('附件读取失败。'));reader.onerror=()=>reject(new Error('附件读取失败。'));reader.readAsDataURL(file);});
    for(const file of files){
      if(next.length>=5){setAttachmentError('一次最多加入 5 个附件。');break;}
      const ext=file.name.split('.').pop()?.toLowerCase()||'';
      const isText=file.type.startsWith('text/')||textExtensions.has(ext);
      if(!isText&&!file.type.startsWith('image/')&&!binaryExtensions.has(ext)){setAttachmentError(`${file.name} 暂不支持。`);continue;}
      if(file.size>(isText?256000:1000000)){setAttachmentError(`${file.name} 超过 ${isText?'256 KB':'1 MB'}。`);continue;}
      const mime=file.type||({pdf:'application/pdf',doc:'application/msword',docx:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',ppt:'application/vnd.ms-powerpoint',pptx:'application/vnd.openxmlformats-officedocument.presentationml.presentation',xls:'application/vnd.ms-excel',xlsx:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'} as Record<string,string>)[ext]||'application/octet-stream';
      const content=isText?await file.text():await asDataUrl(file);
      if(!content.trim()){setAttachmentError(`${file.name} 没有可读取的内容。`);continue;}
      const textTotal=next.filter(item=>item.mime_type.startsWith('text/')||textExtensions.has(item.filename.split('.').pop()?.toLowerCase()||'')).reduce((sum,item)=>sum+item.content.length,0)+(isText?content.length:0);
      if(textTotal>64000){setAttachmentError('文字附件总内容不能超过 64,000 个字符。');break;}
      if(next.reduce((sum,item)=>sum+item.content.length,0)+content.length>4200000){setAttachmentError('附件总大小不能超过 3 MB。');break;}
      next.push({filename:file.name||`粘贴的图片.${ext||'png'}`,content,mime_type:mime});
    }
    setAttachments(next);
  };
  const cannotSend = (!allowEmpty && !value.trim() && !attachments.length) || value.length > maxLength || busy || !!running || sendDisabled;
  const clearDraft=()=>{sessionStorage.removeItem(draftId);sessionStorage.removeItem(draftId+'.sources');sessionStorage.removeItem(draftId+'.attachments');setValue('');setSources([]);setAttachments([]);};
  const send = async () => { if (cannotSend||tutorialExpected) return false; const sent=await onSend(value.trim(),context ? [] : sources,attachments); if (sent) clearDraft(); return sent; };
  useTutorialAction('composer.fill', payload => {
    if (payload.draftId !== draftId) throw new Error('演练对话仍在载入，请稍后重试。');
    setTutorialExpected({value:payload.value,sourceIds:[...payload.sourceIds]});
    setValue(payload.value);
    sessionStorage.setItem(draftId,payload.value);
    return true;
  });
  useTutorialAction('composer.send', async payload => {
    if (payload.draftId !== draftId) throw new Error('演练对话已经变化，请返回当前步骤重试。');
    if(!tutorialExpected||tutorialExpected.value!==payload.expectedValue||tutorialExpected.sourceIds.length!==payload.sourceIds.length||tutorialExpected.sourceIds.some((id,index)=>id!==payload.sourceIds[index]))throw new Error('演练输入状态已经变化，请重试当前步骤。');
    if (value !== payload.expectedValue) throw new Error('固定演练问题已被修改。请重试当前步骤，恢复预填内容后再发送。');
    if (attachments.length) throw new Error('固定演练问题不包含附件。请移除附件后重试。');
    const sourceIds=[...new Set(payload.sourceIds)];
    if(sourceIds.length!==payload.sourceIds.length||sourceIds.some(id=>!documents.some(document=>document.id===id)))throw new Error('演练指定的共享资料没有完整载入，请稍后重试。');
    if (cannotSend) throw new Error(running ? 'Agent 仍在回答，请等待完成。' : busy ? '当前操作仍在保存，请稍后重试。' : '请先确认输入框内的演练问题。');
    if (!await onSend(payload.expectedValue,sourceIds,[])) throw new Error('消息没有发送，请查看页面提示后重试。');
    setTutorialExpected(null);
    clearDraft();
    return true;
  });
  return <div className="composer-wrap" data-tour="composer">{!human && (!!materials.length || !!context?.mounted_folders?.length) && <Materials automatic={false} availableFolders={folders} folders={context?.mounted_folders} resources={materials} available={context?.available || documents} busy={busy} pending={pendingContext} onToggle={toggle} onFolder={context ? onFolder : undefined} onOpen={onResource} />}<div className={`composer ${dragging?'drop-active':''}`} aria-busy={busy}
    onDragOver={event=>{if(allowAttachments&&event.dataTransfer.types.includes('Files')){event.preventDefault();setDragging(true);}}} onDragLeave={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node))setDragging(false);}} onDrop={event=>{if(allowAttachments&&event.dataTransfer.files.length){event.preventDefault();setDragging(false);void addFiles(Array.from(event.dataTransfer.files));}}}>
    {accessory}
    {!!attachments.length&&<div className="composer-attachments">{attachments.map((item,index)=><span key={item.filename+index}><FileTextIcon size={13}/><strong>{item.filename}</strong><Button variant="ghost" size="icon-xs" aria-label={`移除附件：${item.filename}`} onClick={()=>setAttachments(items=>items.filter((_,i)=>i!==index))}><CloseIcon/></Button></span>)}</div>}
    <Textarea data-tour="composer-input" aria-label={inputLabel || (human ? '回复本人' : '输入协作请求')} placeholder={placeholder || (human ? '回复…' : '输入消息…')} value={value} disabled={busy} maxLength={maxLength}
      onPaste={event=>{if(allowAttachments&&event.clipboardData.files.length){event.preventDefault();void addFiles(Array.from(event.clipboardData.files));}}} onChange={event=>setValue(event.target.value)} onKeyDown={event=> { if (onMention && event.key==='@' && !event.nativeEvent.isComposing && (event.currentTarget.selectionStart===0 || /\s/.test(value[event.currentTarget.selectionStart-1]))) { event.preventDefault(); onMention(); return; } if (event.key==='Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); } }} />
    {(error||attachmentError) && <p className="composer-error" role="alert">{error||attachmentError}</p>}
    <div className="composer-toolbar"><div className="composer-left">{allowAttachments&&<><input ref={fileInput} className="visually-hidden" type="file" multiple accept="text/*,image/*,.md,.csv,.json,.yaml,.yml,.log,.ts,.tsx,.js,.jsx,.py,.html,.css,.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx" onChange={event=>{void addFiles(Array.from(event.target.files||[]));event.currentTarget.value='';}}/><Button variant="ghost" size="icon-xs" aria-label="加入本轮附件" title="加入本轮附件" onClick={()=>fileInput.current?.click()}><UploadIcon/></Button></>}<span className="composer-audience">{audience || (human ? '本人会话' : workspace)}</span></div><div className="composer-right">{!human && <span className="composer-mode">{model}</span>}{running ? <Button size="icon" variant="secondary" aria-label="停止生成" onClick={onStop} disabled={busy}><span className="stop-glyph" /></Button> : <Button data-tour="composer-send" className={`send-button${sendLabel ? ' send-action' : ''}`} size={sendLabel ? 'sm' : 'icon'} title={sendLabel || '发送 · Enter（Shift+Enter 换行）'} aria-label={sendLabel || '发送消息'} disabled={cannotSend||!!tutorialExpected} onClick={()=>void send()}>{busy ? <LoadingIcon /> : sendLabel || <ArrowRightIcon className="send-arrow" />}</Button>}</div></div>
    {contextLabel && <div className="composer-context"><span>{contextLabel}</span></div>}
  </div></div>;
}
