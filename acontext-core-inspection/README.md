# Acontext Core Inspection Wrapper

This image wraps the upstream Acontext Core image and adds one read-only,
fixed-file inspection endpoint:

```text
GET /internal/inspection/prompts
```

It exposes only the three prompt modules used by the current Core runtime.
It does not accept a path, write files, or expose user data.

The image also adds one short rule to the upstream Skill distillation and
learning prompts: generated Skill content follows the user's dominant
language. The upstream workflow and machine-readable formats remain unchanged.
