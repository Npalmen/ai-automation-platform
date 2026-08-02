# Information-value question policy

Version: `information_value_plan_v1`

Questions are selected by deterministic scoring:

```text
next-step relevance
+ profile priority
- customer effort
- sensitivity
- redundancy (already-known facts)
```

Rules:

- never ask for known facts,
- deprioritize `contact_name` unless operationally required,
- request `phone_or_email` only when contact channel is missing and next step needs it,
- enforce per-playbook question budget.

Implementation: `app/workflows/reply_quality/information_value.py`
