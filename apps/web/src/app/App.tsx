import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { Button, TooltipProvider } from '@tutti-os/ui-system';
import { AddIcon, CloseIcon, GridRightLinedIcon, LayoutMenuIcon, LoadingIcon, SettingsIcon } from '@tutti-os/ui-system/icons';
import { api, ApiError, command, setAccountScope, type AuthStatus, type Document, type State, type Task, type ThreadData, type Thread, type Folder, type ResourceRef } from '../shared/api';
import { IconButton, Pending } from '../shared/ui';
import { usePresence } from '../features/chat/usePresence';
import { ChatLobby } from '../features/chat/ChatList';
import { AuthScreen } from '../features/auth/AuthScreen';
import { Conversation } from '../features/workspace/Conversation';
import { Sidebar } from '../features/workspace/Sidebar';
import { route, viewTitles, type View } from '../shared/routes';
import { FolderPage } from '../features/workspace/FolderPage';
import { ResourceLibrary } from '../features/workspace/ResourceLibrary';
import { TopicList } from '../features/topics/TopicList';
import { TopicPage } from '../features/topics/TopicPage';
import { proposalDraftKey } from '../features/topics/types';
import { ContextPanel, Lists } from '../features/workspace/Panels';
import { Dialogs, type Modal } from '../features/workspace/Dialogs';
const Gallery = lazy(() => import('../features/gallery/Gallery').then(module => ({ default: module.Gallery })));

export function App() {
  const [state,setState] = useState<State | null>(null);
  const [authStatus,setAuthStatus] = useState<AuthStatus | null>(null);
  const [boot,setBoot] = useState(true);
  const [threadId,setThreadId] = useState<string | null>(['workspace','chat'].includes(route().view) ? route().id : null);
  const selected = useRef(threadId);
  const accountId = useRef('');
  const pendingThread = useRef<string | null>(null);
  const [data,setData] = useState<ThreadData | null>(null);
  const [view,setView] = useState<View>(route().view);
  const [routeId,setRouteId]=useState(route().id); const [section,setSection]=useState(route().section);
  const [undoMove,setUndoMove]=useState<{threadId:string;folderId:string;version:number;label:string} | null>(null);
  const [busy,setBusy] = useState(false); const busyRef = useRef(false);
  const [loading,setLoading] = useState(false);
  const [error,setError] = useState(''); const [modal,setModal] = useState<Modal | null>(null);
  const [theme,setTheme] = useState(localStorage.getItem('accord.theme') || 'dark');
  const [mobileNav,setMobileNav] = useState(false);
  const [nav,setNav] = useState(localStorage.getItem('accord.nav') !== 'closed');
  const [context,setContext] = useState(localStorage.getItem('accord.context') === 'open');
  const [query,setQuery] = useState(''); const [draftKey,setDraftKey] = useState(0);
  useEffect(() => { document.documentElement.dataset.theme=theme; localStorage.setItem('accord.theme',theme); },[theme]);
  useEffect(() => { localStorage.setItem('accord.context',context ? 'open' : 'closed'); },[context]);
  useEffect(() => { localStorage.setItem('accord.nav',nav ? 'open' : 'closed'); },[nav]);
  const syncRoute = useCallback(() => { const next=route(); selected.current=['workspace','chat'].includes(next.view) ? next.id : null; setThreadId(selected.current); setRouteId(next.id); setSection(next.section); setView(next.view); setMobileNav(false); },[]);
  useEffect(() => { window.addEventListener('hashchange',syncRoute); return () => window.removeEventListener('hashchange',syncRoute); },[syncRoute]);
  const navigate = (next: View, id: string | null = null, section='') => { location.hash = next + (id ? '/' + encodeURIComponent(id) : '') + (section ? '/'+section : ''); syncRoute(); };
  const selectThread = (id: string) => {
    const known=state?.threads.find(thread=>thread.id===id);
    if (known) navigate(known.kind==='peer' ? 'chat' : 'workspace',id);
    else void api<ThreadData>(`/threads/${id}`).then(result=>navigate(result.thread.kind==='peer' ? 'chat' : 'workspace',id)).catch(error=>setError(error.message));
  };
  const newWorkspace = useCallback(() => {
    if (accountId.current) { sessionStorage.removeItem(`accord.draft.${accountId.current}.new`); sessionStorage.removeItem(`accord.draft.${accountId.current}.new.sources`); }
    pendingThread.current=null; selected.current=null; setThreadId(null); setData(null); setRouteId(null); setSection(''); setView('workspace'); location.hash='workspace'; setMobileNav(false);
    setDraftKey(k=>k+1);
  },[]);
  const clearSession = useCallback(() => { setState(null); setData(null); setModal(null); selected.current=null; setThreadId(null); setUndoMove(null); setAccountScope(''); },[]);
  useEffect(() => {
    const expired = () => { clearSession(); void api<AuthStatus>('/auth/status').then(setAuthStatus); };
    window.addEventListener('accord:auth-expired',expired); return () => window.removeEventListener('accord:auth-expired',expired);
  },[clearSession]);
  const refresh = useCallback(async (signal?: AbortSignal) => {
    const next = await api<State>('/state',undefined,signal);
    if (signal?.aborted) return;
    accountId.current=next.me; setAccountScope(next.me); setState(next);
    const id = selected.current;
    if (id) {
      try { const result = await api<ThreadData>(`/threads/${id}?person_history=true`,undefined,signal); if (!signal?.aborted && selected.current===id) setData(result); }
      catch (error) { if (error instanceof ApiError && error.status===404) newWorkspace(); throw error; }
    }
  },[newWorkspace]);
  const load = useCallback(async () => {
    setError('');
    try { setAuthStatus(await api<AuthStatus>('/auth/status')); await refresh(); }
    catch (error) { if (!(error instanceof ApiError && error.status===401)) setError((error as Error).message); }
    finally { setBoot(false); }
  },[refresh]);
  useEffect(() => { sessionStorage.removeItem('accord.session'); sessionStorage.removeItem('accord.thread'); void load(); },[load]);
  const signedIn = !!state;
  usePresence(state,threadId,view==='chat');
  useEffect(() => {
    if (!signedIn) return;
    const controller = new AbortController(); let polling=false;
    setData(null); setLoading(!!threadId);
    const update = async () => {
      if (polling) return; polling=true;
      try { await refresh(controller.signal); }
      catch (error) { if (!controller.signal.aborted && !(error instanceof ApiError && error.status===401)) setError((error as Error).message); }
      finally { polling=false; if (!controller.signal.aborted) setLoading(false); }
    };
    void update();
    const timer = setInterval(() => { if (!document.hidden) void update(); },1000);
    return () => { controller.abort(); clearInterval(timer); };
  },[signedIn,refresh,threadId]);
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase()==='k') { event.preventDefault(); newWorkspace(); }
      if (event.key==='Escape') setMobileNav(false);
    };
    window.addEventListener('keydown',handler); return () => window.removeEventListener('keydown',handler);
  },[newWorkspace]);
  const perform = async (path: string, body: Record<string,unknown>) => {
    if (busyRef.current) return false;
    busyRef.current=true; setBusy(true); setError('');
    try {
      await command(path,body);
      try { await refresh(); } catch { setError('操作已保存，页面同步暂时中断，请重新连接。'); }
      return true;
    }
    catch (error) { setError((error as Error).message); return false; }
    finally { busyRef.current=false; setBusy(false); }
  };
  const openMember = async (id: string, folderId='', sourceIds:string[]=[], newItem=false) => {
    if (busyRef.current) return; busyRef.current=true; setBusy(true); setError('');
    try { const peer=id!==state?.me; const result = await command<{id:string}>(peer ? '/chats/open' : '/threads',peer ? {target_id:id,new_item:newItem} : {target_id:id,folder_id:folderId,source_ids:sourceIds}); navigate(peer ? 'chat' : 'workspace',result.id); }
    catch (error) { setError((error as Error).message); } finally { busyRef.current=false; setBusy(false); }
  };
  const send = async (body: string, sourceIds: string[]) => {
    if (!state || busyRef.current) return false;
    busyRef.current=true; setBusy(true); setError('');
    try {
      let id = selected.current || pendingThread.current;
      if (!id) { const result=await command<{id:string}>('/threads',{target_id:state.me}); id=result.id; pendingThread.current=id; }
      await command(`/threads/${id}/messages`,{body,source_ids:sourceIds});
      pendingThread.current=null; if (selected.current!==id) selectThread(id);
      try { await refresh(); } catch { setError('消息已保存，页面同步暂时中断，请重新连接。'); }
      return true;
    } catch (error) { setError((error as Error).message); return false; } finally { busyRef.current=false; setBusy(false); }
  };
  const logout = async () => {
    try { await api('/auth/logout',{}); clearSession(); newWorkspace(); setAuthStatus(await api<AuthStatus>('/auth/status')); setError(''); }
    catch (error) { setError((error as Error).message); }
  };
  const doc = (document: Document) => setModal({kind:'document',document});
  const openResource=(resource:ResourceRef)=> { void api<Document>(`/resources/${resource.id}${resource.version ? '?version='+resource.version : ''}`).then(doc).catch(error=>setError(error.message)); };
  const moveThread=async(thread:Thread,folderId:string)=> {
    if (await perform(`/threads/${thread.id}/move`,{folder_id:folderId,expected_version:thread.placement_version})) setUndoMove({threadId:thread.id,folderId:thread.folder_id,version:thread.placement_version+1,label:state?.folders.find(folder=>folder.id===folderId)?.name || '未分类'});
  };
  const folderMaterial=(folder:Folder,resourceId:string,selected=true)=> {
    const included=selected ? [...new Set([...folder.binding.included,resourceId])] : folder.binding.included.filter(id=>id!==resourceId);
    void perform(`/folders/${folder.id}/bindings`,{included,excluded:[],expected_version:folder.binding.version});
  };
  const bindMaterial=(resourceId:string,enabled:boolean)=> {
    if (!data || (enabled && data.context.resources.some(resource=>resource.id===resourceId))) return;
    const current=data.context.binding;
    const included=enabled ? [...new Set([...current.included,resourceId])] : current.included.filter(id=>id!==resourceId);
    const excluded=enabled ? current.excluded.filter(id=>id!==resourceId) : [...new Set([...current.excluded,resourceId])];
    void perform(`/threads/${data.thread.id}/bindings`,{included,excluded,expected_version:current.version});
  };
  const bindFolder=(folderId:string,enabled=true)=> {
    if (!data) { setError('请先新建聊天，再加入文件夹资料。'); return; }
    const current=data.context.binding;
    const folder_ids=enabled ? [...new Set([...(current.folder_ids || []),folderId])] : (current.folder_ids || []).filter(id=>id!==folderId);
    void perform(`/threads/${data.thread.id}/bindings`,{included:current.included,excluded:current.excluded,folder_ids,expected_version:current.version});
  };
  const submitDraft=(roundId:string,body:string)=> { if (!state) return; sessionStorage.setItem(proposalDraftKey(state.me,roundId),JSON.stringify({title:'',body,sources:[]})); navigate('topics',roundId,'submit'); };
  const folder=state?.folders.find(folder=>folder.id===routeId);

  const task = (item: Task) => { void perform(`/tasks/${item.id}/status`,{status:item.status==='done' ? 'open' : 'done'}); };
  const toggleNav = () => { if (window.matchMedia('(max-width:760px)').matches) setMobileNav(v=>!v); else setNav(v=>!v); };
  return <TooltipProvider delayDuration={300}>
    {boot ? <main className="boot-screen"><Pending /></main> : !state ? authStatus ? <AuthScreen status={authStatus} onLogin={async () => { newWorkspace(); await load(); }} /> : <main className="boot-screen"><div role="alert"><p>{error || '暂时无法连接工作空间'}</p><Button onClick={() => void load()}>重新连接</Button></div></main> : <div className="app-shell"><div className="workbench">
      <header className="workbench-header"><div className="breadcrumb"><IconButton label="切换导航" onClick={toggleNav} active={window.matchMedia('(max-width:760px)').matches ? mobileNav : nav}><LayoutMenuIcon /></IconButton><span className="workspace-name">{state.project.name}</span><span className="breadcrumb-slash">/</span><strong>{view==='chat' && data ? state.members.find(member=>member.id===(data.thread.owner_id===state.me ? data.thread.target_id : data.thread.owner_id))?.person_name || '聊天' : view==='workspace' && data ? data.thread.title : view==='folder' && folder ? folder.name : view==='topics' && routeId ? state.topics.find(topic=>topic.id===routeId)?.title || '课题' : viewTitles[view]}</strong></div>
        <div className="header-actions"><IconButton label="新建协作" onClick={newWorkspace}><AddIcon /></IconButton><span className="context-toggle"><IconButton label="切换协作上下文" active={context} onClick={() => setContext(!context)}><GridRightLinedIcon /></IconButton></span><IconButton label="工作空间设置" onClick={() => setModal({kind:'settings'})}><SettingsIcon /></IconButton></div>
      </header>
      {error && <div className="error-banner" role="alert"><span>{error}</span><Button variant="ghost" size="sm" onClick={() => { void refresh().then(()=>setError('')).catch(error=>setError(error.message)); }}>重新连接</Button><Button variant="ghost" size="icon-xs" aria-label="关闭提示" onClick={() => setError('')}><CloseIcon /></Button></div>}
      <div className="workspace-body">
        <Sidebar state={state} view={view} setView={v=>v==='workspace' ? newWorkspace() : navigate(v)} selected={threadId} selectThread={selectThread} newThread={newWorkspace} query={query} setQuery={setQuery} settings={() => setModal({kind:'settings'})} open={mobileNav} collapsed={!nav} close={() => setMobileNav(false)} busy={busy} onAction={perform} onMove={(thread,folderId)=>void moveThread(thread,folderId)} onFolder={id=>navigate('folder',id)} onFolderMaterial={folderMaterial} onMember={id=>void openMember(id)} />
        <main className="main-surface" id="main-content" inert={mobileNav}>{view==='gallery' && import.meta.env.DEV ? <Suspense fallback={<Pending />}><Gallery /></Suspense> : view==='chat' && !threadId ? <ChatLobby state={state} onMember={id=>void openMember(id)} onInvite={()=>setModal({kind:'settings'})} /> : ['workspace','chat'].includes(view) ? <Conversation state={state} data={data} loading={loading} busy={busy} onSend={send} onHandoff={() => data && setModal({kind:'handoff',thread:data.thread})} onConfirm={() => data && setModal({kind:'confirm',thread:data.thread})} onDocument={doc} onNew={newWorkspace} draftKey={draftKey} onRun={(id,action)=>void perform(`/runs/${id}/${action}`,{})} onResource={openResource} onBind={bindMaterial} onFolder={bindFolder} onRefresh={refresh} onOpen={selectThread} onTopic={id=>navigate('topics',id)} onSubmission={submitDraft} onNewChatItem={id=>void openMember(id,'',[],true)} /> : view==='folder' ? <FolderPage folder={folder} state={state} busy={busy} onNew={()=>void openMember(state.me,routeId || '')} onThread={selectThread} onBind={(id,enabled)=>folder && folderMaterial(folder,id,enabled)} onResource={openResource} /> : view==='library' ? <ResourceLibrary state={state} onRefresh={refresh} onResource={openResource} onUse={id=>void openMember(state.me,'',[id])} /> : view==='topics' ? routeId ? <TopicPage key={state.me+routeId} id={routeId} section={section} state={state} onBack={()=>navigate('topics')} onThread={selectThread} onRefresh={refresh} onResource={openResource} /> : <TopicList state={state} onTopic={id=>navigate('topics',id)} onRefresh={refresh} /> : <Lists view={view} state={state} busy={busy} onMember={id=>void openMember(id)} onThread={selectThread} onDocument={doc} onPublish={() => setModal({kind:'publish'})} onSettings={()=>setModal({kind:'settings'})} onTask={task} />}</main>
        {context && ['workspace','chat'].includes(view) && <ContextPanel state={state} data={data} onDocument={openResource} onThread={selectThread} />}
      </div>
      {undoMove && <div className="operation-toast" role="status"><span>已移动到 {undoMove.label}</span><Button variant="ghost" size="xs" disabled={busy} onClick={()=>void perform(`/threads/${undoMove.threadId}/move`,{folder_id:undoMove.folderId,expected_version:undoMove.version}).then(ok=>ok && setUndoMove(null))}>撤销</Button><Button variant="ghost" size="icon-xs" aria-label="关闭移动提示" onClick={()=>setUndoMove(null)}><CloseIcon /></Button></div>}
      <footer className="workbench-footer"><span>{state.model.label}</span><span>{busy && <LoadingIcon size={12} />}{busy ? '正在保存' : error ? '连接需要恢复' : '已连接工作空间'}</span></footer>
    </div><Dialogs modal={modal} close={() => setModal(null)} state={state} busy={busy} submit={perform} theme={theme} setTheme={setTheme} logout={()=>void logout()} /></div>}
  </TooltipProvider>;
}
