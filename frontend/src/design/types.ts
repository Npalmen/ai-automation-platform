import componentContracts from "../../design/component-contracts.json"
import pageContracts from "../../design/page-contracts.json"
import uiProfile from "../../design/krowolf-ui-profile.json"

export type StatusVariant = keyof typeof componentContracts.StatusBadge.variants
export type SeverityVariant = keyof typeof componentContracts.SeverityBadge.variants

export type ComponentContractName = keyof typeof componentContracts
export type PageContractName = keyof typeof pageContracts

export { componentContracts, pageContracts, uiProfile }
