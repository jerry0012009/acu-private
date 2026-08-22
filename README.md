# acu-private

Private ACU user-facing service.

This repository is the third component of the Private ACU MVP:

- `acu-router` owns request accounting, Observer/Advisor, Learning, Acontext integration, and the protected internal Advisor data API.
- `acu-frontend` owns the authenticated `/dashboard/acu-advisor` page and user feedback controls.
- `acu-private` owns the user-facing API/service boundary that connects the authenticated Console request to the Router data API.

The repository intentionally does not duplicate Router observation, learning, persistence, or LLM calls. It also is not a fork of `new-api`.

## Current State

The Router and Frontend slices are already implemented:

- Router: `81aca33`
- Frontend: `d28dcda6`

Before adding the first service code here, one deployment contract must be fixed: how the authenticated Console identity reaches `acu-private`.

## Required Identity Contract

The service must receive a verified `newapiUserId` from an existing authenticated reverse proxy or Console backend. It must not accept a browser-supplied user id as authorization.

The remaining implementation choice is intentionally small:

1. A trusted internal header set by the authenticated proxy; or
2. A signed internal identity token exchanged between the Console edge and `acu-private`.

After this is decided, the first service endpoint is limited to:

```text
GET  /api/user/self/acu-advisor
POST /api/user/self/acu-advisor/:advisorId/feedback
```

Both endpoints will forward the verified account identity to the Router internal API and will not contain another Advisor database or LLM implementation.
