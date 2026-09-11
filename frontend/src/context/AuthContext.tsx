"use client";

/**
 * Intra AI — Authentication Context & Session Provider
 *
 * Provides reactive authentication state across the entire client application.
 * Synchronizes with cookie and localStorage token stores, handles 401 interceptions,
 * and maintains role-aware session data.
 */

import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  useMemo,
} from "react";
import { useRouter } from "next/navigation";
import type { User, UserRole } from "@/types";
import type {
  LoginCredentials,
  SignupPayload,
  AuthTokenResponse,
  AuthUserResponse,
} from "@/types/api";
import { loginApi, signupApi, refreshTokenApi } from "@/lib/api/auth";
import { registerUnauthorizedHandler } from "@/lib/api/client";
import {
  getAuthToken,
  setAuthToken,
  clearAuthToken,
  isTokenExpired,
  decodeAuthToken,
  AUTH_STORAGE_KEY,
  AUTH_USER_KEY,
} from "@/lib/auth/token-storage";

export interface AuthContextType {
  user: User | null;
  token: string | null;
  role: UserRole | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: LoginCredentials) => Promise<AuthTokenResponse>;
  signup: (payload: SignupPayload) => Promise<AuthTokenResponse>;
  logout: (redirectUrl?: string) => void;
  refreshSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function mapAuthUserToUser(resUser: AuthUserResponse): User {
  return {
    id: resUser.id,
    email: resUser.email,
    name: resUser.name,
    role: resUser.role,
    avatar_url: resUser.avatar_url,
    created_at: resUser.created_at,
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const role = useMemo<UserRole | null>(() => {
    if (user?.role) return user.role;
    const decoded = decodeAuthToken(token || undefined);
    return decoded?.role || null;
  }, [user, token]);

  const isAuthenticated = useMemo(() => {
    return Boolean(token && !isTokenExpired(token));
  }, [token]);

  const logout = useCallback(
    (redirectUrl: string = "/login") => {
      clearAuthToken();
      setUser(null);
      setToken(null);
      if (typeof window !== "undefined") {
        router.push(redirectUrl);
      }
    },
    [router]
  );

  const refreshSession = useCallback(async () => {
    const currentToken = getAuthToken();
    if (!currentToken || isTokenExpired(currentToken)) {
      logout();
      return;
    }

    try {
      const response = await refreshTokenApi();
      setAuthToken(response.access_token, response.user.role);
      const mappedUser = mapAuthUserToUser(response.user);
      setUser(mappedUser);
      setToken(response.access_token);
      try {
        localStorage.setItem(AUTH_USER_KEY, JSON.stringify(mappedUser));
      } catch {
        // Ignore
      }
    } catch {
      // If refresh fails due to 401 or network error
      logout();
    }
  }, [logout]);

  // Initial session restoration
  useEffect(() => {
    queueMicrotask(() => {
      const existingToken = getAuthToken();
      if (existingToken && !isTokenExpired(existingToken)) {
        setToken(existingToken);

        // Restore user from localStorage if present
        try {
          const cachedUserStr = localStorage.getItem(AUTH_USER_KEY);
          if (cachedUserStr) {
            const cachedUser = JSON.parse(cachedUserStr) as User;
            setUser(cachedUser);
          }
        } catch {
          // Ignore
        }

        // Proactively refresh the session to get updated user data
        refreshSession().finally(() => {
          setIsLoading(false);
        });
      } else {
        clearAuthToken();
        setIsLoading(false);
      }
    });
  }, [refreshSession]);

  // Subscribe to 401 unauthorized signals from apiClient
  useEffect(() => {
    const unregister = registerUnauthorizedHandler(() => {
      logout();
    });
    return () => {
      unregister();
    };
  }, [logout]);

  // Synchronize across browser tabs
  useEffect(() => {
    function handleStorageChange(e: StorageEvent) {
      if (e.key === AUTH_STORAGE_KEY) {
        if (!e.newValue) {
          // Logged out in another tab
          setUser(null);
          setToken(null);
          router.push("/login");
        } else {
          // Logged in or token updated in another tab
          setToken(e.newValue);
          const cachedUserStr = localStorage.getItem(AUTH_USER_KEY);
          if (cachedUserStr) {
            try {
              setUser(JSON.parse(cachedUserStr));
            } catch {
              // Ignore
            }
          }
        }
      }
    }

    window.addEventListener("storage", handleStorageChange);
    return () => window.removeEventListener("storage", handleStorageChange);
  }, [router]);

  const login = useCallback(
    async (credentials: LoginCredentials): Promise<AuthTokenResponse> => {
      const response = await loginApi(credentials);
      setAuthToken(response.access_token, response.user.role);
      const mappedUser = mapAuthUserToUser(response.user);
      setUser(mappedUser);
      setToken(response.access_token);
      try {
        localStorage.setItem(AUTH_USER_KEY, JSON.stringify(mappedUser));
      } catch {
        // Ignore
      }
      return response;
    },
    []
  );

  const signup = useCallback(
    async (payload: SignupPayload): Promise<AuthTokenResponse> => {
      const response = await signupApi(payload);
      setAuthToken(response.access_token, response.user.role);
      const mappedUser = mapAuthUserToUser(response.user);
      setUser(mappedUser);
      setToken(response.access_token);
      try {
        localStorage.setItem(AUTH_USER_KEY, JSON.stringify(mappedUser));
      } catch {
        // Ignore
      }
      return response;
    },
    []
  );

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        role,
        isAuthenticated,
        isLoading,
        login,
        signup,
        logout,
        refreshSession,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
