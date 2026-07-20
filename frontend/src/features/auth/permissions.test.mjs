import assert from "node:assert/strict"
import test from "node:test"

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

const NAV_ITEMS = [
  { to: "/", label: "Översikt", allowedRoles: ["read_only", "operations", "admin"] },
  { to: "/needs-help", label: "Behöver hjälp", allowedRoles: ["read_only", "operations", "admin"] },
  { to: "/customers", label: "Kunder", allowedRoles: ["read_only", "operations", "admin"] },
  { to: "/incidents", label: "Incidenter", allowedRoles: ["read_only", "operations", "admin"] },
  { to: "/alerts", label: "Larm", allowedRoles: ["read_only", "operations", "admin"] },
  { to: "/usage", label: "Användning", allowedRoles: ["read_only", "operations", "admin"] },
  { to: "/system", label: "System", allowedRoles: ["operations", "admin"] },
]

function visibleNavItemsForRole(role) {
  return NAV_ITEMS.filter((item) => isRoleAllowed(role, item.allowedRoles))
}

test("role hierarchy inherits upward", () => {
  assert.equal(isRoleAllowed("super_admin", ["admin"]), true)
  assert.equal(isRoleAllowed("admin", ["operations"]), true)
  assert.equal(isRoleAllowed("operations", ["read_only"]), true)
  assert.equal(isRoleAllowed("read_only", ["operations"]), false)
  assert.equal(isRoleAllowed("operations", ["admin"]), false)
})

test("unknown role is fail-closed", () => {
  assert.equal(isRoleAllowed("hacker", ["read_only"]), false)
  assert.equal(isRoleAllowed(undefined, ["read_only"]), false)
})

test("super_admin sees full admin navigation", () => {
  const labels = visibleNavItemsForRole("super_admin").map((item) => item.label)
  assert.deepEqual(labels, [
    "Översikt",
    "Behöver hjälp",
    "Kunder",
    "Incidenter",
    "Larm",
    "Användning",
    "System",
  ])
})

test("admin and operations inherit expected nav items", () => {
  const adminLabels = visibleNavItemsForRole("admin").map((item) => item.label)
  const opsLabels = visibleNavItemsForRole("operations").map((item) => item.label)
  const readLabels = visibleNavItemsForRole("read_only").map((item) => item.label)

  assert.ok(adminLabels.includes("System"))
  assert.ok(opsLabels.includes("System"))
  assert.ok(!readLabels.includes("System"))
  assert.ok(readLabels.includes("Översikt"))
  assert.equal(readLabels.length, 6)
})

test("no known role gets empty navigation", () => {
  for (const role of ["read_only", "operations", "admin", "super_admin"]) {
    assert.ok(visibleNavItemsForRole(role).length > 0, role)
  }
})

test("super_admin inherits admin-only route policy minimum", () => {
  assert.equal(isRoleAllowed("super_admin", ["admin"]), true)
  assert.equal(isRoleAllowed("operations", ["admin"]), false)
})
