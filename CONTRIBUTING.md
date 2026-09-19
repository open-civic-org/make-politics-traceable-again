# Contributing

Thank you for helping make elected representation in India more traceable.

## Principles

1. Work one phase at a time; do not implement later phases prematurely.
2. Never invent missing political data.
3. Preserve original source data; store SHA-256 and retrieval metadata.
4. Never overwrite historical records.
5. Never merge people using name alone.
6. Keep declarations separate from verified facts.
7. Keep individual actions separate from collective government actions.
8. Store provenance for every politically relevant fact.
9. Prefer official sources; flag unavailable data rather than guessing.
10. Do not build political scoring or recommendation features.

## Branches

```text
main          Production-ready
develop       Integration
feature/*     Features
fix/*         Bug fixes
data/*        Data/schema work
collector/*   Collectors and parsers
```

Open pull requests into `develop` (or `main` until `develop` is established). Do not push directly to `main` once branch protection is enabled.

## Definition of done

A feature is done when it has:

- Implementation
- Database migration if necessary
- Tests
- Source/provenance support
- Error handling and logging
- Documentation
- Git commit

## Local checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
cd apps/web && pnpm lint && pnpm typecheck && pnpm build
```

Install pre-commit hooks:

```bash
uv run pre-commit install
```

## Pull requests

- Keep PRs small and focused.
- Describe what changed and why.
- Link issues when applicable.
- CI must pass (format, lint, typecheck, tests, migrations, build).

## Branch protection (maintainers)

After the GitHub remote exists, protect `main`:

- Require pull requests
- Require status checks (CI) to pass before merge
- Disallow force pushes
