# Acontext Core Inspection Wrapper

This image wraps the upstream Acontext Core image and adds one read-only,
fixed-file inspection endpoint:

```text
GET /internal/inspection/prompts
```

It exposes only the three prompt modules used by the current Core runtime.
It does not accept a path, write files, or expose user data.

The image adds a small ACU-specific policy to the upstream Task, Skill
distillation, and Skill learner prompts:

- dissatisfaction can make a pending/running task eligible for the existing
  failure-distillation path;
- learning focuses on contextual user preferences and trajectory experience,
  not technical SOPs;
- preference documents use a short Markdown format, preserve experience IDs,
  and reconcile conflicting conditional preferences;
- generated content follows the user's dominant language.

The upstream tools, queues, and storage remain unchanged. The wrapper only
patches the existing task-agent source to dispatch an explicitly marked
`user_dissatisfaction` context for learning.

It also records each successful upstream Core LLM completion in the existing
Core PostgreSQL database table `acontext_llm_usage_ledger`. The ledger is
best-effort and never blocks a Core task.
