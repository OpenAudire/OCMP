"""AI providers, prompts, and the privacy guard (ADR 042).

Every outbound call goes: prompt template + allow-listed fields -> ``privacy.prepare`` ->
``GuardedRequest`` -> a provider adapter. Adapters accept nothing else.
"""
