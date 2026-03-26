# API Reference

The Loom API uses REST with JSON request/response bodies.
All endpoints are prefixed with `/api/v1`.

## Interactive Documentation

When the backend is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

The OpenAPI schema is auto-generated from FastAPI endpoint
definitions and Pydantic schemas.

## Authentication

Most endpoints require a JWT access token in the
`Authorization: Bearer <token>` header.

### Endpoints

- `POST /api/v1/auth/register` — register first user (admin)
- `POST /api/v1/auth/login` — get access + refresh tokens
- `POST /api/v1/auth/refresh` — refresh access token
- `GET /api/v1/auth/me` — current user profile

## Cases

- `POST /api/v1/cases` — create case
- `GET /api/v1/cases` — list cases (membership-filtered)
- `GET /api/v1/cases/{id}` — case detail
- `PATCH /api/v1/cases/{id}` — update case
- `POST /api/v1/cases/{id}/members` — add member
- `DELETE /api/v1/cases/{id}/members/{user_id}` — remove
- `GET /api/v1/cases/{id}/members` — list members

## Assets

- `POST /api/v1/cases/{id}/assets/upload` — upload file
- `POST /api/v1/cases/{id}/assets/upload-url` — presigned URL
- `POST /api/v1/cases/{id}/assets/{id}/complete` — finalize
- `GET /api/v1/cases/{id}/assets` — list assets
- `GET /api/v1/cases/{id}/assets/{id}` — asset detail
- `GET /api/v1/cases/{id}/assets/{id}/download-url` — download

## Annotations

- `POST /api/v1/cases/{id}/annotations` — create
- `GET /api/v1/cases/{id}/annotations` — list (filterable)
- `GET /api/v1/cases/{id}/annotations/{id}` — detail
- `PATCH /api/v1/cases/{id}/annotations/{id}` — update
- `DELETE /api/v1/cases/{id}/annotations/{id}` — delete

## Timeline

- `POST /api/v1/cases/{id}/events` — create event
- `GET /api/v1/cases/{id}/events` — list events
- `GET /api/v1/cases/{id}/events/{id}` — event detail
- `PATCH /api/v1/cases/{id}/events/{id}` — update event
- `POST /api/v1/cases/{id}/events/{id}/evidence` — link
- `DELETE /api/v1/cases/{id}/events/{id}/evidence/{id}` —
  unlink
- `GET /api/v1/cases/{id}/timeline` — full timeline view

## Exports

- `POST /api/v1/cases/{id}/exports` — start export
- `GET /api/v1/cases/{id}/exports` — list exports
- `GET /api/v1/cases/{id}/exports/{id}` — detail + download

## Health

- `GET /api/v1/health` — service health (no auth required)
