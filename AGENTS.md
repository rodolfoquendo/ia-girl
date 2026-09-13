# AGENTS.md

Canonical agent-readable guidance for the `ia-girl` repository — the single source of truth for project logic and conventions. All AI coding agents (Claude Code, Codex, Copilot Workspace, etc.) should read this file first. `CLAUDE.md` is a thin pointer to this file plus any Claude Code CLI–specific detail.

Deep-dive detail lives under `.ai/` — this file stays a concise entry point. See the pointers inline below.

---

## Project Overview

`ia-girl` is a **multi-character AI persona content engine**. It manages fictional characters (defined in the database and seeded from `character.yaml`), generates lifestyle images, captions, blog articles, Twitter/X threads, and podcast episodes, and auto-publishes to Instagram, TikTok, or WordPress.

It exposes a **FastAPI REST API** (`api/`) and a **single-page frontend** (`api/static/index.html`). A background cron (APScheduler, embedded in the FastAPI process) publishes scheduled posts automatically.

All services run inside Docker. The app connects to a shared MySQL 8.0 container (database: `ia_girl`).

---

## Stack

| Layer | Technology |
|---|---|
| Web server | FastAPI + Uvicorn |
| Database | MySQL 8.0, SQLAlchemy 2.0 ORM (Mapped[] annotations) |
| Image generation | Replicate API (Flux 1.1 Pro) |
| Text / captions / content | Anthropic Claude API (`claude-sonnet-4-6`) |
| Audio / TTS | ElevenLabs REST API (via httpx) |
| Video | ffmpeg slideshow or Runway ML Gen-3 |
| Instagram | instagrapi (`login_by_sessionid` preferred over username/password) |
| Twitter / X | tweepy 4.x (v1.1 API for profile edits, v2 for tweets) |
| TikTok | TikTok Content Posting API |
| Scheduler | APScheduler (BackgroundScheduler, inside FastAPI process) |
| Container | Docker, single service `ia-girl`, port 8082 |
| Frontend | Vanilla JS + Bootstrap Icons, served as static file, no build step |

---

## Development Environment

```bash
make up       # Build image, start container → API at http://localhost:8082
make logs     # Tail container logs
make shell    # bash inside the container
```

Local dev (no Docker):

```bash
make install  # Create .venv and install deps
make api      # FastAPI with hot reload at http://localhost:8000
```

API docs (Swagger UI) auto-generated at `/docs`. Frontend SPA served at `/`.

### Environment variables

Copy `.env.example` to `.env`:

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | From console.anthropic.com |
| `REPLICATE_API_TOKEN` | From replicate.com |
| `ELEVENLABS_API_KEY` | From elevenlabs.io |
| `INSTAGRAM_USERNAME` / `INSTAGRAM_PASSWORD` | Per-character; stored on Character model |
| `INSTAGRAM_SESSION_ID` | Per-character browser cookie; stored on Character model; preferred over password |
| `TIKTOK_SESSION_ID` | Optional; stored on Character model |
| `RUNWAY_API_KEY` | Optional, for animated video |
| `DB_HOST` | `host.docker.internal` (container) or `127.0.0.1` (local) |
| `OUTPUT_DIR` | Where generated files are saved (default `./output`) |

---

## Data Model

Full entity tables, field additions, enums, and post lifecycle: **[`.ai/docs/data-model.md`](.ai/docs/data-model.md)**

Quick reference: all models in `db/models.py`; schema evolves via idempotent `_migrate()` in `api/app.py` (no migration framework). Core entities: `Character`, `Place` (table `apartments`), `Room`, `ClothingItem`, `Post`, `PostMedia`, `CharacterMedia`, `CharacterRelationship`, `CharacterLanguage`, `PromptDefaults`.

**Posts have no `media_path` column** — all media lives in `PostMedia` records; read from `post.media_items`.

---

## Code Architecture

Full breakdown of `db/`, `core/`, `api/`, `worker/`, `platforms/`, the complete route map, image prompt assembly, and content-language handling: **[`.ai/docs/architecture.md`](.ai/docs/architecture.md)**

Key pointers:

- **Places** are at `/api/places` (route file is still `api/routes/apartments.py`; the Python class is `Place` with `__tablename__ = "apartments"`)
- **Image prompt assembly**: `global_positive + base_prompt + char_media_references + outfit_tags + room.render_prompt + scene + visual_style + global_style`
- **Content language**: `persona_system_prompt()` appends `"Write in {language}."` from the character's primary `CharacterLanguage`
- **Instagram login**: always prefer `session_id` over password; delete the stale session file before `login_by_sessionid()`; never call `cl.login()` in a loop (see architecture doc for why)

---

## Frontend

Full File Manager and character-profile-management notes: **[`.ai/docs/frontend.md`](.ai/docs/frontend.md)**

Key pointer: in `#mMediaEditor`, do NOT add the `.m-box` class — it forces `flex-direction:column` and breaks the two-column layout.

---

## Key files

| Path | Purpose |
|---|---|
| `character.yaml` | Seed data for the default character (used on first boot only) |
| `api/app.py` | FastAPI entry + `_migrate()` + `_seed()` + cron startup |
| `api/routes/posts.py` | Post CRUD + all generation endpoints |
| `api/routes/characters.py` | Character CRUD + profile picture + push-to-platform |
| `api/routes/apartments.py` | Place + Room CRUD (prefix `/api/places`) |
| `api/routes/media.py` | PostMedia CRUD + library + tags + usage chain + upload |
| `api/routes/podcast.py` | Podcast/TTS generation |
| `api/static/index.html` | Full single-page frontend |
| `worker/publisher.py` | Scheduled publish cron |
| `platforms/instagram.py` | instagrapi adapter; `client_for()` handles session ID login |
| `platforms/tiktok.py` | TikTok Content Posting API adapter |
| `db/models.py` | All ORM models |
| `docker-compose.yml` | Container config, connects to `ie-api-db` MySQL |
| `Makefile` | All common commands |

---

## Working Style & Communication

Full guidelines: **[`.ai/guidelines/working-style.md`](.ai/guidelines/working-style.md)**

Summary: think before coding, ask if ambiguous, simplicity first, surgical changes only, no `Co-Authored-By` trailers naming any AI agent, and keep replies as brief as possible.

---

## Git safety (CRITICAL — read every session)

Full detail: **[`.ai/guidelines/git-safety.md`](.ai/guidelines/git-safety.md)**

**DO NOT MESS WITH GIT.** Never run `git checkout`, `git stash`, `git reset`, `git restore`, `git clean`, or anything that discards/overwrites working-tree changes — these repos often carry large amounts of uncommitted work. Commit first, or ask the user, before changing branches.

**NEVER TOUCH `insignia-education/infra/envs`** — read-only, gitignored, unrecoverable personal record of deployed environments. Read it if you need to know what's there; never create, edit, move, or delete anything in it.

## Before starting a task

- Check the current branch first.
- Decide: reuse it if it's already the right task branch, or cut a new one off `master` — don't assume either without checking.
- Ask whether this task deploys to `beta`. That answer decides whether direct-to-`master` handling applies to this task.
- Never push directly to `beta`.
- Never promote/merge `beta` into `master` — that direction never happens.

## Communication style
- TL;DR always. Fewest words possible. No preamble, no step-by-step narration, no "here is what I did" summaries, no explaining what you are about to do.
- Log every command executed and every file write, verbatim — syscalls and writes, not model narration.
- Report outputs, not steps: state what a command produced/changed, not the fact that you ran it or why.
