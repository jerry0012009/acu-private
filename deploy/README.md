# Acontext Core Model Release

`core-config.yaml` is the versioned, non-secret authority for the Core model
and completion kwargs. All Core LLM workers use GPT-6.1 Sol with explicit
`medium` reasoning. The old `thinking: disabled` extension and `temperature`
are intentionally absent. No Router, Console, prompt, or queue code changes.

The deployed Core uses the existing ACU Chat relay. GPT-6.1 native OpenAI Chat
does not support tool calling; the configured Sub2API compatibility Profile
passed tool roundtrips. A full real-worker canary is therefore a release gate,
not an inference from a model directory or HTTP health check.

The host's existing Compose file and config mount remain runtime projections.
`core_release.py prepare` snapshots them privately, projects only
`core.environment.LLM_SIMPLE_MODEL`, freezes the current image, and copies the
versioned kwargs. It never copies the production `.env`; all Compose commands
use `/root/jerry/claw-router/deploy/alpha/.env`.

Release steps:

1. Commit and test the configuration and release tools in a task worktree.
2. Run `prepare`, then `prepare-canary`. Start the generated isolated Compose
   project with `--no-build --pull never --wait`. Its database, queues, storage,
   users and sessions are independent of production; only the LLM relay is shared.
3. Run `learning_canary.py` against that stack and save its successful JSON as
   `canary-success.json` in the prepared release directory. It checks actual
   Task, Distillation and Skill Learner completions, a written Skill, usage and
   execution Profile IDs. Synthetic resources are deleted after the check.
4. Start the frozen `core_release.py apply` through an independent host executor
   such as a systemd oneshot. It locks deployment, checks unchanged baseline
   configuration and protected containers, waits for idle Core queues, and
   recreates only `core`. It runs a second full canary in an isolated production
   user/space and restores the exact old files and image on failure.
5. Check `status.json`, model/kwargs, queue health and unchanged Router/Console/API
   container IDs. Remove only the canary project's containers and network.

Core recreation briefly pauses the learning worker; this is not a zero-downtime
Core rollout. Router and Console remain running. Do not run `compose down` on
the production project. Retain the private release manifest, old files and image.

Production acceptance and exact configuration/image evidence are recorded in
[the 2026-10-10 release report](2026-10-10-gpt61-medium-release.md).
