import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

export type DataMode = 'live' | 'demo';
const MODE_KEY = 'revizor.mode';

interface DataSourceValue {
  mode: DataMode;
  setMode: (mode: DataMode) => void;
  isDemo: boolean;
}

const DataSourceContext = createContext<DataSourceValue | null>(null);

export function DataSourceProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<DataMode>(() => {
    const stored = localStorage.getItem(MODE_KEY);
    return stored === 'demo' ? 'demo' : 'live';
  });

  const setMode = useCallback((next: DataMode) => {
    localStorage.setItem(MODE_KEY, next);
    setModeState(next);
  }, []);

  const value = useMemo(() => ({ mode, setMode, isDemo: mode === 'demo' }), [mode, setMode]);
  return <DataSourceContext.Provider value={value}>{children}</DataSourceContext.Provider>;
}

export function useDataSource(): DataSourceValue {
  const ctx = useContext(DataSourceContext);
  if (!ctx) throw new Error('useDataSource outside DataSourceProvider');
  return ctx;
}