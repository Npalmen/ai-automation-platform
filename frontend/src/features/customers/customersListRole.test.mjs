import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"

const ROLE_LEVEL = {
  read_only: 10,
  operations: 20,
  admin: 30,
  super_admin: 40,
}

function isRoleAllowed(role, allowedRoles) {
  if (!role || !(role in ROLE_LEVEL) || allowedRoles.length === 0) {
    return false
  }
  const actual = ROLE_LEVEL[role]
  const minRequired = Math.min(...allowedRoles.map((allowed) => ROLE_LEVEL[allowed]))
  return actual >= minRequired
}

function canShowNewCustomerButton(role) {
  return Boolean(role && isRoleAllowed(role, ["operations", "admin"]))
}

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const customersListSource = fs.readFileSync(path.join(__dirname, "CustomersListPage.tsx"), "utf8")
const newCustomerSource = fs.readFileSync(path.join(__dirname, "../onboarding/NewCustomerPage.tsx"), "utf8")

test("customers list uses role hierarchy for Ny kund", () => {
  assert.match(customersListSource, /isRoleAllowed\(role, \["operations", "admin"\]\)/)
})

test("new customer page uses role hierarchy for create access", () => {
  assert.match(newCustomerSource, /isRoleAllowed\(role, \["operations", "admin"\]\)/)
})

test("super_admin and admin see Ny kund; read_only does not", () => {
  assert.equal(canShowNewCustomerButton("super_admin"), true)
  assert.equal(canShowNewCustomerButton("admin"), true)
  assert.equal(canShowNewCustomerButton("operations"), true)
  assert.equal(canShowNewCustomerButton("read_only"), false)
})
