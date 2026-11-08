"""sentinel_api — FastAPI facade over the existing Python security services.

Issue #96 (M1.2). Wraps, never rewrites:
  identity (RBAC), incident_records, scope_matrix, incident_chat,
  containment_policy, containment_executor, response_audit, investigator.

All state is in-memory and ephemeral — restart loses everything.
"""
