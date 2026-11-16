import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, clearSession, getSession, setSession, unwrap, UNAUTHORIZED_EVENT, type Session } from './client';

interface AuthContextValue {
  session: Session | null;
  login: (username: string, password: string) => Promise<Session>;
  logout: () => Promise<void>;
  canMutate: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSessionState] = useState<Session | null>(() => getSession());

  useEffect(() => {
    const onUnauthorized = () => setSessionState(null);
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const token = await unwrap(
      api.POST('/api/v1/auth/login', { body: { username, password } }),
    );
    const s = setSession(token);
    setSessionState(s);
    return s;
  }, []);

  const logout = useCallback(async () => {
    try {
      if (getSession()) await api.POST('/api/v1/auth/logout');
    } catch {
      /* отзыв токена best-effort: локальная сессия всё равно очищается */
    }
    clearSession();
    setSessionState(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      login,
      logout,
      canMutate: session != null && ['ADMIN', 'OPERATOR', 'SERVICE'].includes(session.user.role),
    }),
    [session, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth outside AuthProvider');
  return ctx;
}