import { useAuth } from '../api/auth';
import { useDataSource } from '../data/source';

/* Права с учётом demo-режима: demo-operator — OPERATOR, мутации разрешены
   в пределах синтетического хранилища. */
export function usePermissions() {
  const { session, canMutate } = useAuth();
  const { isDemo } = useDataSource();
  return {
    canMutate: isDemo || canMutate,
    isDemo,
    username: isDemo ? 'demo-operator' : (session?.user.username ?? null),
    role: isDemo ? 'OPERATOR' : (session?.user.role ?? null),
  };
}