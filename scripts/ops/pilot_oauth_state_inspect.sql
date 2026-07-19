-- Latest integration oauth states for T_NIKLAS_DEMO_001 (no state values)
SELECT 'integration' AS source,
       left(state_id, 8) AS state_prefix,
       tenant_id,
       provider,
       operator_id IS NOT NULL AS operator_set,
       redirect_target,
       created_at,
       expires_at,
       consumed_at IS NOT NULL AS consumed,
       consumed_at,
       state_hash IS NOT NULL AS hash_record_exists,
       expires_at < now() AS expired
FROM integration_oauth_states
WHERE tenant_id = 'T_NIKLAS_DEMO_001'
ORDER BY created_at DESC
LIMIT 5;

SELECT 'onboarding' AS source,
       left(state_id, 8) AS state_prefix,
       tenant_id,
       provider,
       operator_id IS NOT NULL AS operator_set,
       redirect_target,
       created_at,
       expires_at,
       consumed_at IS NOT NULL AS consumed,
       consumed_at,
       state_hash IS NOT NULL AS hash_record_exists,
       expires_at < now() AS expired
FROM onboarding_oauth_states
WHERE tenant_id = 'T_NIKLAS_DEMO_001'
ORDER BY created_at DESC
LIMIT 5;
