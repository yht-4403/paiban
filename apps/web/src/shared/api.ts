import type { Flow } from '../features/coordination/types';
import { newOperationId } from './browser';

export type Activity = {label:string;source:string;seen_at:string|null;agent_working:boolean;work:{title:string;kind:string}|null;shared_tasks:{id:string;title:string;status:string;priority:'high'|'normal'|'low';thread_id:string}[];progress:{completed:number;total:number;scope:string}};
export type Member = { id: string; person_name: string; agent_name: string; window: string; tags: string[]; activity?: Activity };
export type ReasoningEffort = 'low' | 'high' | 'max';
export const reasoningLabels: Record<ReasoningEffort, string> = { low: '轻量', high: '深入', max: '最高' };
export type Thread = { id: string; owner_id: string; target_id: string; title: string; kind: 'workspace' | 'peer' | 'group'; member_ids?: string[]; preview?: string; status: 'agent' | 'scheduled' | 'waiting' | 'human' | 'resolved' | 'closed'; delivery_at: string; handoff_note: string; updated_at: string;
  purpose: 'ordinary' | 'exploration' | 'review' | 'handoff'; round_id: string; folder_id: string; placement_version: number };
export type ResourceRef = { id: string; version: number; title?: string };
export type ProcessAttachmentInput = { filename: string; content: string; mime_type: string };
export type ProcessAttachment = { id: string; thread_id: string; message_id: string; filename: string; mime_type: string; size: number; published_resource_id: string; created_at: string };
export type Document = { id: string; unit_id: string; title: string; body: string; created_at: string; version: number; scope: 'private' | 'team' | 'round'; kind: 'note' | 'collection' | 'brief' | 'proposal' | 'decision' | 'memory' | 'external'; round_id: string; refs: ResourceRef[] };
export type ContentConnection = { id:string; provider:'lark_doc'; locator:string; external_id:string; title:string; resource_id:string; enabled:boolean; status:'ready'|'syncing'|'error'|'disconnected'; external_revision:string; error_code:string; checked_at:string; synced_at:string; version:number; scope:'private'|'team'; resource_version:number };
export type Material = Omit<Document, 'body'> & { origin?: 'folder' | 'thread' | 'round' };
export type Binding = { included: string[]; excluded: string[]; folder_ids?: string[]; version: number };
export type Folder = { id: string; name: string; version: number; binding: Binding };
export type ThreadContext = { resources: Material[]; available: Material[]; binding: Binding; folder_id: string; folder_version: number; mounted_folders?: {id: string; name: string; version: number}[] };
export type TopicSummary = { id: string; title: string; owner_id: string; stage: 'exploring' | 'reviewing' | 'decided'; brief_id: string; deadline: string; version: number; member_ids: string[]; submitted_count: number; my_submitted: boolean; submission_version: number };
export type Message = { id: string; conversation_id: string; from_kind: 'human' | 'agent' | 'system'; from_unit: string; body: string; sources: string[]; created_at: string; meta: {
  completion_id?: string; actor_id?: string; agent_id?: string; mode?: string; status?: 'queued' | 'running' | 'done' | 'error' | 'cancelled'; run_id?: string; model?: string; error?: string; finish_reason?: string; duration_ms?: number; usage?: { total_tokens?: number; reasoning_tokens?: number };
  reasoning_effort?: ReasoningEffort; phase?: 'connecting' | 'thinking' | 'reading' | 'answering'; citations?: ResourceRef[]; context_sources?: import('../features/workspace/KnowledgeTools').ContextSource[];
} };
export type Task = { updated_at?:string; assign_reason?:string; id: string; title: string; detail: string; status: string; assignee_id: string; creator_id: string; thread_id: string; priority: 'high'|'normal'|'low' };
export type State = { flows?:Flow[]; context_sharing?:{source_kind:'conversation'|'state';source_id:string;enabled:number;version:number}[]; content_connections?:ContentConnection[]; me: string; members: Member[]; groups?: (Thread & {preview:string})[]; threads: Thread[]; archived_threads: Thread[]; tasks: Task[]; documents: Document[];
  folders: Folder[]; topics: TopicSummary[]; activity_preferences:{automatic:boolean;work_title:boolean;version:number};
  model: { mode: string; label: string; requests_today: number; reported_tokens_today: number; daily_limit: number; reasoning_effort: ReasoningEffort; reasoning_options: ReasoningEffort[] };
  account: { email: string; role: 'owner' | 'member' }; project: { name: string } };
export type ThreadData = { thread: Thread; segments?: Thread[]; messages: Message[]; context: ThreadContext;
  attachments?: ProcessAttachment[];
  active_context: { roots?: ResourceRef[]; resources: ResourceRef[]; binding_version: number; folder_id: string; folder_version: number }[];
  tool_calls: { id: string; run_id: string; name: string; resource_id: string; resource_version: number | null; status: string; result_chars: number; assistant_message_id: string }[] };
export type FixedAccountKind = 'demo' | 'trial';
export type FixedAccount = { id: string; name: string; agent_name: string; kind: FixedAccountKind };
export type AuthAccounts = { workspace: string; accounts: FixedAccount[] };
export type AuthStatus = { needs_setup: boolean; workspace: string; auth_mode?: 'fixed_accounts' | 'password' };
export type AuthSelection = { me: string; session_token: string };

const sessionTokenKey = 'accord.identity.session';
export function setSessionToken(token: string) {
  if (token) sessionStorage.setItem(sessionTokenKey, token);
  else sessionStorage.removeItem(sessionTokenKey);
}
export function hasSessionToken() { return !!sessionStorage.getItem(sessionTokenKey); }

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}
export async function api<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response;
  const sessionToken = sessionStorage.getItem(sessionTokenKey);
  try { response = await fetch('/api' + path, {
    method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal,
  }); } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError('暂时无法连接工作空间，输入已保留，请重新连接。', 0);
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    if (response.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('accord:auth-expired'));
    throw new ApiError(typeof data.detail === 'string' ? data.detail : response.status >= 500 ? '暂时无法连接工作空间，请重新连接。' : `请求没有完成（${response.status}），请重试。`, response.status);
  }
  return response.json();
}

let accountScope = '';
const retries = new Map<string, string>();
export function setAccountScope(id: string) { if (id !== accountScope) { retries.clear(); accountScope = id; } }
export async function command<T>(path: string, body: Record<string, unknown> = {}): Promise<T> {
  const key = accountScope + path + JSON.stringify(body);
  const operation_id = retries.get(key) ?? newOperationId();
  retries.set(key, operation_id);
  try {
    const result = await api<T>(path, { ...body, operation_id });
    retries.delete(key);
    return result;
  } catch (error) {
    if (error instanceof ApiError && error.status >= 400 && error.status < 500) retries.delete(key);
    throw error;
  }
}

export const statusLabels: Record<Thread['status'], string> = { agent: 'Agent 通道', scheduled: '等待送达', waiting: '待本人处理', human: '本人已回复', resolved: '已确认', closed:'本轮已结束' };
export const timeLabel = (value: string) => new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value));
