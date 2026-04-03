'use client';

import { useEffect, useRef } from 'react';
import { api } from '@/lib/api';
import { usePreferencesStore } from '@/stores/preferencesStore';

interface AuthProviderProps {
  children: React.ReactNode;
}

export default function AuthProvider({ children }: AuthProviderProps) {
  const token = usePreferencesStore((state) => state.token);
  const userId = usePreferencesStore((state) => state.userId);
  const isAuthenticated = usePreferencesStore((state) => state.isAuthenticated);
  const setAuthenticated = usePreferencesStore((state) => state.setAuthenticated);
  const hasCheckedUser = useRef(false);

  useEffect(() => {
    api.setAuthToken(token);
  }, [token]);

  useEffect(() => {
    if (!token || userId || !isAuthenticated || hasCheckedUser.current) {
      return;
    }

    hasCheckedUser.current = true;
    api
      .getCurrentUser()
      .then((user) => {
        setAuthenticated({ userId: user.id, token });
      })
      .catch(() => {
        api.setAuthToken(null);
        setAuthenticated(null);
      });
  }, [token, userId, isAuthenticated, setAuthenticated]);

  return children;
}
