# Service playbook contract (digital coworker replies)

Version: `reply_service_playbook_v1`

Service playbooks define:

- supported business intents,
- operational next-step options,
- required facts per next step,
- question priority and budgets,
- forbidden email questions.

Implementation: `app/workflows/reply_quality/service_playbooks.py`

Playbooks are selected deterministically from `service_type` + `business_intent` before rendering.
