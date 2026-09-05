import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  Button,
  Popover,
  PopoverContent,
  PopoverTrigger,
  Slider,
  Textarea,
} from '@tutti-os/ui-system';
import {
  ArrowRightIcon,
  CheckIcon,
  ChevronDownIcon,
  CloseIcon,
  FileCodeIcon,
  FileIcon,
  FileTextIcon,
  ImageFileIcon,
  LoadingIcon,
  ThinkingIcon,
  UploadIcon,
} from '@tutti-os/ui-system/icons';
import {
  reasoningLabels,
  type Document,
  type ProcessAttachmentInput,
  type ReasoningEffort,
  type ResourceRef,
  type State,
  type ThreadContext,
} from '../../shared/api';
import { Materials } from './Materials';
import { useTutorialAction } from '../tutorial/bridge';

const TEXT_EXTENSIONS = new Set([
  'md', 'markdown', 'txt', 'csv', 'json', 'yaml', 'yml', 'log',
  'ts', 'tsx', 'js', 'jsx', 'py', 'html', 'css',
]);
const BINARY_EXTENSIONS = new Set([
  'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'doc', 'docx',
  'ppt', 'pptx', 'xls', 'xlsx',
]);
const MAX_BINARY_BYTES = 8_000_000;
const MAX_TOTAL_CONTENT_LENGTH = 28_000_000;

const extensionOf = (filename: string) => filename.split('.').pop()?.toLowerCase() || '';
const isReadableAttachment = (item: ProcessAttachmentInput) =>
  item.mime_type.startsWith('text/') || TEXT_EXTENSIONS.has(extensionOf(item.filename));
const isImageAttachment = (item: ProcessAttachmentInput) => item.mime_type.startsWith('image/');

function attachmentSize(item: ProcessAttachmentInput) {
  if (!item.content.startsWith('data:')) return new Blob([item.content]).size;
  const encoded = item.content.split(',', 2)[1] || '';
  const padding = encoded.endsWith('==') ? 2 : encoded.endsWith('=') ? 1 : 0;
  return Math.max(0, Math.floor(encoded.length * 3 / 4) - padding);
}

function sizeLabel(bytes: number) {
  if (bytes < 1000) return `${bytes} B`;
  if (bytes < 1_000_000) return `${Math.round(bytes / 1000)} KB`;
  return `${(bytes / 1_000_000).toFixed(1)} MB`;
}

function kindLabel(item: ProcessAttachmentInput) {
  const extension = extensionOf(item.filename);
  if (isImageAttachment(item)) return '图片';
  if (extension === 'pdf') return 'PDF';
  if (['doc', 'docx'].includes(extension)) return 'Word';
  if (['ppt', 'pptx'].includes(extension)) return 'PowerPoint';
  if (['xls', 'xlsx'].includes(extension)) return 'Excel';
  if (TEXT_EXTENSIONS.has(extension)) return extension ? extension.toUpperCase() : '文本';
  return extension ? extension.toUpperCase() : '文件';
}

function AttachmentIcon({ item }: { item: ProcessAttachmentInput }) {
  const extension = extensionOf(item.filename);
  if (isImageAttachment(item)) return <ImageFileIcon size={22} />;
  if (['ts', 'tsx', 'js', 'jsx', 'py', 'html', 'css', 'json'].includes(extension)) {
    return <FileCodeIcon size={22} />;
  }
  if (isReadableAttachment(item) || ['pdf', 'doc', 'docx', 'ppt', 'pptx'].includes(extension)) {
    return <FileTextIcon size={22} />;
  }
  return <FileIcon size={22} />;
}

function PendingAttachment({ item, onRemove }: {
  item: ProcessAttachmentInput;
  onRemove: () => void;
}) {
  const image = isImageAttachment(item);
  const openImage = () => {
    if (!image) return;
    const link = document.createElement('a');
    link.href = item.content;
    link.target = '_blank';
    link.rel = 'noopener';
    link.click();
  };
  return <div className={`composer-attachment ${image ? 'is-image' : 'is-file'}`} role="listitem">
    {image
      ? <button className="composer-attachment-preview" type="button" onClick={openImage} aria-label={`预览图片：${item.filename}`}><img src={item.content} alt="" /></button>
      : <div className="composer-attachment-icon" aria-hidden="true"><AttachmentIcon item={item} /></div>}
    {!image && <div className="composer-attachment-meta"><strong title={item.filename}>{item.filename}</strong><small>{kindLabel(item)} · {sizeLabel(attachmentSize(item))}</small></div>}
    <Button className="composer-attachment-remove" variant="ghost" size="icon-xs" aria-label={`移除附件：${item.filename}`} title="移除" onClick={onRemove}><CloseIcon /></Button>
  </div>;
}

function ModelControl({ settings, fallback, busy, onPreference, onError }: {
  settings?: State['model'];
  fallback: string;
  busy: boolean;
  onPreference?: (path: string, body: Record<string, unknown>) => Promise<boolean>;
  onError: (message: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const efforts = settings?.reasoning_options || [];
  const selectedIndex = Math.max(0, efforts.indexOf(settings?.reasoning_effort || 'max'));
  const [effortIndex, setEffortIndex] = useState(selectedIndex);
  useEffect(() => setEffortIndex(selectedIndex), [selectedIndex]);
  if (!settings || !onPreference || settings.mode !== 'model') {
    return <span className="composer-mode">{fallback}</span>;
  }
  const saveEffort = async (index: number) => {
    const effort = efforts[index] as ReasoningEffort | undefined;
    if (!effort || effort === settings.reasoning_effort) return;
    onError('');
    if (!await onPreference('/profile/reasoning', { reasoning_effort: effort })) {
      setEffortIndex(selectedIndex);
      onError('思考强度没有保存，请重试。');
    }
  };
  const chooseModel = async (model: string) => {
    if (model === settings.selected_model) return;
    onError('');
    if (await onPreference('/profile/model', { model })) setOpen(false);
    else onError('模型没有切换，请重试。');
  };
  return <Popover open={open} onOpenChange={setOpen}>
    <PopoverTrigger asChild>
      <button className="composer-model-trigger" type="button" disabled={busy} aria-label={`模型：${settings.label}，思考强度：${reasoningLabels[settings.reasoning_effort]}`}>
        <ThinkingIcon size={15} /><span>{settings.label}</span>{efforts.length > 0 && <small>{reasoningLabels[settings.reasoning_effort]}</small>}<ChevronDownIcon size={13} />
      </button>
    </PopoverTrigger>
    <PopoverContent className="composer-model-popover" align="end" side="top" sideOffset={8}>
      <section>
        <span className="composer-popover-label">模型</span>
        <div className="composer-model-options">
          {settings.model_options.map(option => <button key={option.id} type="button" className={option.id === settings.selected_model ? 'selected' : ''} disabled={busy} onClick={() => void chooseModel(option.id)}><span>{option.label}</span>{option.id === settings.selected_model && <CheckIcon size={14} />}</button>)}
        </div>
      </section>
      {efforts.length > 0 && <section className="composer-effort">
        <div><span className="composer-popover-label">思考强度</span><strong>{reasoningLabels[efforts[effortIndex]]}</strong></div>
        <Slider aria-label="思考强度" min={0} max={efforts.length - 1} step={1} value={[effortIndex]} disabled={busy} onValueChange={values => setEffortIndex(values[0] ?? 0)} onValueCommit={values => void saveEffort(values[0] ?? 0)} />
        <div className="composer-effort-labels">{efforts.map((effort, index) => <button key={effort} type="button" className={index === effortIndex ? 'selected' : ''} disabled={busy} onClick={() => { setEffortIndex(index); void saveEffort(index); }}>{reasoningLabels[effort]}</button>)}</div>
      </section>}
    </PopoverContent>
  </Popover>;
}

export function Composer({ folders, documents, onSend, busy, human=false, running, onStop, draftId, model, modelSettings, onPreference, workspace, context, onBind, onFolder, onResource, pendingContext, initialValue='', allowEmpty=false, sendDisabled=false, sendLabel, inputLabel, placeholder, maxLength=8000, audience, contextLabel, accessory, error, onMention, allowAttachments=false }: {
  folders?: {id:string;name:string}[];
  documents: Document[];
  onSend: (body: string, sourceIds: string[], attachments?: ProcessAttachmentInput[]) => Promise<boolean>;
  busy: boolean;
  human?: boolean;
  context?: ThreadContext;
  onBind?: (id: string, selected: boolean) => void;
  onFolder?: (id: string, selected?: boolean) => void;
  onResource: (resource: ResourceRef) => void;
  pendingContext?: boolean;
  running?: boolean;
  onStop: () => void;
  draftId: string;
  model: string;
  modelSettings?: State['model'];
  onPreference?: (path: string, body: Record<string, unknown>) => Promise<boolean>;
  workspace: string;
  initialValue?: string;
  allowEmpty?: boolean;
  sendDisabled?: boolean;
  sendLabel?: string;
  inputLabel?: string;
  placeholder?: string;
  maxLength?: number;
  audience?: string;
  contextLabel?: string;
  accessory?: ReactNode;
  error?: string;
  onMention?: () => void;
  allowAttachments?: boolean;
}) {
  const [value,setValue] = useState(() => sessionStorage.getItem(draftId) ?? initialValue);
  const [sources,setSources] = useState<string[]>(()=> { try { return JSON.parse(sessionStorage.getItem(draftId+'.sources') || '[]'); } catch { return []; } });
  const [attachments,setAttachments] = useState<ProcessAttachmentInput[]>(()=> { try { return JSON.parse(sessionStorage.getItem(draftId+'.attachments') || '[]'); } catch { return []; } });
  const [tutorialExpected,setTutorialExpected]=useState<{value:string;sourceIds:string[]}|null>(null);
  const [attachmentError,setAttachmentError]=useState('');
  const [preferenceError,setPreferenceError]=useState('');
  const [dragging,setDragging]=useState(false);
  const fileInput=useRef<HTMLInputElement>(null);
  useEffect(()=> { if(sources.length)sessionStorage.setItem(draftId+'.sources',JSON.stringify(sources));else sessionStorage.removeItem(draftId+'.sources'); },[sources,draftId]);
  useEffect(()=> {
    try {
      const serialized=JSON.stringify(attachments);
      if(attachments.length && serialized.length<3_000_000)sessionStorage.setItem(draftId+'.attachments',serialized);
      else sessionStorage.removeItem(draftId+'.attachments');
    } catch { sessionStorage.removeItem(draftId+'.attachments'); }
  },[attachments,draftId]);
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
    const asDataUrl=(file:File)=>new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>typeof reader.result==='string'?resolve(reader.result):reject(new Error('附件读取失败。'));reader.onerror=()=>reject(new Error('附件读取失败。'));reader.readAsDataURL(file);});
    for(const file of files){
      if(next.length>=5){setAttachmentError('一次最多加入 5 个附件。');break;}
      const ext=extensionOf(file.name);
      const isText=file.type.startsWith('text/')||TEXT_EXTENSIONS.has(ext);
      if(!isText&&!file.type.startsWith('image/')&&!BINARY_EXTENSIONS.has(ext)){setAttachmentError(`${file.name} 暂不支持。`);continue;}
      if(file.size>(isText?256000:MAX_BINARY_BYTES)){setAttachmentError(`${file.name} 超过 ${isText?'256 KB':'8 MB'}。`);continue;}
      const mime=file.type||({pdf:'application/pdf',doc:'application/msword',docx:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',ppt:'application/vnd.ms-powerpoint',pptx:'application/vnd.openxmlformats-officedocument.presentationml.presentation',xls:'application/vnd.ms-excel',xlsx:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'} as Record<string,string>)[ext]||'application/octet-stream';
      const content=isText?await file.text():await asDataUrl(file);
      if(!content.trim()){setAttachmentError(`${file.name} 没有可读取的内容。`);continue;}
      const textTotal=next.filter(isReadableAttachment).reduce((sum,item)=>sum+item.content.length,0)+(isText?content.length:0);
      if(textTotal>64000){setAttachmentError('文字附件总内容不能超过 64,000 个字符。');break;}
      if(next.reduce((sum,item)=>sum+item.content.length,0)+content.length>MAX_TOTAL_CONTENT_LENGTH){setAttachmentError('附件总大小不能超过 20 MB。');break;}
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
  return <div className="composer-wrap" data-tour="composer">
    {!human && (!!materials.length || !!context?.mounted_folders?.length) && <Materials automatic={false} availableFolders={folders} folders={context?.mounted_folders} resources={materials} available={context?.available || documents} busy={busy} pending={pendingContext} onToggle={toggle} onFolder={context ? onFolder : undefined} onOpen={onResource} />}
    <div className={`composer ${dragging?'drop-active':''}`} aria-busy={busy}
      onDragOver={event=>{if(allowAttachments&&event.dataTransfer.types.includes('Files')){event.preventDefault();setDragging(true);}}}
      onDragLeave={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node))setDragging(false);}}
      onDrop={event=>{if(allowAttachments&&event.dataTransfer.files.length){event.preventDefault();setDragging(false);void addFiles(Array.from(event.dataTransfer.files));}}}>
      {dragging && <div className="composer-drop-hint"><UploadIcon size={18} /><span>放开添加到本轮</span></div>}
      {accessory}
      {!!attachments.length&&<div className="composer-attachments" role="list" aria-label="待发送附件">{attachments.map((item,index)=><PendingAttachment key={item.filename+index} item={item} onRemove={()=>setAttachments(items=>items.filter((_,i)=>i!==index))} />)}</div>}
      <Textarea data-tour="composer-input" aria-label={inputLabel || (human ? '回复本人' : '输入协作请求')} placeholder={placeholder || (human ? '回复…' : '输入消息…')} value={value} disabled={busy} maxLength={maxLength}
        onPaste={event=>{if(allowAttachments&&event.clipboardData.files.length){event.preventDefault();void addFiles(Array.from(event.clipboardData.files));}}}
        onChange={event=>setValue(event.target.value)}
        onKeyDown={event=> { if (onMention && event.key==='@' && !event.nativeEvent.isComposing && (event.currentTarget.selectionStart===0 || /\s/.test(value[event.currentTarget.selectionStart-1]))) { event.preventDefault(); onMention(); return; } if (event.key==='Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); } }} />
      {(error||attachmentError||preferenceError) && <p className="composer-error" role="alert">{error||attachmentError||preferenceError}</p>}
      <div className="composer-toolbar">
        <div className="composer-left">{allowAttachments&&<><input ref={fileInput} className="visually-hidden" type="file" multiple accept="text/*,image/*,.md,.csv,.json,.yaml,.yml,.log,.ts,.tsx,.js,.jsx,.py,.html,.css,.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx" onChange={event=>{void addFiles(Array.from(event.target.files||[]));event.currentTarget.value='';}}/><Button variant="ghost" size="icon-xs" aria-label="加入本轮附件" title="加入本轮附件，也可拖入或粘贴" onClick={()=>fileInput.current?.click()}><UploadIcon/></Button></>}<span className="composer-audience">{audience || (human ? '本人会话' : workspace)}</span></div>
        <div className="composer-right">{!human && <ModelControl settings={modelSettings} fallback={model} busy={busy} onPreference={onPreference} onError={setPreferenceError} />}{running ? <Button size="icon" variant="secondary" aria-label="停止生成" onClick={onStop} disabled={busy}><span className="stop-glyph" /></Button> : <Button data-tour="composer-send" className={`send-button${sendLabel ? ' send-action' : ''}`} size={sendLabel ? 'sm' : 'icon'} title={sendLabel || '发送 · Enter（Shift+Enter 换行）'} aria-label={sendLabel || '发送消息'} disabled={cannotSend||!!tutorialExpected} onClick={()=>void send()}>{busy ? <LoadingIcon /> : sendLabel || <ArrowRightIcon className="send-arrow" />}</Button>}</div>
      </div>
      {contextLabel && <div className="composer-context"><span>{contextLabel}</span></div>}
    </div>
  </div>;
}
