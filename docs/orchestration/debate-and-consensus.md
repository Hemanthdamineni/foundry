# Debate and Consensus

Debate and consensus are not MVP runtime requirements.

If existing judge/debate code remains in the path, it must be bounded, optional,
and subordinate to deterministic validation:

- schema validation runs first;
- ToolGate remains authoritative for Coding/Testing;
- debate failure policy is explicit;
- debate cannot advance phase directly;
- debate cannot bypass rejected ToolGate results.

Mandatory multi-agent debate, adaptive agent selection, confidence analytics,
and consensus optimization are deferred.
