# Active work schema

## Required files

```text
state.json
work.md
context.json
```

## `state.json`

Required top-level fields:

- `schema_version`
- `id`, `kind`, `title`, `slug`
- `lane`, `stage`, `status`
- `created_at`, `updated_at`
- `scope.paths`, `scope.symbols`, `scope.keywords`
- `links.model`, `links.knowledge`, `links.parent`, `links.children`
- `gate.status`, `gate.reasons`, `gate.question`
- `validation.commands`, `validation.last_result`

## `work.md`

Use a single aggregate. Fill only useful sections:

1. Intent and acceptance
2. Evidence / reproduction / characterization
3. Design or root cause
4. Plan
5. Changes and decisions
6. Verification and review
7. Promotion and closure

Micro lane may keep sections 2–4 to one or two bullets. High-risk work must include rollback/rollout.

## `context.json`

Tool-managed receipt map. Do not manually paste source text into it.
