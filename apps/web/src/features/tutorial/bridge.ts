import { useEffect, useRef } from 'react';

export type ComposerFillPayload = { draftId: string; value: string; sourceIds: string[] };
export type FlowFillPayload = {
  assignment: boolean;
  kind: 'sync' | 'decision';
  prompt: string;
  memberIds: string[];
  sourceIds: string[];
};
export type FlowSubmitPayload = {
  assignment: boolean;
  expectedPrompt: string;
  kind: 'sync' | 'decision' | 'assignment';
  memberIds: string[];
  sourceIds: string[];
};
export type FlowChoosePayload = { flowId: string; memberIds: string[] };

type TutorialActions = {
  'composer.fill': (payload: ComposerFillPayload) => boolean | Promise<boolean>;
  'composer.send': (payload: { draftId: string; expectedValue: string; sourceIds: string[] }) => boolean | Promise<boolean>;
  'flow.fill': (payload: FlowFillPayload) => boolean | Promise<boolean>;
  'flow.submit': (payload: FlowSubmitPayload) => { id: string } | Promise<{ id: string }>;
  'flow.choose': (payload: FlowChoosePayload) => { thread_id: string; task_id?: string } | Promise<{ thread_id: string; task_id?: string }>;
};

export type TutorialActionName = keyof TutorialActions;
export type TutorialActionPayload<Name extends TutorialActionName> = Parameters<TutorialActions[Name]>[0];
export type TutorialActionResult<Name extends TutorialActionName> = Awaited<ReturnType<TutorialActions[Name]>>;
type TutorialHandler = (payload: unknown) => unknown | Promise<unknown>;

const handlers = new Map<TutorialActionName, TutorialHandler>();

/** Register the real action owned by the component currently on screen. */
export function useTutorialAction<Name extends TutorialActionName>(name: Name, handler: TutorialActions[Name]) {
  const latest = useRef(handler);
  latest.current = handler;
  useEffect(() => {
    const registered: TutorialHandler = payload => latest.current(payload as never);
    handlers.set(name, registered);
    return () => {
      if (handlers.get(name) === registered) handlers.delete(name);
    };
  }, [name]);
}

/** Invoke a registered React action without reaching into component internals or clicking brittle selectors. */
export async function runTutorialAction<Name extends TutorialActionName>(
  name: Name,
  payload: TutorialActionPayload<Name>,
): Promise<TutorialActionResult<Name>> {
  const handler = handlers.get(name);
  if (!handler) throw new Error('当前操作区还在载入，请稍后重试。');
  return await handler(payload) as TutorialActionResult<Name>;
}
