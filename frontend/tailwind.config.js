import { createRequire } from "node:module"
import { fileURLToPath } from "node:url"
import path from "node:path"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const require = createRequire(import.meta.url)
const profile = require(path.join(__dirname, "design/krowolf-ui-profile.json"))

const screens = Object.fromEntries(
  Object.entries(profile.breakpoints).map(([key, value]) => [key, `${value}px`]),
)

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: profile.typography.fontFamily.split(",").map((f) => f.trim()),
        mono: profile.typography.code.family.split(",").map((f) => f.trim()),
      },
      screens,
      spacing: Object.fromEntries(
        Object.entries(profile.spacing).map(([key, value]) => [key, value]),
      ),
      borderRadius: Object.fromEntries(
        Object.entries(profile.radii).map(([key, value]) => [key, value]),
      ),
      boxShadow: Object.fromEntries(
        Object.entries(profile.shadows).map(([key, value]) => [key, value]),
      ),
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        card: {
          DEFAULT: "var(--card)",
          foreground: "var(--card-foreground)",
        },
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--primary-foreground)",
        },
        secondary: {
          DEFAULT: "var(--secondary)",
          foreground: "var(--secondary-foreground)",
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          foreground: "var(--accent-foreground)",
        },
        destructive: {
          DEFAULT: "var(--destructive)",
          foreground: "var(--destructive-foreground)",
        },
        border: "var(--border)",
        input: "var(--input)",
        ring: "var(--ring)",
        page: "var(--kw-color-page)",
        surface: {
          DEFAULT: "var(--kw-color-surface-default)",
          subtle: "var(--kw-color-surface-subtle)",
        },
        "text-primary": "var(--kw-color-text-primary)",
        "text-secondary": "var(--kw-color-text-secondary)",
        "text-muted": "var(--kw-color-text-muted)",
        brand: {
          DEFAULT: "var(--kw-color-brand-primary)",
          hover: "var(--kw-color-brand-primaryHover)",
          active: "var(--kw-color-brand-primaryActive)",
          subtle: "var(--kw-color-brand-primarySubtle)",
          border: "var(--kw-color-brand-primaryBorder)",
        },
        status: {
          success: "var(--kw-color-status-success)",
          warning: "var(--kw-color-status-warning)",
          danger: "var(--kw-color-status-danger)",
          critical: "var(--kw-color-status-critical)",
          information: "var(--kw-color-status-information)",
          neutral: "var(--kw-color-status-neutral)",
          paused: "var(--kw-color-status-paused)",
          unknown: "var(--kw-color-status-unknown)",
        },
      },
      fontSize: Object.fromEntries(
        Object.entries(profile.typography)
          .filter(([, v]) => typeof v === "object" && v.size)
          .map(([key, v]) => [
            key.replace(/([A-Z])/g, "-$1").toLowerCase(),
            [v.size, { lineHeight: v.lineHeight, fontWeight: v.weight }],
          ]),
      ),
      maxWidth: {
        content: profile.sizing.contentMaxWidth,
      },
    },
  },
  plugins: [],
}
