# Contributing

## Development Setup

See the [Quick Start](../README.md#quick-start) section in
the README.

## Code Style

### Python (backend)
- 4-space indentation, 80-character line width
- Type hints on all function signatures
- Ruff for linting and formatting (replaces black + flake8)
- mypy in strict mode
- Inline comments in lowercase
- Max cyclomatic complexity: 10

### TypeScript (frontend)
- 2-space indentation, 80-character line width
- Strict mode, no `any` type
- Single quotes, trailing commas (prettier)
- ESLint with typescript-eslint plugin
- Inline comments in lowercase

### Commit Messages
- Use the staging branch for development
- Properly cased, concise wording
- 2-4 bullet points maximum
- Do not include co-author information

Example:
```
Add asset upload with hash verification

- Implement multipart upload endpoint for files under 100MB
- Compute SHA-256 and SHA-512 hashes during upload stream
- Store originals in WORM-enabled MinIO bucket
```

## Testing

- Minimum 90% test coverage enforced in CI
- Backend: pytest with pytest-asyncio
- Frontend: Vitest with React Testing Library
- E2E: Playwright
- Run `make test` to verify all tests pass before pushing

## Pull Request Process

1. Create a branch from `staging`
2. Make changes with tests
3. Run `make lint && make test`
4. Push and open PR against `staging`
5. CI must pass before merge

## Architecture Decisions

Major changes should reference the evidence spine model in
`docs/architecture.md`. The core principles in the README
are non-negotiable constraints, not suggestions.
