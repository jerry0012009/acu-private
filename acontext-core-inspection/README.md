# Acontext Core Inspection Wrapper

This image wraps the upstream Acontext Core image and adds one read-only,
fixed-file inspection endpoint:

```text
GET /internal/inspection/prompts
```

It exposes the three upstream prompt modules and the ACU learning prompt
definitions used by the current Core runtime.
It does not accept a path, write files, or expose user data.

The image binds prompt behavior to Acontext Learning Spaces:

- dissatisfaction can make a pending/running task eligible for the existing
  failure-distillation path;
- the Learning Space configured by `ACU_FILM_LEARNING_SPACE_ID` uses an
  independent film Task, Distillation, and Skill Learner prompt set;
- all other Learning Spaces retain the pre-film Private ACU prompts;
- a film `SelectionExperience` can be submitted as text-only or as one text
  plus multiple images;
- film learning keeps multiple conditional claims from one experience and
  updates topic-level Quality Skills;
- learning focuses on contextual user preferences and trajectory experience,
  not technical SOPs;
- preference documents use a short Markdown format, preserve experience IDs,
  and reconcile conflicting conditional preferences;
- generated content follows the user's dominant language.

Prompt selection uses the `learning_space_id` already present in the Task,
Distillation, and Skill Learner calls. The `film_preference_v1` message marker
remains evidence metadata and does not select prompts. The upstream queues and
storage remain unchanged.

The wrapper disables the OpenAI and Anthropic SDKs' built-in request retries.
The ACU Router relay owns the five-attempt provider failover budget, so a Core
completion cannot multiply retries across nested SDK and Router layers.

It also records each successful upstream Core LLM completion in the existing
Core PostgreSQL database table `acontext_llm_usage_ledger`. The ledger is
best-effort and never blocks a Core task. When the Router relay supplies an
`execution_profile_id`, the completion callback returns it to the Router so
the Router can apply its own Profile economics without moving billing logic
into Acontext.
