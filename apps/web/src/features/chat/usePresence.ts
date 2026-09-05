import { useEffect, useRef } from 'react';
import { api, type State } from '../../shared/api';
import { newOperationId } from '../../shared/browser';

export function usePresence(state:State|null,threadId:string|null,chat:boolean) {
  const current=useRef({thread_id:threadId || '',surface:chat ? 'chat' : 'work'});
  current.current={thread_id:threadId || '',surface:chat ? 'chat' : 'work'};
  const enabled=state?.activity_preferences?.automatic;
  const uid=state?.me;
  useEffect(()=> {
    if (!enabled || !uid) return;
    const key='accord.presence.'+uid;
    let client_id=sessionStorage.getItem(key);
    if (!client_id) { client_id=newOperationId(); sessionStorage.setItem(key,client_id); }
    let inFlight=false;
    const update=async()=> {
      if (inFlight) return; inFlight=true;
      try { await api('/presence',{...current.current,client_id,active:!document.hidden && document.hasFocus()}); }
      catch { /* A stale heartbeat expires automatically; ordinary requests surface connection errors. */ }
      finally { inFlight=false; }
    };
    const handle=()=>void update();
    handle(); const timer=setInterval(handle,25000);
    document.addEventListener('visibilitychange',handle);window.addEventListener('focus',handle);window.addEventListener('blur',handle);
    return ()=> { clearInterval(timer);document.removeEventListener('visibilitychange',handle);window.removeEventListener('focus',handle);window.removeEventListener('blur',handle); };
  },[enabled,uid]);
}
