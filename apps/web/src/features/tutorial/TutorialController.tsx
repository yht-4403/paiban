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
export const TUTORIAL_TRIAL_ACCOUNT_IDS = [TRIAL_ONE,TRIAL_TWO,TRIAL_THREE] as const;
export function isTutorialTrialAccount(id:string) { return TUTORIAL_TRIAL_ACCOUNT_IDS.some(accountId=>accountId===id); }
const TUTORIAL_SOURCE_BY_MEMBER:Record<(typeof TUTORIAL_TRIAL_ACCOUNT_IDS)[number],string>={
  [TRIAL_ONE]:'tutorial_context_fixed_trial_1_v1',
  [TRIAL_TWO]:'tutorial_context_fixed_trial_2_v1',
  [TRIAL_THREE]:'tutorial_context_fixed_trial_3_v1',
};
const TUTORIAL_FLOW_SOURCE_IDS=TUTORIAL_TRIAL_ACCOUNT_IDS.map(id=>TUTORIAL_SOURCE_BY_MEMBER[id]);
const STORAGE_KEY = 'accord.guided-tutorial.v1';

export const tutorialCopy = {
  chat: '明天的 Accord 路演应该聚焦哪三个动作？请只依据你已共享的资料回答，并列出来源。',
  meeting: '明天路演前做一次三人同步：请分别汇总三个人已经完成的准备、仍需确认的事项和信息缺口，帮助我判断下一步。',
  assignment: '完成 Accord 工作台 1440 × 900 桌面宽度最终复核\n\n检查聊天主区、右侧待办与工作池、资料来源展开和关键按钮是否清晰可见，并提交一份完成记录。请根据职责和近期经验推荐 1–3 位候选人，最终由我选择。',
  completionTitle: 'Accord 工作台 1440 宽度复核 · 完成记录',
};

type Phase =
  | 'intro'
  | 'chat-ready' | 'chat-wait' | 'chat-result'
  | 'meeting-ready' | 'meeting-wait' | 'meeting-result'
  | 'assignment-ready' | 'assignment-wait' | 'assignment-result'
  | 'handoff-ready' | 'completion-ready' | 'completion-wait'
  | 'done' | 'error';

type Recovery = 'prepare' | 'chat' | 'meeting' | 'assignment' | 'handoff' | 'completion';

const PHASES:Phase[]=['intro','chat-ready','chat-wait','chat-result','meeting-ready','meeting-wait','meeting-result','assignment-ready','assignment-wait','assignment-result','handoff-ready','completion-ready','completion-wait','done','error'];
const RECOVERIES:Recovery[]=['prepare','chat','meeting','assignment','handoff','completion'];

type TutorialSession = {
  version: 1;
  active: true;
  paused: boolean;
  phase: Phase;
  prepared: boolean;
  chatThreadId: string;
  chatBaseline: string[];
  meetingFlowId: string;
  assignmentFlowId: string;
  taskId: string;
  taskThreadId: string;
  completionResourceId: string;
  completionFlowId: string;
  error: string;
  recovery: Recovery;
  errorStep: number;
};

type FlowDetail = {
  id: string;
  kind: 'sync' | 'decision' | 'assignment' | 'chat_summary' | 'task_summary';
  status: string;
  error: string;
  task_id: string;
  thread_id: string;
  sources_changed?: boolean;
  result: { candidates?: { person_id: string; reason: string }[] };
  evidence: {person_id:string;answer:string;sources:{id:string;title?:string;source_kind?:string;version?:number}[]}[];
};

type TaskActionResult = { ok: boolean; flowId?: string; threadId?: string };

type Props = {
  startSignal: number;
  state: State;
  data: ThreadData | null;
  view: View;
  routeId: string | null;
  busy: boolean;
  onNavigate: (view: View, id?: string | null) => void;
  onOpenTrialChat: (id: string) => Promise<string | null>;
  onRefresh: () => Promise<void>;
  onContext: (open: boolean) => void;
  onSwitchAccount: (id: string) => Promise<State>;
  onTask: (task: Task) => Promise<TaskActionResult>;
};

const emptySession = (): TutorialSession => ({
  version: 1,
  active: true,
  paused: false,
  phase: 'intro',
  prepared: false,
  chatThreadId: '',
  chatBaseline: [],
  meetingFlowId: '',
  assignmentFlowId: '',
  taskId: '',
  taskThreadId: '',
  completionResourceId: '',
  completionFlowId: '',
  error: '',
  recovery: 'prepare',
  errorStep: 1,
});

function restoreSession(): TutorialSession | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null') as Partial<TutorialSession> | null;
    if (!value || value.version !== 1 || value.active !== true || !PHASES.includes(value.phase as Phase)) return null;
    if(value.paused!==undefined&&typeof value.paused!=='boolean')return null;
    if(value.prepared!==undefined&&typeof value.prepared!=='boolean')return null;
    if(value.chatBaseline!==undefined&&(!Array.isArray(value.chatBaseline)||value.chatBaseline.some(id=>typeof id!=='string')))return null;
    const stringKeys:(keyof TutorialSession)[]=['chatThreadId','meetingFlowId','assignmentFlowId','taskId','taskThreadId','completionResourceId','completionFlowId','error'];
    if(stringKeys.some(key=>value[key]!==undefined&&typeof value[key]!=='string'))return null;
    if(value.recovery!==undefined&&!RECOVERIES.includes(value.recovery))return null;
    const errorStep=value.errorStep;
    if(errorStep!==undefined&&(!Number.isInteger(errorStep)||errorStep<1||errorStep>5))return null;
    const restored={...emptySession(),...value} as TutorialSession;
    if(restored.phase.startsWith('chat')&&!restored.chatThreadId)return null;
    if((restored.phase==='meeting-wait'||restored.phase==='meeting-result')&&!restored.meetingFlowId)return null;
    if((restored.phase==='assignment-wait'||restored.phase==='assignment-result'||restored.phase==='handoff-ready')&&!restored.assignmentFlowId)return null;
    if((restored.phase==='handoff-ready'||restored.phase.startsWith('completion')||restored.phase==='done')&&!restored.taskId)return null;
    if(restored.phase==='completion-wait'&&!restored.completionFlowId)return null;
    return restored;
  } catch {
    return null;
  }
}

function sleep(ms: number) {
  return new Promise(resolve => window.setTimeout(resolve, ms));
}

function flowEvidenceIssue(flow:FlowDetail) {
  if(flow.sources_changed)return '本轮使用的共享资料范围已经变化。系统已停住，请重新收集。';
  for(const memberId of TUTORIAL_TRIAL_ACCOUNT_IDS){
    const matches=flow.evidence.filter(item=>item.person_id===memberId);
    if(matches.length!==1||!matches[0].answer.trim())return '三位个人 Agent 的真实回复尚未完整返回。系统已停住，请重新收集。';
    if(!matches[0].sources.some(source=>source.id===TUTORIAL_SOURCE_BY_MEMBER[memberId]))return '本轮证据没有完整覆盖三位体验成员的指定共享资料。系统已停住，请重新收集。';
  }
  return '';
}

function phaseAccount(session:TutorialSession) {
  if(session.phase.startsWith('completion')||session.phase==='done')return TRIAL_THREE;
  if(session.phase==='error'&&(session.recovery==='completion'||session.recovery==='handoff'))return TRIAL_THREE;
  return TRIAL_ONE;
}

async function waitForAction<Name extends TutorialActionName>(
  name: Name,
  payload: TutorialActionPayload<Name>,
): Promise<TutorialActionResult<Name>> {
  let last: unknown;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      return await runTutorialAction(name, payload);
    } catch (error) {
      last = error;
      if (!(error instanceof Error) || !error.message.includes('载入')) throw error;
      await sleep(100);
    }
  }
  throw last instanceof Error ? last : new Error('当前操作区没有准备好，请重试。');
}

function phaseStep(session: TutorialSession) {
  if (session.phase === 'error') return session.errorStep;
  if (session.phase === 'intro') return 1;
  if (session.phase.startsWith('chat')) return 2;
  if (session.phase.startsWith('meeting')) return 3;
  if (session.phase.startsWith('assignment')) return 4;
  return 5;
}

function phaseTarget(session: TutorialSession) {
  if (session.phase === 'error') return '#main-content';
  if (session.phase === 'intro') return '[data-tour="work-pool"]';
  if (session.phase === 'chat-ready') return '[data-tour="composer"]';
  if (session.phase === 'chat-wait' || session.phase === 'chat-result') return '[data-tour="conversation-log"]';
  if (session.phase === 'meeting-ready' || session.phase === 'assignment-ready') return '[data-tour="flow-editor"]';
  if (session.phase === 'meeting-wait' || session.phase === 'meeting-result' || session.phase === 'assignment-wait') return '[data-tour="flow-status"]';
  if (session.phase === 'assignment-result') return `[data-tour-person="${TRIAL_THREE}"]`;
  if (session.phase === 'handoff-ready') return '[data-tour="flow-status"]';
  if (session.phase === 'completion-ready' && session.taskId) return `[data-tour-task="${session.taskId}"]`;
  if (session.phase === 'completion-wait') return '[data-tour="conversation-log"]';
  if (session.phase === 'done') return '[data-tour="todo-list"]';
  return '';
}

function phaseContent(session: TutorialSession) {
  const waiting = ['chat-wait', 'meeting-wait', 'assignment-wait', 'completion-wait'].includes(session.phase);
  if (session.phase === 'intro') return {
    title: session.prepared ? '共享上下文已就绪' : '正在准备共享上下文',
    description: session.prepared ? '三位体验成员各有一份真实可检索资料。右侧工作池就是 Agent 的授权来源。' : '只会补齐缺失的教学资料，不会生成对话、会议、任务或答案。',
    action: session.prepared ? '去问同事 Agent' : '正在准备', disabled: !session.prepared,
  };
  if (session.phase === 'chat-ready') return { title: '先问同事 Agent', description: '问题已填入。下一步会真实发送给体验者二的 Agent，并等待它查阅共享资料。', action: '发送问题', disabled: false };
  if (session.phase === 'chat-wait') return { title: '同事 Agent 正在回答', description: '可以看到真实的查阅、思考和生成状态。回答完成前不会推进。', action: '等待回答', disabled: true };
  if (session.phase === 'chat-result') return { title: '回答和来源已返回', description: '这段内容来自真实模型调用；资料来源可以在消息下方展开。', action: '发起同步会', disabled: false };
  if (session.phase === 'meeting-ready') return { title: '会前先收集信息', description: '三人同步议题和相关成员已填好。下一步会让三位个人 Agent 分别查阅各自上下文。', action: '开始收集', disabled: false };
  if (session.phase === 'meeting-wait') return { title: '正在收集三人上下文', description: '页面会持续显示收到的真实 Agent 回复，汇总完成前不会进入下一项。', action: '等待汇总', disabled: true };
  if (session.phase === 'meeting-result') return { title: '会前同步已完成', description: '已形成真实同步纪要并闭环保存，无需留下进行中的会议。', action: '分配任务', disabled: false };
  if (session.phase === 'assignment-ready') return { title: '让 Agent 推荐负责人', description: '任务目标与候选范围已填好。系统只会依据三人的真实授权上下文推荐。', action: '开始推荐', disabled: false };
  if (session.phase === 'assignment-wait') return { title: '正在比较候选人', description: '推荐结果由真实模型生成；没有足够依据时会停住，而不是补一个假人选。', action: '等待推荐', disabled: true };
  if (session.phase === 'assignment-result') return { title: '真实推荐命中体验者三', description: '体验者三的 UI 职责与这项任务相符。下一步会真实创建并分配待办。', action: '分配给体验者三', disabled: false };
  if (session.phase === 'handoff-ready') return { title: '到负责人侧完成待办', description: '下一步会在当前标签页切换到体验者三，并把真实复核结果放入其团队工作池。', action: '切换并准备结果', disabled: false };
  if (session.phase === 'completion-ready') return { title: '负责人确认完成', description: '完成记录已经真实写入工作池。下一步勾选待办，Agent 会核验成果并生成总结。', action: '勾选待办', disabled: false };
  if (session.phase === 'completion-wait') return { title: '正在核验完成证据', description: 'Agent 正在读取负责人上下文；只有找到完成证据，待办才会真正结束。', action: '等待总结', disabled: true };
  if (session.phase === 'done') return { title: '完整协作闭环已完成', description: '你刚才走完了真实问答、会前同步、任务推荐、分配和证据核验。', action: '结束演练', disabled: false };
  if (session.phase === 'error') return { title: '演练停在这里', description: session.error, action: '重试当前步骤', disabled: false };
  return { title: '演练进行中', description: '', action: waiting ? '请稍候' : '下一步', disabled: waiting };
}

export function TutorialController({ startSignal, state, data, view, routeId, busy, onNavigate, onOpenTrialChat, onRefresh, onContext, onSwitchAccount, onTask }: Props) {
  const [session,setSession]=useState<TutorialSession|null>(()=>restoreSession());
  const sessionRef=useRef<TutorialSession|null>(session);
  const [visible,setVisible]=useState(()=>{const restored=restoreSession();return !!restored&&!restored.paused;});
  const [acting,setActing]=useState(false);
  const [pointer,setPointer]=useState<{left:number;top:number}|null>(null);
  const lastStart=useRef(startSignal);
  const preparing=useRef(false);
  const driverRef=useRef<Driver|null>(null);
  const reducedMotion=useMemo(()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches,[]);

  useEffect(()=>{
    driverRef.current=driver({
      animate:!reducedMotion,
      duration:reducedMotion?0:220,
      overlayOpacity:.5,
      overlayColor:getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim(),
      allowClose:false,
      allowKeyboardControl:false,
      disableActiveInteraction:true,
      smoothScroll:!reducedMotion,
      stagePadding:8,
      stageRadius:10,
      showButtons:[],
      waitForElement:4000,
      skipMissingElement:false,
      popoverClass:'accord-tutorial-driver-popover',
    });
    return()=>{driverRef.current?.destroy();driverRef.current=null;};
  },[reducedMotion]);

  const replaceSession=(next:TutorialSession|null)=>{sessionRef.current=next;setSession(next);if(next)sessionStorage.setItem(STORAGE_KEY,JSON.stringify(next));else sessionStorage.removeItem(STORAGE_KEY);};
  const update=(values:Partial<TutorialSession>)=>{const current=sessionRef.current;if(current)replaceSession({...current,...values});};
  const fail=(error:unknown,recovery:Recovery,errorStep:number)=>update({phase:'error',error:error instanceof Error?error.message:'当前步骤没有完成，请重试。',recovery,errorStep});
  const releasePage=()=>window.dispatchEvent(new Event('accord:tutorial-release'));
  const pause=()=>{driverRef.current?.destroy();setPointer(null);releasePage();update({paused:true});setVisible(false);};
  const finish=()=>{driverRef.current?.destroy();setPointer(null);releasePage();setVisible(false);replaceSession(null);};

  const prepare=async()=>{
    if(preparing.current)return;
    preparing.current=true;
    setActing(true);
    try{
      setVisible(true);
      replaceSession({...emptySession(),phase:'intro'});
      onNavigate('workspace');
      onContext(true);
      await api('/tutorial/prepare',{});
      if(state.me!==TRIAL_ONE)await onSwitchAccount(TRIAL_ONE);else await onRefresh();
      onContext(true);
      update({prepared:true,phase:'intro',error:''});
    }catch(error){fail(error,'prepare',1);}finally{preparing.current=false;setActing(false);}
  };

  useEffect(()=>{
    if(!startSignal||startSignal===lastStart.current)return;
    lastStart.current=startSignal;
    if(session){update({paused:false});setVisible(true);return;}
    void prepare();
  // startSignal is an explicit user action; the other values are read at that moment.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[startSignal]);

  useEffect(()=>{
    if(session?.phase==='intro'&&!session.prepared&&!session.paused&&!acting&&!preparing.current)void prepare();
  // This only resumes an interrupted idempotent prepare after a reload.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[session?.phase,session?.prepared,acting]);

  const target=useMemo(()=>session?phaseTarget(session):'',[session]);
  useEffect(()=>{
    const guide=driverRef.current;
    if(!guide||!session||!visible||!target){guide?.destroy();return;}
    const timer=window.setTimeout(()=>{
      const element=document.querySelector(target)||document.querySelector('#main-content');
      if(element)guide.highlight({element,disableActiveInteraction:true});
    },120);
    return()=>window.clearTimeout(timer);
  },[session?.phase,session?.taskId,target,visible,state.me,view,routeId,data?.thread.id]);

  const cue=async(selector:string)=>{
    let element:HTMLElement|null=null;
    for(let attempt=0;attempt<40;attempt+=1){
      element=document.querySelector(selector) as HTMLElement|null;
      if(element)break;
      await sleep(100);
    }
    if(!element)throw new Error('当前操作按钮仍在载入，请稍后重试。');
    element.scrollIntoView({block:'center',inline:'nearest',behavior:reducedMotion?'auto':'smooth'});
    await sleep(reducedMotion?20:140);
    const box=element.getBoundingClientRect();
    setPointer({left:Math.min(window.innerWidth-38,Math.max(8,box.right-24)),top:Math.min(window.innerHeight-44,Math.max(8,box.top+Math.min(box.height/2,30)))});
    element.classList.add('tutorial-action-cue');
    await sleep(reducedMotion?120:660);
    element.classList.remove('tutorial-action-cue');
    setPointer(null);
  };

  const openChat=async()=>{
    if(state.me!==TRIAL_ONE)await onSwitchAccount(TRIAL_ONE);
    const threadId=await onOpenTrialChat(TRIAL_TWO);
    if(!threadId)throw new Error('没有打开体验者二的 Agent 对话，请重试。');
    const draftId=`accord.draft.${TRIAL_ONE}.${threadId}`;
    await cue('[data-tour="composer"]');
    sessionStorage.setItem(draftId,tutorialCopy.chat);
    await waitForAction('composer.fill',{draftId,value:tutorialCopy.chat,sourceIds:[TUTORIAL_SOURCE_BY_MEMBER[TRIAL_TWO]]});
    update({phase:'chat-ready',chatThreadId:threadId,error:''});
  };

  const openFlow=async(assignment:boolean)=>{
    const nextView:View=assignment?'assignments':'meetings';
    const prompt=assignment?tutorialCopy.assignment:tutorialCopy.meeting;
    onNavigate(nextView);
    await cue(assignment?'[data-tour="flow-open-assignment"]':'[data-tour="flow-open-meeting"]');
    await waitForAction('flow.fill',{assignment,kind:'sync',prompt,memberIds:[...TUTORIAL_TRIAL_ACCOUNT_IDS],sourceIds:[...TUTORIAL_FLOW_SOURCE_IDS]});
    update({phase:assignment?'assignment-ready':'meeting-ready',error:''});
  };

  const switchAndPrepareCompletion=async()=>{
    const next=await onSwitchAccount(TRIAL_THREE);
    onContext(true);
    const task=next.tasks.find(item=>item.id===session?.taskId&&item.assignee_id===TRIAL_THREE);
    if(!task)throw new Error('体验者三尚未收到这项真实待办，请返回任务分配步骤重试。');
    await cue('[data-tour="work-pool"]');
    let resourceId=session?.completionResourceId||'';
    if(!resourceId){
      const existing=next.documents.find(document=>document.unit_id===TRIAL_THREE&&document.title===tutorialCopy.completionTitle&&document.body.includes(task.id));
      if(existing)resourceId=existing.id;
      else{
        const body=`# Accord 工作台 1440 宽度复核完成记录\n\n关联待办：${task.id}\n\n## 复核结论\n\n已在 1440 × 900 浏览器视口完成 Accord 工作台最终复核。聊天主区、右侧待办与工作池、资料来源展开和关键按钮均可见，无横向滚动；输入框、任务勾选与来源入口没有遮挡。\n\n## 已检查\n\n- 同事 Agent 回答与来源能够在同一消息流查看。\n- 右侧待办与工作池层级清楚，任务可直接勾选。\n- 同步会和任务推荐的处理中、完成与失败状态均可辨认。\n- 页面没有倒计时弹窗，发送、分配与完成均由用户点击阶段主按钮触发。`;
        const result=await command<{id:string}>('/resources',{title:tutorialCopy.completionTitle,body,scope:'team',resource_ids:[]});
        resourceId=result.id;
      }
      update({completionResourceId:resourceId});
    }
    await sleep(700);
    await onRefresh();
    update({phase:'completion-ready',error:''});
  };

  const retry=async()=>{
    if(!session)return;
    if(session.recovery==='prepare'){await prepare();return;}
    if(session.recovery==='chat'){await openChat();return;}
    if(session.recovery==='meeting'){
      if(session.meetingFlowId){
        const flow=await api<FlowDetail>(`/flows/${session.meetingFlowId}`);
        if(flow.status==='closed'){
          const issue=flowEvidenceIssue(flow);
          if(!issue){update({phase:'meeting-result',error:''});return;}
          update({meetingFlowId:''});await openFlow(false);return;
        }
        if(['queued','running','summarizing'].includes(flow.status)){update({phase:'meeting-wait',error:''});return;}
        await command(`/flows/${session.meetingFlowId}/retry`,{});update({phase:'meeting-wait',error:''});
      }else await openFlow(false);
      return;
    }
    if(session.recovery==='assignment'){
      if(session.assignmentFlowId){
        const flow=await api<FlowDetail>(`/flows/${session.assignmentFlowId}`);
        if(flow.status==='assigned'&&flow.task_id){update({phase:'handoff-ready',taskId:flow.task_id,taskThreadId:flow.thread_id,error:''});return;}
        if(['queued','running','summarizing'].includes(flow.status)){update({phase:'assignment-wait',error:''});return;}
        if(flow.status==='ready'&&!flowEvidenceIssue(flow)&&flow.result.candidates?.some(candidate=>candidate.person_id===TRIAL_THREE)){update({phase:'assignment-result',error:''});return;}
        await command(`/flows/${session.assignmentFlowId}/retry`,{});update({phase:'assignment-wait',error:''});
      }else await openFlow(true);
      return;
    }
    if(session.recovery==='handoff'){await switchAndPrepareCompletion();return;}
    if(session.completionFlowId){
      const flow=await api<FlowDetail>(`/flows/${session.completionFlowId}`);
      if(flow.status==='needs_input')await command(`/task-summaries/${flow.id}/reply`,{body:'1440 × 900 工作台复核已经完成，完成记录已放入团队工作池，请读取该完成记录后重新核验。'});
      else if(flow.status==='error')await command(`/task-summaries/${flow.id}/retry`,{});
      else if(flow.status==='cancelled'){update({phase:'completion-ready',completionFlowId:'',error:''});return;}
      else throw new Error('整理状态已经变化，请稍后再试。');
      update({phase:'completion-wait',error:''});
    }else update({phase:'completion-ready',error:''});
  };

  const advance=async()=>{
    if(!session||acting||busy)return;
    if(session.phase==='done'){finish();return;}
    setActing(true);
    try{
      if(session.phase==='error'){await retry();return;}
      if(session.phase==='intro'){await openChat();return;}
      if(session.phase==='chat-ready'){
        const threadId=session.chatThreadId;
        const draftId=`accord.draft.${TRIAL_ONE}.${threadId}`;
        const baseline=(data?.messages||[]).filter(message=>message.conversation_id===threadId&&message.from_kind==='agent'&&message.meta.status==='done').map(message=>message.id);
        await cue('[data-tour="composer-send"]');
        await runTutorialAction('composer.send',{draftId,expectedValue:tutorialCopy.chat,sourceIds:[TUTORIAL_SOURCE_BY_MEMBER[TRIAL_TWO]]});
        update({phase:'chat-wait',chatBaseline:baseline,error:''});
        return;
      }
      if(session.phase==='chat-result'){await openFlow(false);return;}
      if(session.phase==='meeting-ready'){
        await cue('[data-tour="flow-submit"]');
        const result=await runTutorialAction('flow.submit',{assignment:false,expectedPrompt:tutorialCopy.meeting,kind:'sync',memberIds:[...TUTORIAL_TRIAL_ACCOUNT_IDS],sourceIds:[...TUTORIAL_FLOW_SOURCE_IDS]});
        update({phase:'meeting-wait',meetingFlowId:result.id,error:''});
        return;
      }
      if(session.phase==='meeting-result'){await openFlow(true);return;}
      if(session.phase==='assignment-ready'){
        await cue('[data-tour="flow-submit"]');
        const result=await runTutorialAction('flow.submit',{assignment:true,expectedPrompt:tutorialCopy.assignment,kind:'assignment',memberIds:[...TUTORIAL_TRIAL_ACCOUNT_IDS],sourceIds:[...TUTORIAL_FLOW_SOURCE_IDS]});
        update({phase:'assignment-wait',assignmentFlowId:result.id,error:''});
        return;
      }
      if(session.phase==='assignment-result'){
        await cue(`[data-tour-person="${TRIAL_THREE}"]`);
        const result=await runTutorialAction('flow.choose',{flowId:session.assignmentFlowId,memberIds:[TRIAL_THREE]});
        if(!result.task_id)throw new Error('任务已提交但没有返回真实待办，请重试。');
        update({phase:'handoff-ready',taskId:result.task_id,taskThreadId:result.thread_id,error:''});
        return;
      }
      if(session.phase==='handoff-ready'){
        await switchAndPrepareCompletion();
        return;
      }
      if(session.phase==='completion-ready'){
        const task=state.tasks.find(item=>item.id===session.taskId&&item.assignee_id===state.me);
        if(!task)throw new Error('当前页面还没有同步到这项待办，请刷新后重试。');
        await cue(`[data-tour-task="${task.id}"]`);
        const result=await onTask(task);
        if(!result.ok||!result.flowId)throw new Error('待办没有开始整理，请查看页面提示后重试。');
        update({phase:'completion-wait',completionFlowId:result.flowId,taskThreadId:result.threadId||session.taskThreadId,error:''});
      }
    }catch(error){
      const recovery:Recovery=session.phase.startsWith('chat')?'chat':session.phase.startsWith('meeting')?'meeting':session.phase.startsWith('assignment')?'assignment':session.phase==='handoff-ready'?'handoff':'completion';
      fail(error,recovery,phaseStep(session));
    }finally{setActing(false);}
  };

  useEffect(()=>{
    if(!session||session.phase!=='chat-wait'||state.me!==TRIAL_ONE||data?.thread.id!==session.chatThreadId)return;
    const fresh=(data.messages||[]).filter(message=>message.conversation_id===session.chatThreadId&&message.from_kind==='agent'&&!session.chatBaseline.includes(message.id));
    const failed=[...fresh].reverse().find(message=>['error','cancelled'].includes(message.meta.status||''));
    if(failed){fail(new Error(failed.meta.error||'Agent 回答没有完成，请重试。'),'chat',2);return;}
    const completed=[...fresh].reverse().find(message=>message.meta.status==='done'&&message.body.trim());
    if(completed){
      const returnedSources=new Set([...(completed.sources||[]),...(completed.meta.context_sources||[]).map(source=>source.id)]);
      if(!returnedSources.has(TUTORIAL_SOURCE_BY_MEMBER[TRIAL_TWO])){fail(new Error('Agent 已回答，但没有返回体验者二指定共享资料的可核验来源。请重试本步骤。'),'chat',2);return;}
      update({phase:'chat-result',error:''});
    }
  // The message revision is the only changing input required by this transition.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[session?.phase,session?.chatThreadId,data?.messages]);

  useEffect(()=>{
    if(!session||session.phase!=='completion-ready'||state.me!==TRIAL_THREE||session.completionFlowId)return;
    const task=state.tasks.find(item=>item.id===session.taskId&&item.assignee_id===TRIAL_THREE);
    const flow=(state.flows||[]).find(item=>item.kind==='task_summary'&&item.task_id===session.taskId&&item.status!=='cancelled'&&(item.status!=='closed'||task?.status==='done'));
    if(flow)update({phase:'completion-wait',completionFlowId:flow.id,taskThreadId:flow.thread_id||session.taskThreadId,error:''});
  // Reattach a task-summary committed just before a browser refresh.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[session?.phase,session?.taskId,session?.completionFlowId,state.me,state.tasks,state.flows]);

  useEffect(()=>{
    if(!session)return;
    const phase=session.phase;
    const flowId=phase==='meeting-wait'?session.meetingFlowId:(phase==='assignment-wait'||phase==='assignment-result')?session.assignmentFlowId:phase==='completion-wait'?session.completionFlowId:'';
    if(!flowId)return;
    let stopped=false;
    const check=async()=>{
      try{
        const flow=await api<FlowDetail>(`/flows/${flowId}`);
        if(stopped)return;
        if(flow.status==='error'){
          fail(new Error(flow.error||'Agent 整理没有完成，请重试。'),phase.startsWith('meeting')?'meeting':phase.startsWith('assignment')?'assignment':'completion',phaseStep(session));
          return;
        }
        if(phase==='meeting-wait'&&flow.status==='closed'){
          const issue=flowEvidenceIssue(flow);
          if(issue){update({phase:'error',error:issue,recovery:'meeting',errorStep:3,meetingFlowId:''});return;}
          update({phase:'meeting-result',error:''});
        }
        if(phase==='assignment-wait'&&flow.status==='ready'){
          const issue=flowEvidenceIssue(flow);
          if(issue){fail(new Error(issue),'assignment',4);return;}
          const matched=flow.result.candidates?.some(candidate=>candidate.person_id===TRIAL_THREE);
          if(matched)update({phase:'assignment-result',error:''});
          else fail(new Error('这次真实推荐没有包含体验者三。系统已停住，不会伪造推荐；可以重新收集一次。'),'assignment',4);
        }
        if(phase==='assignment-result'&&flow.status==='ready'){
          const issue=flowEvidenceIssue(flow);
          if(issue){fail(new Error(issue),'assignment',4);return;}
        }
        if((phase==='assignment-wait'||phase==='assignment-result')&&flow.status==='assigned'&&flow.task_id)update({phase:'handoff-ready',taskId:flow.task_id,taskThreadId:flow.thread_id,error:''});
        if(phase==='completion-wait'&&flow.status==='closed'){
          await onRefresh();
          if(!stopped)update({phase:'done',error:''});
        }
        if(phase==='completion-wait'&&flow.status==='cancelled')fail(new Error('本次完成核验已取消，待办仍保持未完成。重试后可以重新勾选。'),'completion',5);
        if(phase==='completion-wait'&&flow.status==='needs_input')fail(new Error('Agent 还缺一条可核验的完成信息。重试会把完成说明写入当前整理，再次核验。'),'completion',5);
      }catch(error){if(!stopped&&error instanceof Error&&!error.message.includes('暂时无法连接'))fail(error,phase.startsWith('meeting')?'meeting':phase.startsWith('assignment')?'assignment':'completion',phaseStep(session));}
    };
    void check();const timer=window.setInterval(()=>void check(),1500);
    return()=>{stopped=true;window.clearInterval(timer);};
  // State transitions replace the polling effect.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[session?.phase,session?.meetingFlowId,session?.assignmentFlowId,session?.completionFlowId]);

  useEffect(()=>{
    if(!session||!visible||acting)return;
    let cancelled=false;
    const restore=async()=>{
      try{
        const expectedAccount=phaseAccount(session);
        if(state.me!==expectedAccount){
          releasePage();
          await onSwitchAccount(expectedAccount);
          return;
        }
        if(session.phase==='intro'){
          if(view!=='workspace'||routeId){onNavigate('workspace');return;}
          onContext(true);return;
        }
        if(session.phase.startsWith('chat')){
          if(view!=='chat'||routeId!==session.chatThreadId){onNavigate('chat',session.chatThreadId);return;}
        }
        if(session.phase==='chat-ready'){
          const draftId=`accord.draft.${TRIAL_ONE}.${session.chatThreadId}`;
          sessionStorage.setItem(draftId,tutorialCopy.chat);
          await waitForAction('composer.fill',{draftId,value:tutorialCopy.chat,sourceIds:[TUTORIAL_SOURCE_BY_MEMBER[TRIAL_TWO]]});
        }
        if(session.phase==='meeting-ready'){
          if(view!=='meetings'||routeId){onNavigate('meetings');return;}
          await waitForAction('flow.fill',{assignment:false,kind:'sync',prompt:tutorialCopy.meeting,memberIds:[...TUTORIAL_TRIAL_ACCOUNT_IDS],sourceIds:[...TUTORIAL_FLOW_SOURCE_IDS]});
        }
        if(session.phase==='assignment-ready'){
          if(view!=='assignments'||routeId){onNavigate('assignments');return;}
          await waitForAction('flow.fill',{assignment:true,kind:'sync',prompt:tutorialCopy.assignment,memberIds:[...TUTORIAL_TRIAL_ACCOUNT_IDS],sourceIds:[...TUTORIAL_FLOW_SOURCE_IDS]});
        }
        if((session.phase==='meeting-wait'||session.phase==='meeting-result')&&session.meetingFlowId&&(view!=='meetings'||routeId!==session.meetingFlowId)){onNavigate('meetings',session.meetingFlowId);return;}
        if((session.phase==='assignment-wait'||session.phase==='assignment-result'||session.phase==='handoff-ready')&&session.assignmentFlowId&&(view!=='assignments'||routeId!==session.assignmentFlowId)){onNavigate('assignments',session.assignmentFlowId);return;}
        if(session.phase==='completion-ready'||session.phase==='completion-wait'||session.phase==='done'){
          if(session.taskThreadId&&(view!=='workspace'||routeId!==session.taskThreadId)){onNavigate('workspace',session.taskThreadId);return;}
          onContext(true);
        }
        if(session.phase==='error'){
          if(session.recovery==='chat'&&session.chatThreadId&&(view!=='chat'||routeId!==session.chatThreadId)){onNavigate('chat',session.chatThreadId);return;}
          if(session.recovery==='meeting'&&session.meetingFlowId&&(view!=='meetings'||routeId!==session.meetingFlowId)){onNavigate('meetings',session.meetingFlowId);return;}
          if(session.recovery==='assignment'&&session.assignmentFlowId&&(view!=='assignments'||routeId!==session.assignmentFlowId)){onNavigate('assignments',session.assignmentFlowId);return;}
          if((session.recovery==='completion'||session.recovery==='handoff')&&session.taskThreadId&&(view!=='workspace'||routeId!==session.taskThreadId)){onNavigate('workspace',session.taskThreadId);return;}
          if(session.recovery==='completion'||session.recovery==='handoff')onContext(true);
        }
      }catch(error){if(!cancelled&&error instanceof Error&&!error.message.includes('载入'))fail(error,session.recovery,phaseStep(session));}
    };
    const timer=window.setTimeout(()=>void restore(),160);
    return()=>{cancelled=true;window.clearTimeout(timer);};
  // Restore only when the current surface or persisted phase changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[session?.phase,session?.chatThreadId,session?.meetingFlowId,session?.assignmentFlowId,session?.taskThreadId,session?.recovery,state.me,view,routeId,visible]);

  if(!session||!visible)return null;
  const content=phaseContent(session);
  const disabled=content.disabled||acting||busy;
  return <>
    <aside className="tutorial-panel" aria-live="polite" aria-label="教学演练">
      <div className="tutorial-panel-meta"><span>步骤 {phaseStep(session)}/5</span><button type="button" onClick={pause}>退出</button></div>
      <strong>{content.title}</strong>
      <p>{content.description}</p>
      <Button data-tour="tutorial-next" size="sm" disabled={disabled} onClick={()=>void advance()}>{(acting||content.disabled)&&session.phase!=='error'?<LoadingIcon size={14}/>:null}{acting?'正在执行':content.action}</Button>
    </aside>
    {pointer&&<span className="tutorial-pointer" style={{left:pointer.left,top:pointer.top}} aria-hidden="true">☝</span>}
  </>;
}
