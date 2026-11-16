import { useState, type FormEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../api/auth';
import { useDataSource } from '../data/source';
import { errorMessage } from '../api/client';
import { Button, Field } from '../components/ui';

function LoginNetworkBg() {
  const nodes = [
    [8, 22], [22, 12], [38, 30], [55, 14], [70, 26], [86, 16],
    [14, 55], [30, 68], [48, 52], [64, 64], [80, 50], [92, 70],
    [20, 86], [42, 90], [60, 82], [78, 88],
  ];
  const edges: [number, number][] = [
    [0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [0, 6], [6, 7], [2, 8],
    [8, 9], [4, 10], [10, 11], [7, 12], [7, 13], [8, 13], [9, 14], [10, 15], [14, 15],
  ];
  return (
    <svg className="login-bg" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid slice" aria-hidden>
      {edges.map(([a, b], i) => (
        <line key={i} x1={nodes[a][0]} y1={nodes[a][1]} x2={nodes[b][0]} y2={nodes[b][1]} stroke="#1C3038" strokeWidth={0.25} />
      ))}
      {nodes.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={i % 4 === 0 ? 0.8 : 0.45} fill={i % 4 === 0 ? '#3D8A81' : '#24404A'} />
      ))}
    </svg>
  );
}

export default function LoginPage() {
  const { login } = useAuth();
  const { setMode } = useDataSource();
  const navigate = useNavigate();
  const location = useLocation();
  const next = (location.state as { next?: string } | null)?.next ?? '/app';

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const health = useQuery({
    queryKey: ['health-public'],
    queryFn: async () => {
      const res = await fetch('/health');
      if (!res.ok) throw new Error('unavailable');
      return res.json();
    },
    retry: 0,
    staleTime: 30_000,
  });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username.trim(), password);
      setMode('live');
      navigate(next, { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const openDemo = () => {
    setMode('demo');
    navigate('/app', { replace: true });
  };

  return (
    <div className="login-page">
      <LoginNetworkBg />
      <div className="login-card">
        <div className="login-brand">
          <img src="/favicon.svg" alt="" width={40} height={40} />
          <div>
            <div className="shell-brand-name">Revizor</div>
            <div className="shell-brand-sub">Command Center · вход</div>
          </div>
        </div>

        <p className="small muted" style={{ marginBottom: 'var(--sp-5)' }}>
          {health.data
            ? 'Сервер доступен. Войдите под учётной записью оператора.'
            : health.isError
              ? 'Сервер недоступен. Войдите, когда соединение восстановится, или откройте демо-режим.'
              : 'Проверяем доступность сервера…'}
        </p>

        <form className="login-form" onSubmit={submit}>
          {error && (
            <div className="login-error" role="alert">
              {error}
            </div>
          )}
          <Field label="Имя пользователя">
            <input
              className="input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
              autoFocus
            />
          </Field>
          <Field label="Пароль">
            <input
              className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </Field>
          <Button type="submit" variant="primary" loading={busy} block>
            Войти
          </Button>
        </form>

        <div className="login-alt">
          <Button variant="default" block onClick={openDemo}>
            Демо-режим без сервера
          </Button>
          <p className="faint" style={{ fontSize: 'var(--text-micro)' }}>
            Демо-режим использует синтетические данные и помечен DEMO. Для живого API в dev-окружении
            seeded-доступ: <span className="mono">demo-operator / demo-operator-password</span>.
          </p>
          <a className="link small" href="/">
            ← Вернуться к презентации продукта
          </a>
        </div>
      </div>
    </div>
  );
}