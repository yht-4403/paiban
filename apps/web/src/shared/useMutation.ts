import { useRef, useState } from 'react';
import { command } from './api';

export function useMutation(refresh?: () => Promise<void>) {
  const lock=useRef(false); const [busy,setBusy]=useState(false); const [error,setError]=useState('');
  const mutate=async <T,>(path:string,body:Record<string,unknown>={}) => {
    if (lock.current) return undefined;
    lock.current=true; setBusy(true); setError('');
    try {
      const result=await command<T>(path,body);
      try { await refresh?.(); } catch { setError('操作已保存，页面同步暂时中断。'); }
      return result;
    } catch (error) { setError((error as Error).message); return undefined; }
    finally { lock.current=false; setBusy(false); }
  };
  return {busy,error,setError,mutate};
}
