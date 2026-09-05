import { useCallback, useEffect, useState } from 'react';
import { Avatar, Badge, Button, TooltipProvider } from '@tutti-os/ui-system';
import { AddIcon, ArrowRightIcon, CloseIcon, GridRightLinedIcon, LayoutMenuIcon, LoadingIcon, SettingsIcon, ViewGridLinedIcon } from '@tutti-os/ui-system/icons';
import { api, command, type Document, type Member, type State, type Task, type ThreadData } from '../shared/api';
import { IconButton, Pending } from '../shared/ui';
import { Conversation } from '../features/workspace/Conversation';
import { Sidebar, type View } from '../features/workspace/Sidebar';
import { ContextPanel, Lists } from '../features/workspace/Panels';
import { Dialogs, type Modal } from '../features/workspace/Dialogs';
import { Gallery } from '../features/gallery/Gallery';

const viewTitles = {workspace:'我的工作台',people:'找同事',inbox:'待我拍板',tasks:'我的待办',library:'共享成果',gallery:'组件样板'};

export function App() {
  const [token,setToken] = useState(sessionStorage.getItem('accord.session'));
  const [state,setState] = useState<State | null>(null);
  const [members,setMembers] = useState<Member[]>([]);
  const [threadId,setThreadId] = useState<string | null>(sessionStorage.getItem('accord.thread'));
  const [data,setData] = useState<ThreadData | null>(null);
  const [view,setView] = useState<View>(location.hash === '#gallery' ? 'gallery' : 'workspace');
  const [busy,setBusy] = useState(false); const [loading,setLoading] = useState(false);
  const [error,setError] = useState(''); const [modal,setModal] = useState<Modal | null>(null);
  const [theme,setTheme] = useState(localStorage.getItem('accord.theme') || 'dark');
  const [sidebar,setSidebar] = useState(false); const [context,setContext] = useState(true);
  const [query,setQuery] = useState('');
  useEffect(() => { document.documentElement.dataset.theme=theme; localStorage.setItem('accord.theme',theme); },[theme]);
  useEffect(() => { api<{enabled:boolean;members:Member[]}>('/demo').then(d => { setMembers(d.members); if (!d.enabled) setError('演示入口未启用，请按 README 启动本地服务。'); }).catch(e => setError(e.message)); },[]);
  const refresh = useCallback(async (signal?: AbortSignal) => {
    const next = await api<State>('/state',undefined,signal); if (!signal?.aborted) setState(next);
    if (threadId) { const result = await api<ThreadData>(`/threads/${threadId}`,undefined,signal); if (!signal?.aborted) setData(result); }
  },[threadId]);
  useEffect(() => {
    if (!token) return;
    const controller = new AbortController(); setLoading(!!threadId); setData(null);
    void refresh(controller.signal).catch(e => { if (!controller.signal.aborted) setError(e.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    const timer = setInterval(() => { if (!document.hidden) void refresh(controller.signal).catch(e => { if (!controller.signal.aborted) setError('连接暂时中断：'+e.message); }); },3000);
    return () => { controller.abort(); clearInterval(timer); };
  },[token,refresh,threadId]);
  const navigate = (next: View) => { setView(next); location.hash = next === 'gallery' ? 'gallery' : ''; setSidebar(false); };
  const selectThread = (id: string) => { setThreadId(id); sessionStorage.setItem('accord.thread',id); navigate('workspace'); };
  const newWorkspace = useCallback(() => { setThreadId(null); sessionStorage.removeItem('accord.thread'); setData(null); setView('workspace'); location.hash = ''; setSidebar(false); },[]);
  useEffect(() => { const handler = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); newWorkspace(); } }; window.addEventListener('keydown',handler); return () => window.removeEventListener('keydown',handler); },[newWorkspace]);
  const login = async (id: string) => {
    setBusy(true); setError('');
    try { const result = await api<{token:string}>('/demo/login',{unit_id:id}); sessionStorage.setItem('accord.session',result.token); sessionStorage.removeItem('accord.thread'); setThreadId(null); setData(null); setState(null); setToken(result.token); setModal(null); setView('workspace'); location.hash = ''; }
    catch(e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const perform = async (path: string, body: Record<string,unknown>) => {
    if (busy) return false;
    setBusy(true); setError('');
    try { await command(path,body); await refresh(); return true; } catch(e) { setError((e as Error).message); return false; } finally { setBusy(false); }
  };
  const openMember = async (id: string) => {
    if (busy) return; setBusy(true); setError('');
    try { const result = await command<{id:string}>('/threads',{target_id:id}); selectThread(result.id); }
    catch(e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const send = async (body: string, sourceIds: string[]) => {
    if (!state || busy) return false;
    setBusy(true); setError('');
    try {
      let id = threadId;
      if (!id) { const result = await command<{id:string}>('/threads',{target_id:state.me}); id=result.id; }
      await command(`/threads/${id}/messages`,{body,source_ids:sourceIds});
      if (threadId !== id) selectThread(id); else await refresh();
      return true;
    } catch(e) { setError((e as Error).message); return false; } finally { setBusy(false); }
  };
  const doc = (document: Document) => setModal({kind:'document',document});
  const task = (item: Task) => { void perform(`/tasks/${item.id}/status`,{status:item.status === 'done' ? 'open' : 'done'}); };
  return <TooltipProvider delayDuration={300}>
    {!token ? <main className="login-screen"><div className="login-card"><span className="wordmark">accord<span>·</span></span><h1>让协作先行。</h1><p>Agent 接住日常问题，重要的事由你拍板。</p><div className="login-members">{members.map(m => <button key={m.id} disabled={busy} onClick={() => void login(m.id)}><Avatar label={m.person_name} initial={m.person_name[0]} size={36} /><span><strong>{m.person_name}</strong><small>{m.tags[0]}</small></span><ArrowRightIcon size={16} /></button>)}</div>{error && <p role="alert" className="form-error">{error}<Button variant="ghost" size="sm" onClick={() => location.reload()}>重新连接</Button></p>}<small className="login-note">选择一个演示成员进入 · 使用合成资料 · 仅本机运行</small></div></main> : !state ? <main className="boot-screen"><Pending />{error && <div role="alert"><p>{error}</p><Button variant="secondary" onClick={() => { sessionStorage.removeItem('accord.session'); setToken(null); }}>重新进入</Button></div>}</main> : <div className="app-shell">
      <div className="app-rail"><button className="brand-mark" aria-label="Accord 工作台" onClick={newWorkspace}>a</button><IconButton label="工作空间" active onClick={() => navigate('workspace')}><ViewGridLinedIcon /></IconButton><div className="rail-spacer" /><IconButton label="工作空间设置" onClick={() => setModal({kind:'settings'})}><SettingsIcon /></IconButton><Avatar label={state.members.find(m=>m.id===state.me)!.person_name} initial={state.members.find(m=>m.id===state.me)!.person_name[0]} size={25} /></div>
      <Sidebar state={state} view={view} setView={v => v === 'workspace' ? newWorkspace() : navigate(v)} selected={threadId} selectThread={selectThread} newThread={newWorkspace} query={query} setQuery={setQuery} settings={() => setModal({kind:'settings'})} open={sidebar} close={() => setSidebar(false)} />
      <div className="workbench"><header className="workbench-header"><div className="breadcrumb"><span className="mobile-menu"><IconButton label="打开导航" onClick={() => setSidebar(!sidebar)}><LayoutMenuIcon /></IconButton></span><span>AlxOrigin</span><span className="breadcrumb-slash">/</span><strong>{view === 'workspace' && data ? data.thread.title : viewTitles[view]}</strong></div><div className="header-actions"><Badge variant="ghost" className="local-badge">本地演示</Badge><IconButton label="新建协作" onClick={newWorkspace}><AddIcon /></IconButton><span className="context-toggle"><IconButton label="切换项目上下文" active={context} onClick={() => setContext(!context)}><GridRightLinedIcon /></IconButton></span><IconButton label="外观与成员" onClick={() => setModal({kind:'settings'})}><SettingsIcon /></IconButton></div></header>
        {error && <div className="error-banner" role="alert"><span>{error}</span><Button variant="ghost" size="sm" onClick={() => { void refresh().then(()=>setError('')).catch(e=>setError(e.message)); }}>重试</Button><Button variant="ghost" size="icon-xs" aria-label="关闭提示" onClick={() => setError('')}><CloseIcon /></Button></div>}
        <div className="workspace-body"><main className="main-surface" id="main-content">{view === 'gallery' ? <Gallery /> : view === 'workspace' ? <Conversation state={state} data={data} loading={loading} busy={busy} onSend={send} onHandoff={() => data && setModal({kind:'handoff',thread:data.thread})} onConfirm={() => data && setModal({kind:'confirm',thread:data.thread})} onDocument={doc} onNew={newWorkspace} prompt="" /> : <Lists view={view} state={state} busy={busy} onMember={id=>void openMember(id)} onThread={selectThread} onDocument={doc} onPublish={() => setModal({kind:'publish'})} onTask={task} />}</main>{context && view !== 'gallery' && <ContextPanel state={state} onDocument={doc} onThread={selectThread} />}</div>
        <footer className="workbench-footer"><span><span className="status-dot" />{state.model.label}</span><span>{busy && <LoadingIcon size={12} />}{busy ? '正在处理' : error ? '请处理上方提示' : '协作记录自动保存'}</span></footer>
      </div><Dialogs modal={modal} close={() => setModal(null)} state={state} busy={busy} submit={perform} theme={theme} setTheme={setTheme} login={id=>void login(id)} />
    </div>}
  </TooltipProvider>;
}
