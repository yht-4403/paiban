import { Button } from '@tutti-os/ui-system';
import { MessageSquareTextIcon } from '@tutti-os/ui-system/icons';
import type { Thread } from '../../shared/api';
import { Empty } from '../../shared/ui';

export function TrashPage({ threads, busy, onRestore }: { threads: Thread[]; busy: boolean; onRestore: (id: string) => void }) {
  return <div className="content-page"><div className="page-intro"><h1>回收站</h1></div>
    {threads.map(thread => <div className="trash-row" key={thread.id}><MessageSquareTextIcon size={16} /><span>{thread.title}</span><Button variant="secondary" size="sm" disabled={busy} onClick={() => onRestore(thread.id)}>恢复</Button></div>)}
    {!threads.length && <Empty icon={<MessageSquareTextIcon size={24} />} title="回收站为空" />}
  </div>;
}
