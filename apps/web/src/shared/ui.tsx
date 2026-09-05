import type { ComponentProps, ReactNode } from 'react';
import { Button, DialogContent, DialogClose, Tooltip, TooltipContent, TooltipTrigger } from '@tutti-os/ui-system';
import { CloseIcon, LoadingIcon } from '@tutti-os/ui-system/icons';

export function IconButton({ label, children, onClick, active }: { label: string; children: ReactNode; onClick: () => void; active?: boolean }) {
  return <Tooltip><TooltipTrigger asChild><Button variant="ghost" size="icon" aria-label={label} aria-pressed={active} onClick={onClick}>{children}</Button></TooltipTrigger><TooltipContent>{label}</TooltipContent></Tooltip>;
}

export function Pending({ label = '正在载入工作台' }: { label?: string }) {
  return <div className="pending" role="status"><LoadingIcon size={18} /><span>{label}</span></div>;
}

export function Empty({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return <div className="empty-state"><div className="empty-symbol">{icon}</div><h2>{title}</h2><p>{children}</p></div>;
}

export function LocalizedDialogContent({children, ...props}: ComponentProps<typeof DialogContent>) {
  return <DialogContent {...props} showCloseButton={false}>{children}<DialogClose asChild><Button className="dialog-close" variant="ghost" size="icon-sm" aria-label="关闭弹窗"><CloseIcon /></Button></DialogClose></DialogContent>;
}
