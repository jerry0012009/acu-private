# GPT-6.1 Sol Medium Production Release

Completed on 2026-10-10 at 05:31:52 UTC.

## Scope

- All Acontext Core default LLM calls use `gpt-6.1-sol`.
- Completion kwargs are exactly `reasoning_effort: medium`.
- `thinking: disabled` and `temperature: 0.3` are removed.
- Task, Distillation, Skill Learner, prompts and queue code are unchanged.
- Router, Console and the Acontext API were not rebuilt or restarted.
- Private ACU Observer/Advisor/satisfaction Judge configuration is unchanged.

This was a configuration release from `acu-private` revision
`077795be374f437928b77087dfda90698ced5fa2`, not a new Core application image.
The final documentation commit can advance main without another service replacement.

## Runtime

The Core image was retained:

```text
sha256:d5ff3183f7a58571e95aa10f0493d6064e8437f479852c1a651da61b20961d7a
```

New Core container: `0a5ee78640b3`, started at `2026-10-10T05:30:30.516227511Z`,
healthy with restart count zero after acceptance.

Configuration SHA-256:

```text
26e2a683bddafc4d0e10c7130338818defb36d02d185cc3c9c79337fc0b49a98
```

The runtime Compose model and mounted config are projections of
`deploy/core-config.yaml`. The production environment authority remains
`/root/jerry/claw-router/deploy/alpha/.env`; no second production environment
file was created.

Protected container IDs remained unchanged throughout replacement and acceptance:

| Service | Container ID Prefix |
| --- | --- |
| Router | `ac693f1bd2d2` |
| Console / New API | `61165a6ecc64` |
| Acontext API | `27c393ea9b65` |

Router still reports application revision
`6a06ff2333f6d912d851a5a36756a0221655efa5`.

## Acceptance

- 19 offline tests passed: 11 prompt regressions and 8 release/canary tests.
- Isolated full-stack canary: 12 completions, 27,262 input tokens, 1,432 output
  tokens, completed with two written Skills.
- Production canary in a generated, isolated user/space: 10 completions,
  22,032 input tokens, 1,401 output tokens, completed with two written Skills.
- Both canaries exercised `agent.task`, `distill.skill_learner` and
  `agent.skill_learner`, including real multi-round tool execution.
- All completions used `gpt-6.1-sol` and
  `managed-sub2api-55331a0217aa:gpt-6.1-sol:chat_completions`.
- Both Core configurations were inspected directly and matched explicit medium
  with no disabled-thinking or temperature override.
- Generated users, spaces, sessions and Skills were deleted after verification.
- The separate canary stack and its private network were removed; production
  queues had zero ready/unacknowledged messages and active consumers.

These results verify the configured Sub2API compatibility path, not native
OpenAI Chat tool support or every failover Profile.

## Rollout and Recovery

The frozen executor ran as systemd oneshot
`acu-private-core-gpt61-medium-20261010.service`, exited successfully and did not
need rollback. It waited for idle Core queues and recreated only `core` with
the retained image. Core processing paused during replacement; zero Core
downtime was not claimed. Router/Console/API remained healthy and retained IDs.

Private backups, the manifest, canary summaries and final `status.json` are
retained under:

```text
/root/jerry/deployment-releases/acu-core-gpt61-medium-20261010/
```

The exact previous Compose/config bytes and retained image remain available for
Core-only rollback. Do not use the dated September release's environment
snapshot for this deployment.
