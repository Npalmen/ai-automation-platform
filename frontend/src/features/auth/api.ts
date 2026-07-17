import { get, post, postJson } from "@/api/client"

import type { AuthLoginResponse, AuthMeResponse } from "./types"

export function fetchMe(): Promise<AuthMeResponse> {
  return get<AuthMeResponse>("/auth/admin/me")
}

export function login(
  username: string,
  password: string,
): Promise<AuthLoginResponse> {
  return postJson<AuthLoginResponse>("/auth/admin/login", {
    username,
    password,
  })
}

export function logout(): Promise<{ ok: boolean }> {
  return post<{ ok: boolean }>("/auth/admin/logout")
}
