import {
  componentContracts,
  pageContracts,
  uiProfile,
} from "@/design/types"

function assertObject(value: unknown, label: string): asserts value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`Design contract invalid: ${label} must be an object`)
  }
}

export function assertUiProfile() {
  assertObject(uiProfile.profile, "profile")
  assertObject(uiProfile.colors, "colors")
  assertObject(uiProfile.typography, "typography")
  assertObject(uiProfile.breakpoints, "breakpoints")
  if (!Array.isArray(uiProfile.forbiddenPatterns) || uiProfile.forbiddenPatterns.length === 0) {
    throw new Error("Design contract invalid: forbiddenPatterns must be a non-empty array")
  }
  return uiProfile
}

export function loadComponentContracts() {
  for (const [name, contract] of Object.entries(componentContracts)) {
    if (!contract.purpose || typeof contract.implemented !== "boolean") {
      throw new Error(`Component contract invalid: ${name}`)
    }
  }
  return componentContracts
}

export function loadPageContracts() {
  for (const [name, contract] of Object.entries(pageContracts)) {
    if (!contract.purpose || !contract.desktopLayout || !contract.mobileLayout) {
      throw new Error(`Page contract invalid: ${name}`)
    }
  }
  return pageContracts
}

export function getDesignContracts() {
  return {
    uiProfile: assertUiProfile(),
    componentContracts: loadComponentContracts(),
    pageContracts: loadPageContracts(),
  }
}
