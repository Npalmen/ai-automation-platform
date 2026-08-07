# R4 Attempt 4 thread reconciliation — 271a977

- generated_at: `2026-08-07T13:08:36Z`
- campaign_id: `99fa0b7f-1a6b-45aa-bec9-07f54f845de3`
- scenario: `PTB-DCQ-0000`
- classification: **THREAD_EVIDENCE_PROPAGATION_BUG**
- proceed_to_fix: **True**

## Provider sent object

- provider_message_id: `19fd…45d7`
- gmail_thread_id_redacted: `19fd…fb60`
- rfc_message_id_redacted: `caeka9pp…il.com`
- in_reply_to_redacted: `cafbf1sy…il.com`
- references_redacted: `<cafbf1syle3h+ze6rfwpckrjg2c=h1d_jrhorhmeowkxnyattlw@mail.gmail.com>`
- has_sent_label: `True`
- subject_token: `Re: KROWOLF-EVAL/f5089b6b-09bc-43f9-8877-f9a8d106ed11/PTB-DCQ-0000/1 | Offert solceller Uppsala`

## Inbound app-mailbox

- gmail_message_id_redacted: `19fd…fb60`
- gmail_thread_id_redacted: `19fd…fb60`
- rfc_message_id_redacted: `cafbf1sy…il.com`

## Delivered sender-mailbox reply

- gmail_message_id_redacted: `19fd…c011`
- rfc_message_id_redacted: `caeka9pp…il.com`
- in_reply_to_redacted: `cafbf1sy…il.com`
- references_redacted: `<cafbf1syle3h+ze6rfwpckrjg2c=h1d_jrhorhmeowkxnyattlw@mail.gmail.com>`
- subject_token: `Re: KROWOLF-EVAL/f5089b6b-09bc-43f9-8877-f9a8d106ed11/PTB-DCQ-0000/1 | Offert solceller Uppsala`

## Checks

- A_provider_rfc_present: True
- B_delivered_rfc_equals_provider_rfc: True
- C_in_reply_to_matches_inbound: True
- C_references_contains_inbound: True
- C_same_mailbox_gmail_thread: True
- thread_linkage_pass: True
- execution_reply_rfc_exposed_to_verifier: None
- verifier_used_rfc_as_thread_id_bug: True
