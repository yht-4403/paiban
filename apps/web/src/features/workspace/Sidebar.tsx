import { Avatar, Button, Input } from '@tutti-os/ui-system';
import { AddIcon, CheckIcon, ChevronDownIcon, FileTextIcon, MessageSquareTextIcon, SearchIcon, SettingsIcon, TaskIcon, UserLinedIcon, ViewGridLinedIcon } from '@tutti-os/ui-system/icons';
import type { State } from '../../shared/api';

export type View = 'workspace' | 'people' | 'inbox' | 'tasks' | 'library' | 'gallery';
const items: {id: View; label: string; icon: typeof TaskIcon}[] = [
  {id:'workspace',label:'我的工作台',icon:MessageSquareTextIcon},{id:'people',label:'找同事',icon:UserLinedIcon},
  {id:'inbox',label:'待我拍板',icon:CheckIcon},{id:'tasks',label:'我的待办',icon:TaskIcon},{id:'library',label:'共享成果',icon:FileTextIcon},
];

export function Sidebar({ state, view, setView, selected, selectThread, newThread, query, setQuery, settings, open, close }: {
  state: State; view: View; setView: (v: View) => void; selected: string | null; selectThread: (id: string) => void; newThread: () => void;
  query: string; setQuery: (value: string) => void; settings: () => void; open: boolean; close: () => void;
}) {
  const me = state.members.find(m => m.id === state.me)!;
  const inbox = state.threads.filter(t => t.target_id === state.me && ['waiting','human'].includes(t.status)).length;
  return <><div className={`sidebar-shade ${open ? 'visible' : ''}`} onClick={close} />
    <aside className={`sidebar ${open ? 'sidebar-open' : ''}`} aria-label="工作区导航">
      <button className="project-switch" onClick={() => setView('workspace')}><span className="project-initial">A</span><span><strong>AlxOrigin Team</strong><small>Accord 工作空间</small></span><ChevronDownIcon size={13} /></button>
      <div className="sidebar-search"><SearchIcon size={14} /><Input aria-label="搜索协作" placeholder="搜索协作…" value={query} onChange={e => setQuery(e.target.value)} /><span>⌕</span></div>
      <Button className="new-button" variant="secondary" onClick={newThread}><AddIcon />新的协作<span className="shortcut">⌘ K</span></Button>
      <nav className="primary-nav">{items.map(({id,label,icon:Icon}) => <Button key={id} variant="ghost" className={`nav-row ${view === id ? 'selected' : ''}`} onClick={() => setView(id)} aria-current={view === id ? 'page' : undefined}><Icon /><span>{label}</span>{id === 'inbox' && inbox > 0 && <span className="nav-count">{inbox}</span>}</Button>)}</nav>
      <div className="sidebar-section-title"><span>最近协作</span><Button variant="ghost" size="icon-xs" aria-label="新建协作" onClick={newThread}><AddIcon /></Button></div>
      <div className="recent-threads">{state.threads.filter(t => t.title.includes(query)).map(t => <Button key={t.id} variant="ghost" className={`thread-row ${view === 'workspace' && selected === t.id ? 'selected' : ''}`} onClick={() => selectThread(t.id)}><MessageSquareTextIcon /><span>{t.title}</span>{t.status === 'waiting' && <span className="notification-dot" />}</Button>)}{!state.threads.filter(t => t.title.includes(query)).length && <p className="sidebar-empty">{query ? '没有找到相关协作' : '开始对话后，会保存在这里'}</p>}</div>
      <div className="sidebar-bottom"><div className="quiet-note"><span className="status-dot" /><span>本地演示空间</span></div><Button variant="ghost" className="profile-button" onClick={settings}><Avatar label={me.person_name} initial={me.person_name[0]} size={28} /><span><strong>{me.person_name}</strong><small>{me.tags[0]}</small></span><SettingsIcon /></Button><Button variant="ghost" size="sm" className="gallery-link" onClick={() => setView('gallery')}><ViewGridLinedIcon />组件样板</Button></div>
    </aside></>;
}
