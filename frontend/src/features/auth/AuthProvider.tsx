import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  type ReactNode,
} from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"

import { ApiError } from "@/api/client"

import * as authApi from "./api"
import type { AuthState, OperatorEnvironment, OperatorInfo } from "./types"

type AuthContextValue = {
  auth: AuthState
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refetch: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

const AUTH_QUERY_KEY = ["auth", "me"] as const

async function loadAuthState(): Promise<AuthState> {
  try {
    const response = await authApi.fetchMe()
    return {
      status: "authenticated",
      operator: response.operator,
      environment: response.environment,
    }
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return { status: "unauthenticated" }
    }
    throw error
  }
}

type AuthProviderProps = {
  children: ReactNode
}

export function AuthProvider({ children }: AuthProviderProps) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const { data, isLoading, refetch } = useQuery({
    queryKey: AUTH_QUERY_KEY,
    queryFn: loadAuthState,
    staleTime: 60_000,
    retry: false,
    refetchOnWindowFocus: false,
  })

  const loginMutation = useMutation({
    mutationFn: async ({
      username,
      password,
    }: {
      username: string
      password: string
    }) => authApi.login(username, password),
    onSuccess: (response) => {
      if (response.operator && response.environment) {
        const nextState: AuthState = {
          status: "authenticated",
          operator: response.operator,
          environment: response.environment,
        }
        queryClient.setQueryData<AuthState>(AUTH_QUERY_KEY, nextState)
      } else {
        void queryClient.invalidateQueries({ queryKey: AUTH_QUERY_KEY })
      }
    },
  })

  const logoutMutation = useMutation({
    mutationFn: authApi.logout,
    onSuccess: () => {
      queryClient.clear()
      navigate("/login", { replace: true })
    },
  })

  const auth: AuthState = isLoading
    ? { status: "loading" }
    : (data ?? { status: "unauthenticated" })

  const login = useCallback(
    async (username: string, password: string) => {
      await loginMutation.mutateAsync({ username, password })
    },
    [loginMutation],
  )

  const logout = useCallback(async () => {
    await logoutMutation.mutateAsync()
  }, [logoutMutation])

  const value = useMemo<AuthContextValue>(
    () => ({
      auth,
      login,
      logout,
      refetch: async () => {
        await refetch()
      },
    }),
    [auth, login, logout, refetch],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider")
  }
  return context
}

export function useOperator(): OperatorInfo | undefined {
  const { auth } = useAuth()
  return auth.status === "authenticated" ? auth.operator : undefined
}

export function useEnvironment(): OperatorEnvironment | undefined {
  const { auth } = useAuth()
  return auth.status === "authenticated" ? auth.environment : undefined
}
