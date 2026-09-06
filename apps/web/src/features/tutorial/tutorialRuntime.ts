type TutorialStorage = Pick<Storage, 'getItem' | 'removeItem'>;

export function tutorialSnapshotOnPageLoad(storage: TutorialStorage, key: string) {
  storage.removeItem(key);
  return null;
}

export function completionNeedsFreshThread(error: string) {
  return [
    '资料不存在',
    '无权读取',
    '引用资料',
    '资料权限',
    '上下文引用链',
    '上下文已更新',
    '会话未共享',
    '内容不存在',
  ].some(fragment => error.includes(fragment));
}

export function completionRetryAction(status: string, error = '') {
  // A generic reply such as "重新核验" does not add completion evidence and can
  // leave the summary flow asking the same question forever. Rebuild the work
  // step instead; the checkbox itself is the user's completion confirmation.
  if (status === 'needs_input') return 'fresh-thread';
  if (status === 'error' && completionNeedsFreshThread(error)) return 'fresh-thread';
  if (status === 'error') return 'retry';
  if (status === 'cancelled' && completionNeedsFreshThread(error)) return 'fresh-thread';
  if (status === 'cancelled') return 'ready';
  if (status === 'closed') return 'advance';
  return 'unsupported';
}
