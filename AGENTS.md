# ACU Private Workflow

- Canonical source: `/root/jerry/acu-private`, remote `jerry0012009/acu-private`.
  Keep main clean; use an owned task worktree under `/root/jerry/.worktrees`.
- Before production changes read the canonical Router `deploy-acu` skill and
  `docs/operations/acontext-blue-green.md`. API/Core use A/B slots controlled by
  `deploy/alpha/acontext-slots.py` in Router. Do not use historical
  `deploy/core_release.py apply`, direct Docker restart or Compose replacement.
- Core prompts and lifecycle code belong here. Build from reviewed fixed
  baseline, record full private revision and image ID, do not pull mutable latest
  to combine upstream upgrades with deployment changes.
- Run prompt/lifecycle tests and real isolated learning/drain canary for queue
  changes. Candidate Core starts standby; old delivered work, ACKs and usage
  callbacks must complete before retirement. Never activate both slots manually.
- Production env authority is Router `deploy/alpha/.env`. Generated private
  Compose/control files are not another editable source; never print secrets.
- State containers with historical acceptance names are production data stores,
  not disposable tests. Do not remove data or replay historical pending records.
- Documentation/skill changes do not require rebuilding or restarting apps.
