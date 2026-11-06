# Stage an existing Dispatcher instance and historical metrics (review)

This is an **offline, non-destructive preparation step** for returning from the
S03 attached-Strata trial to the operator's usual instance and ensemble policy.
It does not implement S07 LaunchPlan, reconfigure Strata, start an engine,
change the four AIW services, merge metrics histories, or modify authentication.

## Keep repository code and instance configuration separate

The operator's old Dispatcher **program source** should not be copied over
the reviewed program checkout. Git retains the new implementation and its
PR history. Only the authored user-owned instance configuration and historical
SQLite data need to come across.

An instance such as `Speedy_Win` has its own `instance.yaml` machine GUID,
`engines/`, `profiles/`, `ensembles/`, and `data/metrics.db`.
The public [versioned instance repository](https://github.com/SomeSunlight/Llama_Dispatcher_Speedy_Win)
contains the authored config; runtime data stays untracked. The
`3090.yaml` ensemble currently declares **four** aliases:
`sparringpartner`, proxy-only `agent`, `context_king`, `uncensored`.
Their llama.cpp-specific launch parameters must **not** be assumed to be valid
Strata launch arguments.

## Stage a copy without overwriting either installation

From a **review checkout** of the current Dispatcher (not the live checkout
while its services are running), after checking the original and target paths:

```powershell
uv run --frozen python scripts/stage_legacy_instance.py `
  --source-instance '<existing-versioned-Speedy_Win-instance-directory>' `
  --destination-checkout '<reviewed-Llama_Dispatcher-checkout>' `
  --destination-name Speedy_Win
```

That is a **preview only**. After verifying the plan and arranging a controlled
offline window, repeat with `--apply`.

The script refuses to overwrite any existing destination; for an independent
instance Git repository it requires no uncommitted changes and preserves its
Git metadata via a local clone. It copies the historical DB with SQLite's
online backup API (including committed WAL transactions) and checks the backup
integrity, without copying live `-wal`/`-shm` files. The old directory and
the new `Speedy_S03_Stage` database remain unchanged. It cannot merge their
rows or rewrite the old stable `machine_guid` silently.

The actual production database should ultimately be
`instances/Speedy_Win/data/metrics.db` if maintaining historical
`Speedy_Win` continuity is the goal. The S03 Stage database should remain
available as a **separate historical snapshot** pending an additive,
schema-aware and ID-safe import (S04/S06). Never merge SQLite databases by
copying one file over the other.

## S07 / external supervisor gate

The currently accepted S03 `--strata-config` and old
`serve --ensemble 3090` flags are mutually exclusive. The latter still
launches an internal llama.cpp process and therefore **violates** the new
single-external-supervisor architecture when used as the AIW managed
Dispatcher command. Do **not** change native AIW's Dispatcher command to
the old ensemble serve command as a shortcut.

Before switching active user clients, S07 needs a deterministic engine-aware
LaunchPlan compiled from the real instance ensemble/profile/engine YAML,
with `sparringpartner` and `agent` aliases and their distinct thinking/sampling
policies, compiled for the selected backend. AI Workstation owns each
engine process; Dispatcher attaches to it, authenticates individual clients,
applies policy and writes the selected instance's metrics. If a llama.cpp
backend is chosen alongside Strata, resource admission/VRAM checks and
distinct backend ports are required before both run concurrently.

A live switch also needs: offline configuration preview; separate S02
credentials still valid; preservation of the public HTTPS gateway; new
database backup/integrity checks; one model discovery plus short inference
from Goose and both Open WebUI installations; verified AIW-owned stop/start;
and the untouched legacy installation as rollback.
