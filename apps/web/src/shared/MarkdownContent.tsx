import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function Markdown({ children }: { children: string }) {
  return <div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={{
    a: ({ children, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer">{children}</a>,
    img: ({ src, alt }) => <a href={typeof src === 'string' ? src : undefined} target="_blank" rel="noopener noreferrer">{alt || '查看图片'}</a>,
    table: ({ children }) => <div className="markdown-table"><table>{children}</table></div>,
  }}>{children}</ReactMarkdown></div>;
}
