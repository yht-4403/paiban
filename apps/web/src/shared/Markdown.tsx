import { lazy, Suspense } from 'react';
const Content = lazy(() => import('./MarkdownContent'));
export function Markdown({ children }: { children: string }) {
  return <Suspense fallback={<div className="message-body">{children}</div>}><Content>{children}</Content></Suspense>;
}
