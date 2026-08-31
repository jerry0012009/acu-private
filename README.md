# ACU Private Acontext Adapter

This repository is the single source of truth for ACU's Acontext Core
integration:

- Acontext Core wrapper image;
- Learning Space-bound prompt sets;
- Task, Distillation, and Skill Learner patches;
- Core prompt inspection and usage reporting.

Repository boundaries:

```text
acu-private
  Acontext Core adapter and learning internals

acu-router
  Private ACU orchestration, ingress, persistence, relay, and admin APIs

acu-frontend
  Private ACU administration UI
```

Acontext prompt definitions and Core patches must remain in this repository
and must not be copied into `acu-router`. The deployed Acontext Core image is
built from [`acontext-core-inspection`](acontext-core-inspection).
