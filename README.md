# ACU Private Acontext Adapter

This repository is the single source of truth for the one Acontext Core
service used by ACU Private. Ordinary Private ACU Learning and the film POC
run in this same service and are separated by Learning Space-bound prompts and
data, not by separate Acontext deployments.

- Acontext Core wrapper image;
- Learning Space-bound prompt sets;
- Task, Distillation, and Skill Learner patches;
- Core prompt inspection and usage reporting.

Repository boundaries:

```text
acu-private
  the one Acontext Core service, adapter, and learning internals

acu-router
  Private ACU orchestration, ingress, persistence, relay, and admin APIs

acu-frontend
  Private ACU administration UI
```

Acontext prompt definitions and Core patches must remain in this repository
and must not be copied into `acu-router`. The deployed Acontext Core image is
built from [`acontext-core-inspection`](acontext-core-inspection).
