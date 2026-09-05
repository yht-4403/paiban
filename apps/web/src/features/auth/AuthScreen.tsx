import { useState } from 'react';
import { Button, Input } from '@tutti-os/ui-system';
import { ArrowRightIcon, LoadingIcon } from '@tutti-os/ui-system/icons';
import { api, type AuthStatus } from '../../shared/api';

export function AuthScreen({ status, onLogin }: { status: AuthStatus; onLogin: () => Promise<void> }) {
  const [joining, setJoining] = useState(false);
  const [name, setName] = useState(''); const [email, setEmail] = useState('');
  const [password, setPassword] = useState(''); const [workspace, setWorkspace] = useState('');
  const [invite, setInvite] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const creating = status.needs_setup; const registering = creating || joining;
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); if (busy) return; setBusy(true); setError('');
    try {
      await api(`/auth/${creating ? 'setup' : joining ? 'register' : 'login'}`, { email, password, name, workspace, invite });
      setPassword(''); await onLogin();
    } catch (error) { setError((error as Error).message); } finally { setBusy(false); }
  };
  return <main className="login-screen"><section className="login-card" aria-labelledby="auth-title">
    <span className="wordmark">accord<span>·</span></span>
    <h1 id="auth-title">{creating ? '创建你的工作空间' : joining ? `加入 ${status.workspace}` : `登录 ${status.workspace}`}</h1>
    <p>{creating ? '从你的账号开始，邀请同事一起协作。' : joining ? '使用创建者提供的邀请码，建立你的账号。' : '继续你的工作、协作和待办。'}</p>
    <form onSubmit={event => void submit(event)} className="auth-form">
      {creating && <div className="form-field"><label htmlFor="workspace">工作空间名称</label><Input id="workspace" value={workspace} onChange={e => setWorkspace(e.target.value)} maxLength={80} required autoFocus autoComplete="organization" /></div>}
      {registering && <div className="form-field"><label htmlFor="name">你的姓名</label><Input id="name" value={name} onChange={e => setName(e.target.value)} maxLength={40} required autoComplete="name" /></div>}
      <div className="form-field"><label htmlFor="email">邮箱</label><Input id="email" type="email" value={email} onChange={e => setEmail(e.target.value)} required maxLength={254} autoComplete="username" autoFocus={!registering} /></div>
      <div className="form-field"><label htmlFor="password">密码</label><Input id="password" type="password" value={password} onChange={e => setPassword(e.target.value)} minLength={registering ? 12 : 1} maxLength={128} required autoComplete={registering ? 'new-password' : 'current-password'} />{registering && <p>至少 12 位，请使用专属于此账号的密码。</p>}</div>
      {joining && <div className="form-field"><label htmlFor="invite">邀请码</label><Input id="invite" value={invite} onChange={e => setInvite(e.target.value)} required autoComplete="off" maxLength={100} /></div>}
      {error && <p role="alert" className="form-error">{error}</p>}
      <Button type="submit" disabled={busy} aria-busy={busy} className="auth-submit">{busy ? <LoadingIcon /> : <ArrowRightIcon />}{creating ? '创建并进入' : joining ? '加入工作空间' : '登录'}</Button>
    </form>
    {!creating && <Button variant="ghost" onClick={() => { setJoining(!joining); setError(''); setPassword(''); }} disabled={busy}>{joining ? '已有账号，去登录' : '使用邀请码加入'}</Button>}
  </section></main>;
}
