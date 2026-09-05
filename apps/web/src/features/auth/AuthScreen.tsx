import { useCallback, useEffect, useState } from 'react';
import { Avatar, Button } from '@tutti-os/ui-system';
import { ArrowRightIcon, LoadingIcon } from '@tutti-os/ui-system/icons';
import { api, setSessionToken, type AuthAccounts, type AuthSelection, type AuthStatus, type FixedAccount, type FixedAccountKind } from '../../shared/api';

const accountGroups: { kind: FixedAccountKind; label: string }[] = [
  { kind: 'demo', label: '演示成员' },
  { kind: 'trial', label: '体验账号' },
];

export function AuthScreen({ status, onLogin }: { status: AuthStatus; onLogin: () => Promise<void> }) {
  const [accounts, setAccounts] = useState<FixedAccount[]>([]);
  const [workspace, setWorkspace] = useState(status.workspace);
  const [loading, setLoading] = useState(true);
  const [selecting, setSelecting] = useState('');
  const [error, setError] = useState('');

  const loadAccounts = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await api<AuthAccounts>('/auth/accounts');
      setAccounts(result.accounts);
      setWorkspace(result.workspace || status.workspace);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setLoading(false);
    }
  }, [status.workspace]);

  useEffect(() => { void loadAccounts(); }, [loadAccounts]);

  const selectAccount = async (account: FixedAccount) => {
    if (selecting) return;
    setSelecting(account.id);
    setError('');
    try {
      const result = await api<AuthSelection>('/auth/select', { account_id: account.id });
      setSessionToken(result.session_token);
      await onLogin();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setSelecting('');
    }
  };

  return <main className="login-screen identity-login-screen">
    <section className="login-card identity-picker" aria-labelledby="auth-title">
      <span className="wordmark">accord<span>·</span></span>
      <div className="identity-heading">
        <h1 id="auth-title">选择身份</h1>
        <p>{workspace}</p>
      </div>

      {loading ? <div className="identity-loading" role="status"><LoadingIcon size={18} /><span>正在载入身份</span></div> : <div className="identity-groups">
        {accountGroups.map(group => {
          const options = accounts.filter(account => account.kind === group.kind);
          if (!options.length) return null;
          return <section className="identity-group" key={group.kind} aria-labelledby={`identity-${group.kind}`}>
            <h2 id={`identity-${group.kind}`}>{group.label}</h2>
            <div className="identity-options">
              {options.map(account => <Button
                key={account.id}
                variant="ghost"
                className="identity-option"
                disabled={!!selecting}
                aria-busy={selecting === account.id}
                onClick={() => void selectAccount(account)}
              >
                <Avatar label={account.name} initial={account.name[0]} size={38} />
                <span className="identity-name"><strong>{account.name}</strong><small>{account.agent_name}</small></span>
                {selecting === account.id ? <LoadingIcon size={16} /> : <ArrowRightIcon size={16} />}
              </Button>)}
            </div>
          </section>;
        })}
      </div>}

      {error && <div className="identity-error" role="alert"><span>{error}</span>{!accounts.length && <Button variant="secondary" size="sm" onClick={() => void loadAccounts()}>重试</Button>}</div>}
    </section>
  </main>;
}
