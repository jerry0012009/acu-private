# ACU Private Acontext Adapter

This repository is the single source of truth for the Acontext Core application
used by ACU Private. Ordinary Private ACU Learning and the film POC
run in this same service and are separated by Learning Space-bound prompts and
data, not by separate Acontext deployments.

- Acontext Core wrapper image;
- Learning Space-bound prompt sets;
- Task, Distillation, and Skill Learner patches;
- Core prompt inspection and usage reporting.
- Versioned Core model configuration and isolated, Core-only release tooling
  in [`deploy`](deploy/README.md).

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

Production API/Core use blue/green application slots; read the canonical Router
runbook `/root/jerry/claw-router/docs/operations/acontext-blue-green.md` and
`deploy-acu` skill before release. `deploy/core_release.py` is historical
single-instance model-release tooling, not the current publishing path.
