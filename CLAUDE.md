# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> The canonical agent-readable version of these instructions is **`AGENTS.md`** (same directory). Both files are kept in sync; CLAUDE.md adds Claude Code–specific detail where needed. When the two files disagree, update both together.

---

## Project Overview

`ia-girl` is a **multi-character AI persona content engine**. It manages fictional characters, generates lifestyle images, captions, blog articles, Twitter/X threads, and podcast episodes, and auto-publishes to Instagram, TikTok, or WordPress.

Full architecture, data model, and working style rules are in **`AGENTS.md`** — read that first.

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

API docs (Swagger UI) at `/docs`. Frontend SPA at `/`.

---

## Stack (summary)

| Layer | Technology |
|---|---|
| Web server | FastAPI + Uvicorn |
| Database | MySQL 8.0, SQLAlchemy 2.0 ORM (`Mapped[]` annotations) |
| Image generation | Replicate API (Flux 1.1 Pro) |
| Text / captions | Anthropic Claude API (`claude-sonnet-4-6`) |
| Audio / TTS | ElevenLabs REST API (via httpx) |
| Video | ffmpeg slideshow or Runway ML Gen-3 |
| Instagram | instagrapi (`login_by_sessionid` preferred — avoids bot detection) |
| Twitter / X | tweepy 4.x (v1.1 API for profile updates) |
| TikTok | TikTok Content Posting API |
| Scheduler | APScheduler (embedded in FastAPI process) |
| Frontend | Vanilla JS + Bootstrap Icons, single HTML file, no build step |

---

## Code Architecture

See `AGENTS.md` for the full breakdown. Key pointers:

- **Models**: `db/models.py` — `Character`, `Place` (table: `apartments`), `Room`, `ClothingItem`, `Post`, `PostMedia`, `CharacterMedia`, `CharacterLanguage`, `CharacterRelationship`
- **Posts have no `media_path` column** — all media lives in `PostMedia` records; read from `post.media_items`
- **Places** are at `/api/places` (route file is still `api/routes/apartments.py`; the Python class is `Place` with `__tablename__ = "apartments"`)
- **Schema evolution**: idempotent `_migrate()` in `api/app.py` — `ALTER TABLE … ADD/DROP COLUMN` with existence checks. No migration framework
- **Image prompt assembly**: `base_prompt + outfit_tags + room.render_prompt + scene + visual_style`
- **Content language**: `persona_system_prompt()` appends `"Write in {language}."` from the character's primary `CharacterLanguage`

### Character model additions

| Field | Type | Notes |
|---|---|---|
| `instagram_session_id` | `VARCHAR(500)` | Browser `sessionid` cookie; passed to `client_for()` to use `login_by_sessionid()` |
| `profile_bio` | `TEXT` | Cross-platform character bio (pushed to Instagram and Twitter/X) |
| `profile_picture` | `VARCHAR(500)` | Server path to current profile picture (stored under `output/profiles/`) |

### PostMedia additions

| Field | Type | Notes |
|---|---|---|
| `tags` | `JSON` | `list[str]`; assigned in the file manager; drives tag filter and autocomplete |

### Route map

| File | Prefix | Purpose |
|---|---|---|
| `routes/posts.py` | `/api/posts` | Post CRUD + generate-caption / generate-image / generate-blog / generate-thread / schedule |
| `routes/characters.py` | `/api/characters` | Character CRUD + profile picture upload + push-profile to Instagram / Twitter |
| `routes/apartments.py` | `/api/places` | Place + Room CRUD (place_type, duplicate, resident) |
| `routes/wardrobe.py` | `/api/wardrobe` | ClothingItem CRUD + duplicate |
| `routes/media.py` | `/api/media` | PostMedia CRUD + library + upload + tags + usage chain |
| `routes/relationships.py` | `/api/relationships` | CharacterRelationship CRUD |
| `routes/podcast.py` | `/api/podcast` | voices / script / episode / preview-tts |
| `routes/character_media.py` | `/api/characters/{id}/media` | CharacterMedia CRUD + generate |
| `routes/languages.py` | `/api/characters/{id}/languages` | CharacterLanguage CRUD + common presets |
| `routes/settings.py` | `/api/settings` | `PromptDefaults` singleton GET/PATCH |

### Instagram login — important rules

`platforms/instagram.py` → `client_for(username, password, session_id=None)`:

1. **Always prefer `session_id`** — bypasses Instagram bot detection entirely
2. When using `session_id`: **delete the stale session file first** (`session_file.unlink(missing_ok=True)`) before calling `login_by_sessionid()`. Stale settings corrupt auth state and cause `LoginRequired` on write operations even after a successful login.
3. Never call `cl.login()` in a loop — repeated username/password logins trigger IP blacklisting.

### File Manager — frontend notes

- `#mMediaEditor` modal: `height:88vh;display:flex;flex-direction:row`. **Do not add `.m-box` class** — it forces `flex-direction:column` and breaks the two-column layout.
- Tag autocomplete uses a custom `<div id="mmeTagAc">` dropdown (not native `<datalist>`). Tags are pre-loaded from `GET /api/media/tags` into `_mmeAllTags` global array when the editor opens. The dropdown filters `_mmeAllTags` on every keystroke and is positioned above the input using `bottom:calc(100% + 2px)`.

---

## Working Style

- **Think before coding.** State assumptions. Ask if ambiguous. Stop when confused.
- **Simplicity first.** Minimum code that solves the problem. No speculative abstractions.
- **Surgical changes.** Touch only what the task requires.
- **No commits in Claude's name.** All commits must be authored solely by the human developer. Do not add `Co-Authored-By` trailers naming Claude or any AI agent.

---

## Key files

| Path | Purpose |
|---|---|
| `AGENTS.md` | Canonical full reference — read this first |
| `character.yaml` | Seed data for the default character (first boot only) |
| `api/app.py` | FastAPI entry + `_migrate()` + `_seed()` + cron startup |
| `api/routes/posts.py` | Post CRUD + all generation endpoints |
| `api/routes/characters.py` | Character CRUD + profile picture + push to platforms |
| `api/routes/apartments.py` | Place + Room CRUD (prefix `/api/places`) |
| `api/routes/media.py` | PostMedia CRUD + library + upload + tags + usage chain |
| `api/routes/podcast.py` | Podcast/TTS generation |
| `api/static/index.html` | Full single-page frontend |
| `worker/publisher.py` | Scheduled publish cron |
| `platforms/instagram.py` | instagrapi adapter; `client_for()` handles session ID login |
| `db/models.py` | All ORM models |
| `docker-compose.yml` | Container config |
| `Makefile` | All common commands |

## Communication style
- Respond as briefly as possible. Caveman mode: shortest answer that works. No fluff, no summaries, no "here is what I did".

---

## Git safety (CRITICAL — read every session)

**DO NOT MESS WITH GIT.** DO NOT run `git checkout`, `git stash`, `git reset`, `git restore`,
`git clean`, or any command that discards or overwrites working-tree changes. These repos often
carry large amounts of **uncommitted** work, and these commands will destroy it irreversibly.

If you need to change the current branch: **commit the work first, or ask the user to commit.**
Never revert, discard, or overwrite changes via git without explicit permission from the user.
