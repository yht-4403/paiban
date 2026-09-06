export type View = 'workspace' | 'chat' | 'people' | 'inbox' | 'tasks' | 'library' | 'gallery' | 'folder' | 'topics' | 'trash' | 'group' | 'meetings' | 'assignments';
export const viewTitles: Record<View,string> = { workspace:'工作台', chat:'找同事', people:'找同事', inbox:'需要你', tasks:'待办', library:'资料', gallery:'组件样板', folder:'文件夹', topics:'创新探索', trash:'回收站', group:'群聊',meetings:'开会',assignments:'任务分配' };
export type Route = { view: View; id: string | null; section: string };
export function route(): Route {
  const [page, rawId, section=''] = location.hash.slice(1).split('/');
  const view = (page==='tasks' ? 'workspace' : page in viewTitles && (page!=='gallery' || import.meta.env.DEV) ? page : 'workspace') as View;
  let id = null;
  try { id = ['workspace','chat','group','folder','topics','meetings','assignments'].includes(view) && rawId ? decodeURIComponent(rawId) : null; } catch { /* Invalid addresses return to the work list. */ }
  return { view, id, section };
}
