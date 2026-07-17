import { createRequire } from "node:module"
import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const require = createRequire(import.meta.url)
const profile = require(path.join(__dirname, "../design/krowolf-ui-profile.json"))

function flattenColors(colors, prefix = "") {
  const entries = []
  for (const [key, value] of Object.entries(colors)) {
    const name = prefix ? `${prefix}-${key}` : key
    if (typeof value === "string") {
      entries.push([`--kw-color-${name}`, value])
    } else {
      entries.push(...flattenColors(value, name))
    }
  }
  return entries
}

function cssVarBlock() {
  const lines = [":root {"]
  lines.push(`  --kw-font-family: ${profile.typography.fontFamily};`)

  for (const [name, value] of flattenColors(profile.colors)) {
    lines.push(`  ${name}: ${value};`)
  }

  for (const [key, value] of Object.entries(profile.spacing)) {
    lines.push(`  --kw-spacing-${key}: ${value};`)
  }

  for (const [key, value] of Object.entries(profile.radii)) {
    lines.push(`  --kw-radius-${key}: ${value};`)
  }

  for (const [key, value] of Object.entries(profile.shadows)) {
    lines.push(`  --kw-shadow-${key}: ${value};`)
  }

  for (const [key, value] of Object.entries(profile.sizing)) {
    const cssKey = key.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`)
    lines.push(`  --kw-size-${cssKey}: ${value};`)
  }

  lines.push(
    "  --background: var(--kw-color-page);",
    "  --foreground: var(--kw-color-text-primary);",
    "  --card: var(--kw-color-surface-default);",
    "  --card-foreground: var(--kw-color-text-primary);",
    "  --primary: var(--kw-color-brand-primary);",
    "  --primary-foreground: var(--kw-color-text-inverse);",
    "  --secondary: var(--kw-color-surface-subtle);",
    "  --secondary-foreground: var(--kw-color-text-primary);",
    "  --muted: var(--kw-color-surface-subtle);",
    "  --muted-foreground: var(--kw-color-text-muted);",
    "  --accent: var(--kw-color-brand-primarySubtle);",
    "  --accent-foreground: var(--kw-color-brand-primary);",
    "  --destructive: var(--kw-color-status-danger);",
    "  --destructive-foreground: var(--kw-color-text-inverse);",
    "  --border: var(--kw-color-border-default);",
    "  --input: var(--kw-color-border-default);",
    "  --ring: var(--kw-color-brand-primary);",
    "  --radius: var(--kw-radius-lg);",
    "}",
  )
  return lines.join("\n") + "\n"
}

const outPath = path.join(__dirname, "../src/styles/tokens.generated.css")
fs.mkdirSync(path.dirname(outPath), { recursive: true })
fs.writeFileSync(outPath, cssVarBlock(), "utf8")
console.log(`Wrote ${outPath}`)
