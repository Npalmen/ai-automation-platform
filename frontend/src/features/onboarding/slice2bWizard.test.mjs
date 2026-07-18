import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const wizardPath = path.join(__dirname, "OnboardingWizardPage.tsx")
const apiPath = path.join(__dirname, "api.ts")
const mutationsPath = path.join(__dirname, "mutations.ts")
const panelPath = path.join(__dirname, "IntegrationsStepPanel.tsx")

const wizard = fs.readFileSync(wizardPath, "utf8")
const api = fs.readFileSync(apiPath, "utf8")
const mutations = fs.readFileSync(mutationsPath, "utf8")
const panel = fs.readFileSync(panelPath, "utf8")

const credentialPattern =
  /access_token|refresh_token|client_secret|authorization_code|api_key|password/i

assert.doesNotMatch(wizard, /READONLY_STEPS/, "integrations step must be editable")
assert.match(wizard, /IntegrationsStepPanel/, "wizard uses integrations panel")
assert.match(api, /\/integrations/, "slice2b integrations api")
assert.match(api, /external-routing/, "slice2b external routing api")
assert.match(api, /local-unlink/, "local unlink api")
assert.match(api, /unrequest/, "unrequest api")
assert.match(api, /external-routing-reset/, "external routing reset api")
assert.match(mutations, /invalidateSlice2bSideEffects/, "slice2b cache invalidation")
assert.match(mutations, /useLocalUnlinkIntegrationMutation/, "unlink mutation")
assert.match(mutations, /useUnrequestIntegrationMutation/, "unrequest mutation")
assert.match(mutations, /useResetExternalRoutingMutation/, "routing reset mutation")
assert.match(panel, /Verifiera/, "verify UX present")
assert.match(panel, /oauth/, "oauth return notice support")
assert.match(panel, /CriticalActionDialog/, "unlink requires critical dialog")
assert.match(panel, /Lokalt koppla bort/, "visma local unlink copy")
assert.match(panel, /Extern revoke/, "external revoke disclaimer")
assert.match(panel, /Ta bort begäran/, "unrequest button")
assert.match(panel, /Återställ till inherit/, "routing reset")
assert.match(panel, /authorization_required|Auktorisering krävs/, "authorization required copy")
assert.match(panel, /Gmail label scope/, "gmail section")
assert.match(panel, /gmail_classification/, "gmail classification from backend")
assert.match(panel, /platform_credential/, "gmail platform credential display")
assert.match(panel, /live_intake/, "gmail live intake display")
assert.match(panel, /ingen automatisk verifiering/i, "save does not auto-verify")
assert.doesNotMatch(panel, credentialPattern, "no credential fields in panel source")
assert.doesNotMatch(api, credentialPattern, "no credential fields in api source")

console.log("slice2bWizard.test.mjs: PASS")
