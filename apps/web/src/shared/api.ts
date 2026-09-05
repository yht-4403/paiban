export type Member = { id: string; person_name: string; agent_name: string; window: string; tags: string[] };
export type Thread = { id: string; owner_id: string; target_id: string; title: string; kind: 'workspace' | 'peer'; status: 'agent' | 'scheduled' | 'waiting' | 'human' | 'resolved'; delivery_at: string; handoff_note: string; updated_at: string };
export type Document = { id: string; unit_id: string; title: string; body: string; created_at: string };
export type Message = { id: string; from_kind: 'human' | 'agent' | 'system'; from_unit: string; body: string; sources: string[]; created_at: string; meta: { mode?: string; needs_human?: boolean } };
export type Task = { id: string; title: string; detail: string; status: string; assignee_id: string; creator_id: string; thread_id: string };
export type State = { me: string; members: Member[]; threads: Thread[]; tasks: Task[]; documents: Document[]; model: { mode: string; label: string }; demo: boolean; project: { name: string; description: string } };
export type ThreadData = { thread: Thread; messages: Message[] };

export async function api<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const token = sessionStorage.getItem('accord.session');
  const response = await fetch('/api' + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : `请求没有完成（${response.status}），请重试。`);
  }
  return response.json();
}

const retries = new Map<string, string>();
export async function command<T>(path: string, body: Record<string, unknown> = {}): Promise<T> {
  const key = sessionStorage.getItem('accord.session') + path + JSON.stringify(body);
  const operation_id = retries.get(key) ?? crypto.randomUUID();
  retries.set(key, operation_id);
  const result = await api<T>(path, { ...body, operation_id });
  retries.delete(key);
  return result;
}

export const statusLabels: Record<Thread['status'], string> = { agent: 'Agent 通道', scheduled: '等待送达', waiting: '待本人处理', human: '本人已接手', resolved: '已确认' };
export const timeLabel = (value: string) => new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value));
