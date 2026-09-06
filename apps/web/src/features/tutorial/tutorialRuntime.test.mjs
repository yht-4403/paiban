import assert from 'node:assert/strict';
import test from 'node:test';
import {
  completionNeedsFreshThread,
  completionRetryAction,
  tutorialSnapshotOnPageLoad,
} from './tutorialRuntime.ts';

function memoryStorage(initial) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: key => values.get(key) ?? null,
    removeItem: key => values.delete(key),
  };
}

test('页面重载会丢弃上一次教学步骤', () => {
  const storage = memoryStorage({ tutorial: JSON.stringify({ phase: 'completion-two-wait' }) });
  assert.equal(tutorialSnapshotOnPageLoad(storage, 'tutorial'), null);
  assert.equal(storage.getItem('tutorial'), null);
});

test('资料权限失效时必须换一条全新工作台对话', () => {
  assert.equal(completionNeedsFreshThread('资料不存在或当前无权读取。'), true);
  assert.equal(completionNeedsFreshThread('引用资料已收回。'), true);
  assert.equal(completionNeedsFreshThread('模型暂时不可用。'), false);
});

test('补充信息后整理已经关闭时直接推进下一步', () => {
  assert.equal(completionRetryAction('closed'), 'advance');
});

test('缺少完成证据时重建工作步骤而不是要求用户回复 ok', () => {
  assert.equal(completionRetryAction('needs_input'), 'fresh-thread');
});
