# Repository Organization

```
project-name/
├── .kiro/
│   ├── steering/         # global context (product, tech, structure)
│   └── specs/            # one subfolder per module, written before any code
├── backend/
│   └── app/modules/      # one subfolder per module group (see tech.md)
├── frontend/
├── docs/
│   ├── data-models/       # conceptual data models (CDM) per module
│   └── modules/           # functional documentation per module (10-section standard)
└── README.md
```

## Ownership
- **Backend** (`backend/`): Ousmane, Verdiane, NYNA Amanda — one module subfolder each.
- **Frontend** (`frontend/`): Belvira.

## Branches
- `main`: protected, no direct pushes.
- One branch per module: `feature/auth-catalogues`, `feature/measurements`,
  `feature/business-rules`, `feature/frontend-ui`.
- Pull request + review before merging into `main`.

## Before coding a module
1. Write the spec in `.kiro/specs/<module>/` (requirements → design → tasks).
2. Use Kiro to generate the code from the spec + steering context.
3. Document the module in `docs/modules/` following the team standard (10 sections).
4. Keep a screenshot of the Kiro session as proof of use.
