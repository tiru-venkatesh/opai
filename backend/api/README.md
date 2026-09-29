# API architecture

`main.py` remains the compatibility entry point for the existing public API.
New agent/workflow logic should be introduced behind these boundaries:

- `permissions/` — ownership and authorization
- `validators/` — request validation
- `routes/` — incremental route extraction from `main.py`
- `auth/` — authentication adapters

This keeps the current API stable while allowing a gradual route-by-route split.
