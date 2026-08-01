# Inbox Failure Taxonomy (Todo A)

> Authoritative taxonomy for PD-IQH-001 quality hardening. Maps failure families to routing and draft policy.

## Taxonomy

| Failure family | Typical signals | Threat class | Business intent | Customer draft | Routing |
|---|---|---|---|---|---|
| `benign_business_request` | Normal lead/support language | `trusted_business_content` | lead / existing_customer_support | Allowed (if eligibility passes) | continue |
| `irrelevant_message` | Newsletter, wrong recipient | `suspicious` or none | irrelevant | Denied | manual_review |
| `spam` | Lottery, massmail, SEO offers | `spam` | irrelevant | Denied | reject |
| `phishing` | Account verify, click-here | `phishing` | unknown | Denied | security_review |
| `prompt_injection` | Ignore instructions, system override | `prompt_injection` | unknown | Denied | security_review |
| `credential_request` | Send password, login credentials | `credential_request` | unknown | Denied | security_review |
| `payment_detail_change` | Bankgiro change, wire urgent | `payment_detail_change` | invoice | Denied | security_review |
| `urgent_safety` | Brand, burnt smell, sparks | content_risk | safety_incident | Denied | manual_review |
| `pricing_request` | Vad kostar, offert on price | none | pricing_request | Denied (forbidden topic) | hold |
| `booking_request` | Boka tid, schedule | none | booking_request | Denied (forbidden topic) | hold |
| `complaint` | Reklamation, missnöjd | content_risk | complaint | Denied | manual_review |
| `existing_customer_support` | Problem med installation | none | existing_customer_support | Context-dependent | manual_review |
| `supplier_message` | Order confirmation | none | supplier | Denied | observe |
| `invoice_document` | Faktura attached | none | invoice | Denied | manual_review |
| `data_privacy_request` | GDPR, radera uppgifter | sensitive_personal_data | data_privacy_request | Denied | manual_review |
| `unknown` | Empty, ambiguous | unknown | unknown | Denied | manual_review |
| `conflicting_intents` | Price + booking mixed | varies | mixed | Denied | manual_review |
| `malformed_message` | Empty body | unknown | unknown | Denied | manual_review |

## Component ownership per family

- **Trust/threat families** (`phishing`, `prompt_injection`, `spam`, etc.): `app/workflows/threat_assessment.py`
- **Business intent families**: `app/workflows/business_intent.py` + `classification_processor`
- **Safe-ack eligibility**: `app/workflows/safe_acknowledgement.py`
- **Extraction exclusion**: `app/workflows/safe_extraction.py`

## PTB-SEM-0024 mapping

| Dimension | Expected |
|---|---|
| Failure family | `phishing` + `prompt_injection` |
| Threat class | `phishing` (primary) or `prompt_injection` |
| Business intent | `unknown` (threat-blocked) |
| Customer draft | Forbidden |
| Routing | `security_review` |
