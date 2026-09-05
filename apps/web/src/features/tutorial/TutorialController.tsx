import { useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@tutti-os/ui-system';
import { LoadingIcon } from '@tutti-os/ui-system/icons';
import { driver, type Driver } from 'driver.js';
import 'driver.js/dist/driver.css';
import { api, command, type State, type Task, type ThreadData } from '../../shared/api';
import type { View } from '../../shared/routes';
import { runTutorialAction, type TutorialActionName, type TutorialActionPayload, type TutorialActionResult } from './bridge';
import './tutorial.css';

const TRIAL_ONE = 'fixed_trial_1';
const TRIAL_TWO = 'fixed_trial_2';
const TRIAL_THREE = 'fixed_trial_3';
export const TUTORIAL_TRIAL_ACCOUNT_IDS = [TRIAL_ONE, TRIAL_TWO, TRIAL_THREE] as const;
export function isTutorialTrialAccount(id: string) { return TUTORIAL_TRIAL_ACCOUNT_IDS.some(accountId => accountId === id); }

const TUTORIAL_SOURCE_BY_MEMBER: Record<(typeof TUTORIAL_TRIAL_ACCOUNT_IDS)[number], string> = {
  [TRIAL_ONE]: 'tutorial_context_fixed_trial_1_v1',
  [TRIAL_TWO]: 'tutorial_context_fixed_trial_2_v1',
  [TRIAL_THREE]: 'tutorial_context_fixed_trial_3_v1',
};
const TUTORIAL_FLOW_SOURCE_IDS = TUTORIAL_TRIAL_ACCOUNT_IDS.map(id => TUTORIAL_SOURCE_BY_MEMBER[id]);
const STORAGE_KEY = 'accord.guided-tutorial.v2';

export const tutorialCopy = {
  chat: '明天的 Accord 路演应该聚焦哪三个动作？请只依据你已共享的资料回答，并列出来源。',
  meeting: '请在路演前确定三段演示的最终主线、90 秒开场稿和 1440 × 900 界面验收范围。先收集三位成员的上下文，推荐必要参会者；正式会议中再由人确认分工。',
  ownerLine: '今天拍板三段演示：问同事 Agent、开决策会、分配并完成任务。体验者二负责定稿 90 秒开场稿，体验者三负责完成 1440 × 900 界面复核；请两位确认。',
  productLine: '确认。我负责定稿 90 秒开场稿，今天完成后把完整稿件放入团队工作池。',
  uiLine: '确认。我负责完成 1440 × 900 界面复核，今天提交包含结论和检查项的复核记录。',
  productCompletionTitle: 'Accord 90 秒开场稿 · 完成记录',
  uiCompletionTitle: 'Accord 工作台 1440 宽度复核 · 完成记录',
};

type Phase =
  | 'intro'
  | 'chat-ready' | 'chat-wait' | 'chat-result'
  | 'meeting-ready' | 'meeting-prepare-wait' | 'meeting-attendees'
  | 'meeting-one-ready' | 'meeting-two-ready' | 'meeting-three-ready' | 'meeting-finish-ready'
  | 'meeting-summary-wait' | 'meeting-actions'
  | 'completion-two-ready' | 'completion-two-wait'
  | 'completion-three-ready' | 'completion-three-wait'
  | 'followup-ready' | 'followup-wait'
  | 'done' | 'error';

type Recovery = 'prepare' | 'chat' | 'meeting' | 'actions' | 'completion-two' | 'completion-three' | 'followup';

const PHASES: Phase[] = [
  'intro', 'chat-ready', 'chat-wait', 'chat-result',
  'meeting-ready', 'meeting-prepare-wait', 'meeting-attendees',
  'meeting-one-ready', 'meeting-two-ready', 'meeting-three-ready', 'meeting-finish-ready',
  'meeting-summary-wait', 'meeting-actions',
  'completion-two-ready', 'completion-two-wait',
  'completion-three-ready', 'completion-three-wait',
  'followup-ready', 'followup-wait', 'done', 'error',
];
const RECOVERIES: Recovery[] = ['prepare', 'chat', 'meeting', 'actions', 'completion-two', 'completion-three', 'followup'];

type TutorialSession = {
  version: 2; active: true; paused: boolean; phase: Phase; prepared: boolean;
  chatThreadId: string; chatBaseline: string[]; meetingFlowId: string; meetingThreadId: string;
  taskTwoId: string; taskThreeId: string; completionTwoResourceId: string; completionThreeResourceId: string;
  completionFlowId: string; completionThreadId: string; nextFlowId: string;
  error: string; recovery: Recovery; errorStep: number;
};

type FlowAction = { id: string; assignee_id: string; title: string; detail: string; status: string; task_id: string; task_status?: string };
type FlowDetail = {
  id: string; kind: 'sync' | 'decision' | 'assignment' | 'chat_summary' | 'task_summary'; status: string; error: string;
  task_id: string; thread_id: string; sources_changed?: boolean;
  result: { candidates?: { person_id: string; reason: string }[] };
  evidence: { person_id: string; answer: string; sources: { id: string; title?: string; source_kind?: string; version?: number }[] }[];
  actions: FlowAction[];
  follow_up?: { ready: boolean; status: 'waiting' | 'suggested' | 'created' | 'dismissed'; next_flow_id: string; completed_count: number; task_count: number };
};
type TaskActionResult = { ok: boolean; flowId?: string; threadId?: string };
type Props = {
  startSignal: number; state: State; data: ThreadData | null; view: View; routeId: string | null; busy: boolean;
  onNavigate: (view: View, id?: string | null) => void; onOpenTrialChat: (id: string) => Promise<string | null>;
  onRefresh: () => Promise<void>; onContext: (open: boolean) => void; onSwitchAccount: (id: string) => Promise<State>;
  onTask: (task: Task) => Promise<TaskActionResult>;
};

const emptySession = (): TutorialSession => ({
  version: 2, active: true, paused: false, phase: 'intro', prepared: false, chatThreadId: '', chatBaseline: [],
  meetingFlowId: '', meetingThreadId: '', taskTwoId: '', taskThreeId: '', completionTwoResourceId: '',
  completionThreeResourceId: '', completionFlowId: '', completionThreadId: '', nextFlowId: '', error: '', recovery: 'prepare', errorStep: 1,
});

function restoreSession(): TutorialSession | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null') as Partial<TutorialSession> | null;
    if (!value || value.version !== 2 || value.active !== true || !PHASES.includes(value.phase as Phase)) return null;
    if (value.paused !== undefined && typeof value.paused !== 'boolean') return null;
    if (value.prepared !== undefined && typeof value.prepared !== 'boolean') return null;
    if (value.chatBaseline !== undefined && (!Array.isArray(value.chatBaseline) || value.chatBaseline.some(id => typeof id !== 'string'))) return null;
    const keys: (keyof TutorialSession)[] = ['chatThreadId', 'meetingFlowId', 'meetingThreadId', 'taskTwoId', 'taskThreeId', 'completionTwoResourceId', 'completionThreeResourceId', 'completionFlowId', 'completionThreadId', 'nextFlowId', 'error'];
    if (keys.some(key => value[key] !== undefined && typeof value[key] !== 'string')) return null;
    if (value.recovery !== undefined && !RECOVERIES.includes(value.recovery)) return null;
    if (value.errorStep !== undefined && (!Number.isInteger(value.errorStep) || value.errorStep! < 1 || value.errorStep! > 7)) return null;
    return { ...emptySession(), ...value } as TutorialSession;
  } catch { return null; }
}

function sleep(ms: number) { return new Promise(resolve => window.setTimeout(resolve, ms)); }
function flowEvidenceIssue(flow: FlowDetail) {
  if (flow.sources_changed) return '本轮使用的共享资料范围已经变化。系统已停住，请重新收集。';
  for (const memberId of TUTORIAL_TRIAL_ACCOUNT_IDS) {
    const matches = flow.evidence.filter(item => item.person_id === memberId);
    if (matches.length !== 1 || !matches[0].answer.trim()) return '三位个人 Agent 的真实回复尚未完整返回。系统已停住，请重新收集。';
    if (!matches[0].sources.some(source => source.id === TUTORIAL_SOURCE_BY_MEMBER[memberId])) return '本轮证据没有完整覆盖三位体验成员的指定共享资料。系统已停住，请重新收集。';
  }
  return '';
}
function meetingActionIssue(flow: FlowDetail) {
  if (!flow.actions.some(action => action.assignee_id === TRIAL_TWO)) return '会议纪要没有识别到体验者二明确承诺的开场稿任务。';
  if (!flow.actions.some(action => action.assignee_id === TRIAL_THREE)) return '会议纪要没有识别到体验者三明确承诺的界面复核任务。';
  return '';
}
function phaseAccount(session: TutorialSession) {
  if (session.phase === 'meeting-two-ready' || session.phase.startsWith('completion-two')) return TRIAL_TWO;
  if (session.phase === 'meeting-three-ready' || session.phase.startsWith('completion-three')) return TRIAL_THREE;
  if (session.phase === 'error' && session.recovery === 'completion-two') return TRIAL_TWO;
  if (session.phase === 'error' && session.recovery === 'completion-three') return TRIAL_THREE;
  return TRIAL_ONE;
}
async function waitForAction<Name extends TutorialActionName>(name: Name, payload: TutorialActionPayload<Name>): Promise<TutorialActionResult<Name>> {
  let last: unknown;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try { return await runTutorialAction(name, payload); }
    catch (error) { last = error; if (!(error instanceof Error) || !error.message.includes('载入')) throw error; await sleep(100); }
  }
  throw last instanceof Error ? last : new Error('当前操作区没有准备好，请重试。');
}
function phaseStep(session: TutorialSession) {
  if (session.phase === 'error') return session.errorStep;
  if (session.phase === 'intro') return 1;
  if (session.phase.startsWith('chat')) return 2;
  if (['meeting-ready', 'meeting-prepare-wait', 'meeting-attendees'].includes(session.phase)) return 3;
  if (session.phase.startsWith('meeting')) return 4;
  if (session.phase.startsWith('completion-two')) return 5;
  if (session.phase.startsWith('completion-three')) return 6;
  return 7;
}
function phaseTarget(session: TutorialSession) {
  if (session.phase === 'error') return '#main-content';
  if (session.phase === 'intro') return '[data-tour="work-pool"]';
  if (session.phase === 'chat-ready') return '[data-tour="composer"]';
  if (session.phase === 'chat-wait' || session.phase === 'chat-result') return '[data-tour="conversation-log"]';
  if (session.phase === 'meeting-ready') return '[data-tour="flow-editor"]';
  if (session.phase === 'meeting-prepare-wait' || session.phase === 'meeting-summary-wait') return '[data-tour="flow-status"]';
  if (session.phase === 'meeting-attendees') return '[data-tour="flow-candidates"]';
  if (['meeting-one-ready', 'meeting-two-ready', 'meeting-three-ready'].includes(session.phase)) return '[data-tour="composer"]';
  if (session.phase === 'meeting-finish-ready') return '[data-tour="meeting-finish"]';
  if (session.phase === 'meeting-actions') return '.flow-suggestions';
  if (session.phase === 'completion-two-ready') return `[data-tour-task="${session.taskTwoId}"]`;
  if (session.phase === 'completion-three-ready') return `[data-tour-task="${session.taskThreeId}"]`;
  if (session.phase === 'completion-two-wait' || session.phase === 'completion-three-wait') return '[data-tour="conversation-log"]';
  if (session.phase === 'followup-ready') return '[data-tour="flow-follow-up"]';
  if (session.phase === 'followup-wait' || session.phase === 'done') return '[data-tour="flow-status"]';
  return '#main-content';
}
function phaseContent(session: TutorialSession) {
  if (session.phase === 'intro') return { title: session.prepared ? '共享资料已就绪' : '正在准备共享资料', description: session.prepared ? '三位体验成员各有一份团队可读资料。' : '只补齐资料，不预制回答和业务结果。', action: session.prepared ? '去问同事 Agent' : '正在准备', disabled: !session.prepared };
  if (session.phase === 'chat-ready') return { title: '先问同事 Agent', description: '问题已经填好；发送后 Agent 会真实查阅体验者二的资料。', action: '发送问题', disabled: false };
  if (session.phase === 'chat-wait') return { title: '同事 Agent 正在回答', description: '真实查阅、思考和生成完成后再继续。', action: '等待回答', disabled: true };
  if (session.phase === 'chat-result') return { title: '回答与来源已返回', description: '下一步用同一套授权上下文准备决策会。', action: '发起决策会', disabled: false };
  if (session.phase === 'meeting-ready') return { title: '会前收集信息', description: '议题、会议类型和三位相关成员已经填好。', action: '开始收集', disabled: false };
  if (session.phase === 'meeting-prepare-wait') return { title: '正在询问三位个人 Agent', description: '系统正在整理进展、缺口与必要参会人。', action: '等待汇总', disabled: true };
  if (session.phase === 'meeting-attendees') return { title: '确认参会人', description: '下一步创建三人的真人文字会议。', action: '开始会议', disabled: false };
  if (session.phase === 'meeting-one-ready') return { title: '发起人提出分工', description: '这是会议中的真人消息。', action: '发送并切换体验者二', disabled: false };
  if (session.phase === 'meeting-two-ready') return { title: '体验者二确认承诺', description: '确认后切换到体验者三。', action: '发送并切换体验者三', disabled: false };
  if (session.phase === 'meeting-three-ready') return { title: '体验者三确认承诺', description: '两项责任都由本人在群里确认。', action: '发送并返回发起人', disabled: false };
  if (session.phase === 'meeting-finish-ready') return { title: '结束真人会议', description: '结束后 Agent 才整理纪要和行动项。', action: '结束会议', disabled: false };
  if (session.phase === 'meeting-summary-wait') return { title: '正在整理会议纪要', description: '系统会识别明确承诺，不替成员补任务。', action: '等待纪要', disabled: true };
  if (session.phase === 'meeting-actions') return { title: '发布会后任务', description: '把两位成员已确认的行动项正式放进各自待办。', action: '确认分配', disabled: false };
  if (session.phase === 'completion-two-ready') return { title: '体验者二完成待办', description: '开场稿已放入工作池；勾选后由 Agent 核验。', action: '勾选待办', disabled: false };
  if (session.phase === 'completion-two-wait') return { title: '正在核验开场稿', description: '有真实完成证据才会关闭待办。', action: '等待核验', disabled: true };
  if (session.phase === 'completion-three-ready') return { title: '体验者三完成待办', description: '界面复核记录已放入工作池；勾选后由 Agent 核验。', action: '勾选待办', disabled: false };
  if (session.phase === 'completion-three-wait') return { title: '正在核验界面复核', description: '完成结果会回到原会议。', action: '等待核验', disabled: true };
  if (session.phase === 'followup-ready') return { title: '两项会后任务均已完成', description: '系统提出下一次同步，由发起人决定是否开始。', action: '发起下一次同步', disabled: false };
  if (session.phase === 'followup-wait') return { title: '正在汇总最新结果', description: '下一轮会读取两位成员刚完成的成果。', action: '等待同步', disabled: true };
  if (session.phase === 'done') return { title: '协作闭环已完成', description: '你已走完 Agent 代答、会前收集、真人会议、多人待办与下一轮同步。', action: '结束演练', disabled: false };
  return { title: '演练停在这里', description: session.error, action: '重试当前步骤', disabled: false };
}

export function TutorialController({ startSignal, state, data, view, routeId, busy, onNavigate, onOpenTrialChat, onRefresh, onContext, onSwitchAccount, onTask }: Props) {
  const [session, setSession] = useState<TutorialSession | null>(() => restoreSession());
  const sessionRef = useRef<TutorialSession | null>(session);
  const [visible, setVisible] = useState(() => { const restored = restoreSession(); return !!restored && !restored.paused; });
  const [acting, setActing] = useState(false);
  const [pointer, setPointer] = useState<{ left: number; top: number } | null>(null);
  const lastStart = useRef(startSignal);
  const preparing = useRef(false);
  const transitioning = useRef(false);
  const driverRef = useRef<Driver | null>(null);
  const reducedMotion = useMemo(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches, []);

  useEffect(() => {
    driverRef.current = driver({ animate: !reducedMotion, duration: reducedMotion ? 0 : 220, overlayOpacity: .5, overlayColor: getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim(), allowClose: false, allowKeyboardControl: false, disableActiveInteraction: true, smoothScroll: !reducedMotion, stagePadding: 8, stageRadius: 10, showButtons: [], waitForElement: 4000, skipMissingElement: false, popoverClass: 'accord-tutorial-driver-popover' });
    return () => { driverRef.current?.destroy(); driverRef.current = null; };
  }, [reducedMotion]);

  const replaceSession = (next: TutorialSession | null) => { sessionRef.current = next; setSession(next); if (next) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next)); else sessionStorage.removeItem(STORAGE_KEY); };
  const update = (values: Partial<TutorialSession>) => { const current = sessionRef.current; if (current) replaceSession({ ...current, ...values }); };
  const fail = (error: unknown, recovery: Recovery, errorStep: number) => update({ phase: 'error', error: error instanceof Error ? error.message : '当前步骤没有完成，请重试。', recovery, errorStep });
  const releasePage = () => window.dispatchEvent(new Event('accord:tutorial-release'));
  const pause = () => { driverRef.current?.destroy(); setPointer(null); releasePage(); update({ paused: true }); setVisible(false); };
  const finish = () => { driverRef.current?.destroy(); setPointer(null); releasePage(); setVisible(false); replaceSession(null); };
  const cue = async (selector: string) => {
    let element: HTMLElement | null = null;
    for (let attempt = 0; attempt < 40; attempt += 1) { element = document.querySelector(selector) as HTMLElement | null; if (element) break; await sleep(100); }
    if (!element) throw new Error('当前操作按钮仍在载入，请稍后重试。');
    element.scrollIntoView({ block: 'center', inline: 'nearest', behavior: reducedMotion ? 'auto' : 'smooth' });
    await sleep(reducedMotion ? 20 : 140);
    const box = element.getBoundingClientRect();
    setPointer({ left: Math.min(window.innerWidth - 38, Math.max(8, box.right - 24)), top: Math.min(window.innerHeight - 44, Math.max(8, box.top + Math.min(box.height / 2, 30))) });
    element.classList.add('tutorial-action-cue'); await sleep(reducedMotion ? 120 : 660); element.classList.remove('tutorial-action-cue'); setPointer(null);
  };

  const prepare = async () => {
    if (preparing.current) return;
    preparing.current = true; setActing(true);
    try {
      setVisible(true); replaceSession({ ...emptySession(), phase: 'intro' }); onNavigate('workspace'); onContext(true); await api('/tutorial/prepare', {});
      if (state.me !== TRIAL_ONE) await onSwitchAccount(TRIAL_ONE); else await onRefresh();
      onContext(true); update({ prepared: true, phase: 'intro', error: '' });
    } catch (error) { fail(error, 'prepare', 1); } finally { preparing.current = false; setActing(false); }
  };
  const openChat = async () => {
    if (state.me !== TRIAL_ONE) await onSwitchAccount(TRIAL_ONE);
    const threadId = await onOpenTrialChat(TRIAL_TWO);
    if (!threadId) throw new Error('没有打开体验者二的 Agent 对话，请重试。');
    const draftId = `accord.draft.${TRIAL_ONE}.${threadId}`;
    await cue('[data-tour="composer"]'); sessionStorage.setItem(draftId, tutorialCopy.chat);
    await waitForAction('composer.fill', { draftId, value: tutorialCopy.chat, sourceIds: [TUTORIAL_SOURCE_BY_MEMBER[TRIAL_TWO]] });
    update({ phase: 'chat-ready', chatThreadId: threadId, error: '' });
  };
  const openMeeting = async () => {
    if (state.me !== TRIAL_ONE) await onSwitchAccount(TRIAL_ONE);
    onNavigate('meetings'); await cue('[data-tour="flow-open-meeting"]');
    await waitForAction('flow.fill', { assignment: false, kind: 'decision', prompt: tutorialCopy.meeting, memberIds: [...TUTORIAL_TRIAL_ACCOUNT_IDS], sourceIds: [...TUTORIAL_FLOW_SOURCE_IDS] });
    update({ phase: 'meeting-ready', error: '' });
  };
  const fillMeetingLine = async (accountId: string, line: string, phase: Phase) => {
    const current = sessionRef.current;
    if (!current?.meetingThreadId) throw new Error('真人会议尚未创建。');
    if (state.me !== accountId) await onSwitchAccount(accountId);
    onNavigate('group', current.meetingThreadId);
    const draftId = `accord.draft.${accountId}.${current.meetingThreadId}.group`;
    sessionStorage.setItem(draftId, line); await cue('[data-tour="composer"]');
    await waitForAction('composer.fill', { draftId, value: line, sourceIds: [] }); update({ phase, error: '' });
  };
  const sendMeetingLine = async (accountId: string, line: string) => {
    const current = sessionRef.current;
    if (!current?.meetingThreadId) throw new Error('真人会议尚未创建。');
    const draftId = `accord.draft.${accountId}.${current.meetingThreadId}.group`;
    await cue('[data-tour="composer-send"]'); await runTutorialAction('composer.send', { draftId, expectedValue: line, sourceIds: [] }); await sleep(420);
  };
  const completionBody = (memberId: string, task: Task) => memberId === TRIAL_TWO
    ? `# Accord 90 秒开场稿完成记录\n\n关联待办：${task.id}\n\n## 开场稿\n\n团队协作的瓶颈，常常不是没人做，而是每个人都在反复解释自己做过什么。Accord 为每位成员提供一个只读取授权资料的专属 Agent：同事先问 Agent，资料不足再在原对话找本人；会议前自动收集上下文，会议后把真人确认的行动项送入负责人待办；完成结果会回到原会议，帮助团队在需要时立刻开始下一轮同步。\n\n## 已完成\n\n- 明确问题、解决方式与三段演示主线。\n- 控制在 90 秒内可讲完。\n- 保留资料授权、人类拍板和真实完成证据。`
    : `# Accord 工作台 1440 宽度复核完成记录\n\n关联待办：${task.id}\n\n## 复核结论\n\n已在 1440 × 900 浏览器视口完成 Accord 工作台复核。聊天主区、右侧待办与工作池、来源入口和关键按钮均可见，无横向滚动。\n\n## 已检查\n\n- 同事 Agent 回答与来源在同一消息流查看。\n- 真人会议输入框不再出现 Agent 入口。\n- 会后行动项、完成回执与下一次同步入口层级清楚。\n- 页面没有倒计时弹窗。`;
  const prepareCompletion = async (memberId: typeof TRIAL_TWO | typeof TRIAL_THREE, taskId: string) => {
    const next = await onSwitchAccount(memberId); onNavigate('workspace'); onContext(true);
    const task = next.tasks.find(item => item.id === taskId && item.assignee_id === memberId);
    if (!task) throw new Error(`${memberId === TRIAL_TWO ? '体验者二' : '体验者三'}尚未收到会议待办。`);
    await cue('[data-tour="work-pool"]');
    const title = memberId === TRIAL_TWO ? tutorialCopy.productCompletionTitle : tutorialCopy.uiCompletionTitle;
    const field = memberId === TRIAL_TWO ? 'completionTwoResourceId' : 'completionThreeResourceId';
    let resourceId = sessionRef.current?.[field] || '';
    if (!resourceId) {
      const body = completionBody(memberId, task);
      const existing = next.documents.find(document => document.unit_id === memberId && document.title === title);
      if (existing) {
        if (!existing.body.includes(task.id)) await command(`/resources/${existing.id}/update`, { title, body, scope: 'team', resource_ids: [], expected_version: existing.version });
        resourceId = existing.id;
      } else resourceId = (await command<{ id: string }>('/resources', { title, body, scope: 'team', resource_ids: [] })).id;
      update({ [field]: resourceId });
    }
    await onRefresh(); update({ phase: memberId === TRIAL_TWO ? 'completion-two-ready' : 'completion-three-ready', completionFlowId: '', completionThreadId: '', error: '' });
  };
  const publishMeetingActions = async () => {
    const current = sessionRef.current;
    if (!current?.meetingFlowId) throw new Error('会议纪要尚未生成。');
    const flow = await api<FlowDetail>(`/flows/${current.meetingFlowId}`);
    const issue = meetingActionIssue(flow); if (issue) throw new Error(issue);
    const selected = [flow.actions.find(action => action.assignee_id === TRIAL_TWO), flow.actions.find(action => action.assignee_id === TRIAL_THREE)].filter((action): action is FlowAction => !!action);
    const wanted = new Set(selected.map(action => action.id)); const taskIds: Record<string, string> = {};
    for (const action of flow.actions) {
      const accept = wanted.has(action.id);
      if (action.status === 'suggested') {
        await cue(`[data-tour-flow-action="${action.id}"]`);
        const result = await command<{ task_id: string }>(`/flow-actions/${action.id}/${accept ? 'accept' : 'dismiss'}`, {});
        if (accept) taskIds[action.assignee_id] = result.task_id;
        await sleep(280);
      } else if (accept && action.status === 'accepted') taskIds[action.assignee_id] = action.task_id;
      else if (accept) throw new Error('演练需要的行动项已经被忽略，请重新开始演练。');
    }
    if (!taskIds[TRIAL_TWO] || !taskIds[TRIAL_THREE]) throw new Error('会议行动项没有完整创建为两位成员的待办。');
    update({ taskTwoId: taskIds[TRIAL_TWO], taskThreeId: taskIds[TRIAL_THREE], error: '' }); await onRefresh(); await prepareCompletion(TRIAL_TWO, taskIds[TRIAL_TWO]);
  };
  const retryCompletion = async (memberId: typeof TRIAL_TWO | typeof TRIAL_THREE) => {
    const current = sessionRef.current; if (!current) return;
    if (!current.completionFlowId) { update({ phase: memberId === TRIAL_TWO ? 'completion-two-ready' : 'completion-three-ready', error: '' }); return; }
    const flow = await api<FlowDetail>(`/flows/${current.completionFlowId}`);
    if (flow.status === 'needs_input') await command(`/task-summaries/${flow.id}/reply`, { body: '对应完成记录已经放入我的团队工作池，请读取该记录并按待办目标重新核验。' });
    else if (flow.status === 'error') await command(`/task-summaries/${flow.id}/retry`, {});
    else if (flow.status === 'cancelled') { update({ phase: memberId === TRIAL_TWO ? 'completion-two-ready' : 'completion-three-ready', completionFlowId: '', error: '' }); return; }
    else throw new Error('整理状态已经变化，请稍后再试。');
    update({ phase: memberId === TRIAL_TWO ? 'completion-two-wait' : 'completion-three-wait', error: '' });
  };
  const resumeLiveMeeting = async (threadId: string) => {
    update({ meetingThreadId: threadId });
    const thread = await api<ThreadData>(`/threads/${threadId}`);
    const humanLines = new Set(thread.messages.filter(message => message.from_kind === 'human').map(message => message.body));
    if (!humanLines.has(tutorialCopy.ownerLine)) { await fillMeetingLine(TRIAL_ONE, tutorialCopy.ownerLine, 'meeting-one-ready'); return; }
    if (!humanLines.has(tutorialCopy.productLine)) { await fillMeetingLine(TRIAL_TWO, tutorialCopy.productLine, 'meeting-two-ready'); return; }
    if (!humanLines.has(tutorialCopy.uiLine)) { await fillMeetingLine(TRIAL_THREE, tutorialCopy.uiLine, 'meeting-three-ready'); return; }
    await onSwitchAccount(TRIAL_ONE); onNavigate('group', threadId); update({ phase: 'meeting-finish-ready', error: '' });
  };
  const retry = async () => {
    const current = sessionRef.current; if (!current) return;
    if (current.recovery === 'prepare') { await prepare(); return; }
    if (current.recovery === 'chat') { await openChat(); return; }
    if (current.recovery === 'actions') { await publishMeetingActions(); return; }
    if (current.recovery === 'completion-two') { await retryCompletion(TRIAL_TWO); return; }
    if (current.recovery === 'completion-three') { await retryCompletion(TRIAL_THREE); return; }
    if (current.recovery === 'followup') {
      const flow = await api<FlowDetail>(`/flows/${current.meetingFlowId}`);
      if (flow.follow_up?.next_flow_id) {
        const next = await api<FlowDetail>(`/flows/${flow.follow_up.next_flow_id}`);
        if (next.status === 'error') await command(`/flows/${next.id}/retry`, {});
        onNavigate('meetings', next.id);
        update({ phase: next.status === 'closed' ? 'done' : 'followup-wait', nextFlowId: next.id, error: '' });
      }
      else update({ phase: 'followup-ready', error: '' });
      return;
    }
    if (!current.meetingFlowId) { await openMeeting(); return; }
    const flow = await api<FlowDetail>(`/flows/${current.meetingFlowId}`);
    if (flow.status === 'error') { await command(`/flows/${flow.id}/retry`, {}); update({ phase: flow.thread_id ? 'meeting-summary-wait' : 'meeting-prepare-wait', error: '' }); }
    else if (flow.status === 'ready') update({ phase: 'meeting-attendees', error: '' });
    else if (flow.status === 'live') await resumeLiveMeeting(flow.thread_id);
    else if (flow.status === 'closed' && !meetingActionIssue(flow)) update({ phase: 'meeting-actions', error: '' });
    else await prepare();
  };
  const advance = async () => {
    const current = sessionRef.current; if (!current || acting || busy) return;
    if (current.phase === 'done') { finish(); return; }
    setActing(true);
    try {
      if (current.phase === 'error') { await retry(); return; }
      if (current.phase === 'intro') { await openChat(); return; }
      if (current.phase === 'chat-ready') {
        const draftId = `accord.draft.${TRIAL_ONE}.${current.chatThreadId}`;
        const baseline = (data?.messages || []).filter(message => message.conversation_id === current.chatThreadId && message.from_kind === 'agent' && message.meta.status === 'done').map(message => message.id);
        await cue('[data-tour="composer-send"]'); await runTutorialAction('composer.send', { draftId, expectedValue: tutorialCopy.chat, sourceIds: [TUTORIAL_SOURCE_BY_MEMBER[TRIAL_TWO]] });
        update({ phase: 'chat-wait', chatBaseline: baseline, error: '' }); return;
      }
      if (current.phase === 'chat-result') { await openMeeting(); return; }
      if (current.phase === 'meeting-ready') {
        await cue('[data-tour="flow-submit"]');
        const result = await runTutorialAction('flow.submit', { assignment: false, expectedPrompt: tutorialCopy.meeting, kind: 'decision', memberIds: [...TUTORIAL_TRIAL_ACCOUNT_IDS], sourceIds: [...TUTORIAL_FLOW_SOURCE_IDS] });
        update({ phase: 'meeting-prepare-wait', meetingFlowId: result.id, error: '' }); return;
      }
      if (current.phase === 'meeting-attendees') {
        await cue('[data-tour="flow-choose"]');
        const result = await runTutorialAction('flow.choose', { flowId: current.meetingFlowId, memberIds: [...TUTORIAL_TRIAL_ACCOUNT_IDS] });
        update({ meetingThreadId: result.thread_id }); await fillMeetingLine(TRIAL_ONE, tutorialCopy.ownerLine, 'meeting-one-ready'); return;
      }
      if (current.phase === 'meeting-one-ready') { await sendMeetingLine(TRIAL_ONE, tutorialCopy.ownerLine); await fillMeetingLine(TRIAL_TWO, tutorialCopy.productLine, 'meeting-two-ready'); return; }
      if (current.phase === 'meeting-two-ready') { await sendMeetingLine(TRIAL_TWO, tutorialCopy.productLine); await fillMeetingLine(TRIAL_THREE, tutorialCopy.uiLine, 'meeting-three-ready'); return; }
      if (current.phase === 'meeting-three-ready') { await sendMeetingLine(TRIAL_THREE, tutorialCopy.uiLine); await onSwitchAccount(TRIAL_ONE); onNavigate('group', current.meetingThreadId); update({ phase: 'meeting-finish-ready', error: '' }); return; }
      if (current.phase === 'meeting-finish-ready') { await cue('[data-tour="meeting-finish"]'); await command(`/flows/${current.meetingFlowId}/finish`, {}); onNavigate('meetings', current.meetingFlowId); update({ phase: 'meeting-summary-wait', error: '' }); return; }
      if (current.phase === 'meeting-actions') { await publishMeetingActions(); return; }
      if (current.phase === 'completion-two-ready' || current.phase === 'completion-three-ready') {
        const taskId = current.phase === 'completion-two-ready' ? current.taskTwoId : current.taskThreeId;
        const task = state.tasks.find(item => item.id === taskId && item.assignee_id === state.me);
        if (!task) throw new Error('当前账号还没有同步到这项待办，请刷新后重试。');
        await cue(`[data-tour-task="${task.id}"]`); const result = await onTask(task);
        if (!result.ok || !result.flowId) throw new Error('待办没有开始整理，请查看页面提示后重试。');
        update({ phase: current.phase === 'completion-two-ready' ? 'completion-two-wait' : 'completion-three-wait', completionFlowId: result.flowId, completionThreadId: result.threadId || '', error: '' }); return;
      }
      if (current.phase === 'followup-ready') {
        const flow = await api<FlowDetail>(`/flows/${current.meetingFlowId}`);
        if (!flow.follow_up?.ready || flow.follow_up.status !== 'suggested') throw new Error('两项会议待办尚未全部完成。');
        await cue('[data-tour="flow-follow-up-create"]');
        const result = await command<{ id: string }>(`/flows/${current.meetingFlowId}/follow-up`, { action: 'create', kind: 'sync' });
        onNavigate('meetings', result.id); update({ phase: 'followup-wait', nextFlowId: result.id, error: '' });
      }
    } catch (error) {
      const latest = sessionRef.current || current;
      const recovery: Recovery = latest.phase.startsWith('chat') ? 'chat' : latest.phase === 'meeting-actions' ? 'actions' : latest.phase.startsWith('completion-two') ? 'completion-two' : latest.phase.startsWith('completion-three') ? 'completion-three' : latest.phase.startsWith('followup') ? 'followup' : 'meeting';
      fail(error, recovery, phaseStep(latest));
    } finally { setActing(false); }
  };

  useEffect(() => { if (!startSignal || startSignal === lastStart.current) return; lastStart.current = startSignal; if (session) { update({ paused: false }); setVisible(true); return; } void prepare(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [startSignal]);
  useEffect(() => { if (session?.phase === 'intro' && !session.prepared && !session.paused && !acting && !preparing.current) void prepare(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [session?.phase, session?.prepared, acting]);

  const target = useMemo(() => session ? phaseTarget(session) : '', [session]);
  useEffect(() => {
    const guide = driverRef.current; if (!guide || !session || !visible || !target) { guide?.destroy(); return; }
    const timer = window.setTimeout(() => { const element = document.querySelector(target) || document.querySelector('#main-content'); if (element) guide.highlight({ element, disableActiveInteraction: true }); }, 120);
    return () => window.clearTimeout(timer);
  }, [session?.phase, session?.taskTwoId, session?.taskThreeId, target, visible, state.me, view, routeId, data?.thread.id]);

  useEffect(() => {
    if (!session || session.phase !== 'chat-wait' || state.me !== TRIAL_ONE || data?.thread.id !== session.chatThreadId) return;
    const fresh = data.messages.filter(message => message.conversation_id === session.chatThreadId && message.from_kind === 'agent' && !session.chatBaseline.includes(message.id));
    const failed = [...fresh].reverse().find(message => ['error', 'cancelled'].includes(message.meta.status || ''));
    if (failed) { fail(new Error(failed.meta.error || 'Agent 回答没有完成，请重试。'), 'chat', 2); return; }
    const completed = [...fresh].reverse().find(message => message.meta.status === 'done' && message.body.trim());
    if (completed) {
      const returnedSources = new Set([...(completed.sources || []), ...(completed.meta.context_sources || []).map(source => source.id)]);
      if (!returnedSources.has(TUTORIAL_SOURCE_BY_MEMBER[TRIAL_TWO])) { fail(new Error('Agent 已回答，但没有返回体验者二指定共享资料的来源。'), 'chat', 2); return; }
      update({ phase: 'chat-result', error: '' });
    }
  /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [session?.phase, session?.chatThreadId, data?.messages]);

  useEffect(() => {
    if (!session) return;
    const phase = session.phase;
    const flowId = phase === 'meeting-prepare-wait' || phase === 'meeting-summary-wait' ? session.meetingFlowId : phase === 'completion-two-wait' || phase === 'completion-three-wait' ? session.completionFlowId : phase === 'followup-wait' ? session.nextFlowId : '';
    if (!flowId) return;
    let stopped = false;
    const check = async () => {
      try {
        const flow = await api<FlowDetail>(`/flows/${flowId}`); if (stopped || transitioning.current) return;
        if (flow.status === 'error') {
          const recovery: Recovery = phase.startsWith('completion-two') ? 'completion-two' : phase.startsWith('completion-three') ? 'completion-three' : phase.startsWith('followup') ? 'followup' : 'meeting';
          fail(new Error(flow.error || 'Agent 整理没有完成，请重试。'), recovery, phaseStep(session)); return;
        }
        if (phase === 'meeting-prepare-wait' && flow.status === 'ready') { const issue = flowEvidenceIssue(flow); if (issue) { fail(new Error(issue), 'meeting', 3); return; } update({ phase: 'meeting-attendees', error: '' }); return; }
        if (phase === 'meeting-summary-wait' && flow.status === 'closed') { const issue = meetingActionIssue(flow); if (issue) { fail(new Error(issue), 'actions', 4); return; } update({ phase: 'meeting-actions', error: '' }); return; }
        if ((phase === 'completion-two-wait' || phase === 'completion-three-wait') && flow.status === 'closed') {
          transitioning.current = true;
          try {
            await onRefresh();
            if (phase === 'completion-two-wait') await prepareCompletion(TRIAL_THREE, session.taskThreeId);
            else { await onSwitchAccount(TRIAL_ONE); onNavigate('meetings', session.meetingFlowId); await onRefresh(); update({ phase: 'followup-ready', completionFlowId: '', completionThreadId: '', error: '' }); }
          } finally { transitioning.current = false; }
          return;
        }
        if ((phase === 'completion-two-wait' || phase === 'completion-three-wait') && flow.status === 'cancelled') { fail(new Error('本次完成核验已取消，待办仍保持未完成。'), phase === 'completion-two-wait' ? 'completion-two' : 'completion-three', phaseStep(session)); return; }
        if ((phase === 'completion-two-wait' || phase === 'completion-three-wait') && flow.status === 'needs_input') { fail(new Error('Agent 还缺一条可核验的完成信息。重试会请它读取工作池里的完成记录。'), phase === 'completion-two-wait' ? 'completion-two' : 'completion-three', phaseStep(session)); return; }
        if (phase === 'followup-wait' && flow.status === 'closed') update({ phase: 'done', error: '' });
      } catch (error) {
        if (!stopped && error instanceof Error && !error.message.includes('暂时无法连接')) {
          const recovery: Recovery = phase.startsWith('completion-two') ? 'completion-two' : phase.startsWith('completion-three') ? 'completion-three' : phase.startsWith('followup') ? 'followup' : 'meeting';
          fail(error, recovery, phaseStep(session));
        }
      }
    };
    void check(); const timer = window.setInterval(() => void check(), 1500); return () => { stopped = true; window.clearInterval(timer); };
  /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [session?.phase, session?.meetingFlowId, session?.completionFlowId, session?.nextFlowId]);

  useEffect(() => {
    if (!session || !visible || acting) return;
    let cancelled = false;
    const restore = async () => {
      try {
        const expectedAccount = phaseAccount(session);
        if (state.me !== expectedAccount) { releasePage(); await onSwitchAccount(expectedAccount); return; }
        if (session.phase === 'intro') { if (view !== 'workspace' || routeId) { onNavigate('workspace'); return; } onContext(true); return; }
        if (session.phase.startsWith('chat')) {
          if (view !== 'chat' || routeId !== session.chatThreadId) { onNavigate('chat', session.chatThreadId); return; }
          if (session.phase === 'chat-ready') { const draftId = `accord.draft.${TRIAL_ONE}.${session.chatThreadId}`; sessionStorage.setItem(draftId, tutorialCopy.chat); await waitForAction('composer.fill', { draftId, value: tutorialCopy.chat, sourceIds: [TUTORIAL_SOURCE_BY_MEMBER[TRIAL_TWO]] }); }
          return;
        }
        if (session.phase === 'meeting-ready') {
          if (view !== 'meetings' || routeId) { onNavigate('meetings'); return; }
          await waitForAction('flow.fill', { assignment: false, kind: 'decision', prompt: tutorialCopy.meeting, memberIds: [...TUTORIAL_TRIAL_ACCOUNT_IDS], sourceIds: [...TUTORIAL_FLOW_SOURCE_IDS] }); return;
        }
        if (['meeting-prepare-wait', 'meeting-attendees', 'meeting-summary-wait', 'meeting-actions', 'followup-ready'].includes(session.phase)) { if (view !== 'meetings' || routeId !== session.meetingFlowId) { onNavigate('meetings', session.meetingFlowId); return; } return; }
        if (['meeting-one-ready', 'meeting-two-ready', 'meeting-three-ready', 'meeting-finish-ready'].includes(session.phase)) {
          if (view !== 'group' || routeId !== session.meetingThreadId) { onNavigate('group', session.meetingThreadId); return; }
          if (session.phase !== 'meeting-finish-ready') {
            const account = session.phase === 'meeting-one-ready' ? TRIAL_ONE : session.phase === 'meeting-two-ready' ? TRIAL_TWO : TRIAL_THREE;
            const line = session.phase === 'meeting-one-ready' ? tutorialCopy.ownerLine : session.phase === 'meeting-two-ready' ? tutorialCopy.productLine : tutorialCopy.uiLine;
            const draftId = `accord.draft.${account}.${session.meetingThreadId}.group`; sessionStorage.setItem(draftId, line); await waitForAction('composer.fill', { draftId, value: line, sourceIds: [] });
          }
          return;
        }
        if (session.phase.startsWith('completion-two') || session.phase.startsWith('completion-three')) {
          if (session.phase.endsWith('-wait') && session.completionThreadId && (view !== 'workspace' || routeId !== session.completionThreadId)) { onNavigate('workspace', session.completionThreadId); return; }
          if (session.phase.endsWith('-ready') && view !== 'workspace') { onNavigate('workspace'); return; }
          onContext(true); return;
        }
        if (session.phase === 'followup-wait' || session.phase === 'done') { if (view !== 'meetings' || routeId !== session.nextFlowId) { onNavigate('meetings', session.nextFlowId); return; } }
      } catch (error) { if (!cancelled && error instanceof Error && !error.message.includes('载入')) fail(error, session.recovery, phaseStep(session)); }
    };
    const timer = window.setTimeout(() => void restore(), 160); return () => { cancelled = true; window.clearTimeout(timer); };
  /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [session?.phase, session?.chatThreadId, session?.meetingFlowId, session?.meetingThreadId, session?.completionThreadId, session?.nextFlowId, session?.recovery, state.me, view, routeId, visible, acting]);

  if (!session || !visible) return null;
  const content = phaseContent(session); const disabled = content.disabled || acting || busy;
  return <>
    <aside className="tutorial-panel" aria-live="polite" aria-label="教学演练">
      <div className="tutorial-panel-meta"><span>步骤 {phaseStep(session)}/7</span><button type="button" onClick={pause}>退出</button></div>
      <strong>{content.title}</strong><p>{content.description}</p>
      <Button data-tour="tutorial-next" size="sm" disabled={disabled} onClick={() => void advance()}>{(acting || content.disabled) && session.phase !== 'error' ? <LoadingIcon size={14} /> : null}{acting ? '正在执行' : content.action}</Button>
    </aside>
    {pointer && <span className="tutorial-pointer" style={{ left: pointer.left, top: pointer.top }} aria-hidden="true">☝</span>}
  </>;
}
