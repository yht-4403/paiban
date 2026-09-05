import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../shared/api';
import type { Topic } from './types';

export function useTopic(id:string) {
  const [topic,setTopic]=useState<Topic | null>(null); const [error,setError]=useState(''); const active=useRef(id); active.current=id;
  const refresh=useCallback(async(signal?:AbortSignal)=> {
    const next=await api<Topic>(`/topics/${id}`,undefined,signal);
    if (!signal?.aborted && active.current===id) { setTopic(next); setError(''); }
  },[id]);
  useEffect(()=> {
    setTopic(null); const controller=new AbortController(); let loading=false;
    const update=async()=> { if (loading) return; loading=true; try { await refresh(controller.signal); } catch(error) { if (!controller.signal.aborted) setError((error as Error).message); } finally { loading=false; } };
    void update(); const timer=setInterval(()=> { if (!document.hidden) void update(); },1000);
    return()=> { controller.abort(); clearInterval(timer); };
  },[refresh]);
  return {topic,error,refresh};
}
