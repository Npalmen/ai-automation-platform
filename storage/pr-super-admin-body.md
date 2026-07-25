## Summary
- Allow `super_admin` to inherit admin operator permissions for usage, system status, onboarding, Google OAuth, operator actions, and the create-customer UI flow
- Use frontend `isRoleAllowed` hierarchy instead of direct admin/operations equality checks
- Add focused backend and frontend regression tests for the three reported pilot symptoms

## Reported symptoms fixed
1. Missing Ny kund button for super_admin
2. Usage and Systemstatus pages returning 403 / error state
3. Operator actions blocked with insufficient permission message

## Scope
- No general RBAC refactor
- No change to operations/read_only product policy
- super_admin-only endpoints remain exclusive

## Test plan
- [x] Focused backend tests: usage, system status, operator actions, onboarding smoke, Google OAuth
- [x] Frontend lint, typecheck, onboarding role tests, contracts, build
- [ ] Pilot deploy + super_admin smoke after merge
