export type Role = "read_only" | "operations" | "admin" | "super_admin"

export type OperatorEnvironment = "local" | "test" | "production"

export type OperatorInfo = {
  id: string
  display_name: string
  role: Role
}

export type AuthMeResponse = {
  authenticated: boolean
  operator: OperatorInfo
  environment: OperatorEnvironment
}

export type AuthLoginResponse = {
  ok: boolean
  mode: string
  operator?: OperatorInfo
  environment?: OperatorEnvironment
}

export type AuthState =
  | { status: "loading" }
  | { status: "unauthenticated" }
  | {
      status: "authenticated"
      operator: OperatorInfo
      environment: OperatorEnvironment
    }
