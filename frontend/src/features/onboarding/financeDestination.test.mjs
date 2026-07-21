import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const panelPath = path.join(__dirname, "FinanceDestinationPanel.tsx")
const integrationsPath = path.join(__dirname, "IntegrationsStepPanel.tsx")
const typesPath = path.join(__dirname, "types.ts")

const panel = fs.readFileSync(panelPath, "utf8")
const integrations = fs.readFileSync(integrationsPath, "utf8")
const types = fs.readFileSync(typesPath, "utf8")

assert.match(panel, /Ekonomidestination/, "finance destination heading")
assert.match(panel, /manual_accounting_routing/, "manual routing choice")
assert.match(panel, /visma_disposition|visma-disposition/, "visma disposition dialog")
assert.match(panel, /Ej aktuell/, "not_selected disposition copy")
assert.match(panel, /Valfri/, "selected_optional disposition copy")
assert.match(panel, /Visma-credential raderas inte/, "credential preservation copy")
assert.match(panel, /Routing-steget/, "routing step link")
assert.match(integrations, /FinanceDestinationPanel/, "integrations step embeds finance panel")
assert.match(types, /FinanceDestinationStatus/, "finance destination status type")
assert.match(types, /VismaDisposition/, "visma disposition type")

console.log("financeDestination.test.mjs: PASS")
