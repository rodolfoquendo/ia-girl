# AGENTS.md

Canonical agent-readable guidance for the `ia-girl` repository. All AI coding agents (Claude Code, Codex, Copilot Workspace, etc.) should read this file. `CLAUDE.md` extends this with Claude Code–specific detail and must remain in sync.

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
| Frontend | Vanilla JS + Bootstrap Icons, served as static file |

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

API docs (Swagger UI) auto-generated at `/docs`.

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

All models are in `db/models.py`. Schema evolves via the idempotent `_migrate()` function in `api/app.py` — `ALTER TABLE … ADD COLUMN IF NOT EXISTS` style checks. No migration framework.

### Core entities

| Model | Table | Description |
|---|---|---|
| `Character` | `characters` | A persona: name, age, gender, voice_id, visual prompts, social credentials, bio, profile picture |
| `Place` | `apartments` | A location a character uses: apartment, office, park, café… (class renamed, table kept for compat) |
| `Room` | `rooms` | An area inside a Place: bedroom, kitchen, balcony… |
| `ClothingItem` | `clothing_items` | A wardrobe item with `prompt_tag` injected into image prompts |
| `Post` | `posts` | A content unit: scene, caption, mood, network, status, schedule |
| `PostMedia` | `post_media` | Media files attached to a post (photos, video, audio). The post has no `media_path` column — all media lives here |
| `CharacterMedia` | `character_media` | Photos/audio that define how a character looks; used to build image prompts |
| `CharacterRelationship` | `character_relationships` | Typed edge between two characters (friend, colleague, partner…) |
| `CharacterLanguage` | `character_languages` | Languages a character speaks; primary language drives content generation language |
| `PromptDefaults` | `prompt_defaults` | Singleton (id=1): global positive/negative/style merged into every image generation |

### Character fields (relevant additions)

| Field | Type | Purpose |
|---|---|---|
| `instagram_session_id` | `VARCHAR(500)` | Browser `sessionid` cookie; used by `login_by_sessionid()` to avoid bot detection |
| `profile_bio` | `TEXT` | Cross-platform bio for the character (pushed to Instagram, Twitter/X, etc.) |
| `profile_picture` | `VARCHAR(500)` | Server path to the character's current profile picture |

### PostMedia fields (relevant additions)

| Field | Type | Purpose |
|---|---|---|
| `tags` | `JSON` | List of string tags assigned to this media file; used for filtering in the file manager |

### Key enums

- `Network`: `instagram`, `tiktok`, `both`, `wordpress`, `twitter`
- `PostStatus`: `pending` → `to_be_published` → `published` / `failed`
- `MediaType`: `photo`, `video`, `audio`
- `Gender`: `female`, `male`, `non_binary`, `other`
- `ClothingCategory`, `ClothingStyle`, `RelationshipType`

### Post lifecycle

```
pending → to_be_published (via /api/posts/{id}/schedule) → published
                                                         → failed
```

`wordpress` and `twitter` network posts are text-only — no media required before scheduling.

---

## Code Architecture

### `db/`

- `database.py` — SQLAlchemy engine, `SessionLocal`, `get_db()` dependency, `Base`
- `models.py` — all ORM models with `Mapped[]` type annotations

### `core/`

- `character.py` — `load(character_id)` returns a dict; `persona_system_prompt(char)` builds Claude system prompt including primary language instruction; `load_yaml()` / `yaml_to_db_fields()` for seed
- `content_gen.py` — `caption()`, `dm_reply()`, `content_ideas()`, `story_text()`, `blog_post()`, `twitter_thread()` — all accept an optional `char` dict
- `image_gen.py` — Replicate/Flux wrapper; `generate(scene, char, aspect_ratio, full_prompt)`; always prepends character's `base_prompt` when no `full_prompt` supplied
- `audio_gen.py` — ElevenLabs TTS wrapper; `tts(text, voice_id)` returns a `Path`
- `video_gen.py` — `slideshow(images)` via ffmpeg; `animate_with_runway()` for AI video

### `api/`

- `app.py` — FastAPI entry point; lifespan: `Base.metadata.create_all` → `_migrate()` → `_seed()` → start APScheduler; mounts `/media` and `/static`
- `routes/posts.py` — post CRUD, `generate-caption`, `generate-image`, `generate-blog`, `generate-thread`, `schedule`
- `routes/characters.py` — character CRUD + profile management (see route map below)
- `routes/apartments.py` — Place CRUD at `/api/places` (`place_type` field; room sub-routes; duplicate/resident endpoints)
- `routes/wardrobe.py` — `ClothingItem` CRUD + duplicate; includes `gender` field
- `routes/media.py` — `PostMedia` CRUD + file library + tag management (see route map below)
- `routes/relationships.py` — `CharacterRelationship` CRUD
- `routes/podcast.py` — `/api/podcast/voices`, `/api/podcast/script`, `/api/podcast/episode`, `/api/podcast/preview-tts`
- `routes/character_media.py` — `CharacterMedia` CRUD + `generate` endpoint at `/api/characters/{id}/media`
- `routes/languages.py` — `CharacterLanguage` CRUD at `/api/characters/{id}/languages`; `/api/characters/languages/common` returns 16 ISO 639-1 presets
- `routes/settings.py` — `/api/settings/prompt-defaults` GET/PATCH for the `PromptDefaults` singleton
- `static/index.html` — full SPA; vanilla JS, Bootstrap Icons, no build step

### `worker/`

- `publisher.py` — runs every 60 s; queries `to_be_published` posts where `scheduled_at <= now`; reads media from `post.media_items` (position 0); checks character credentials before publishing — accepts `instagram_session_id` OR password for Instagram; if no credentials configured, marks post as `published` with a "no credentials" note (not `failed`) so posts accumulate safely without errors

### `platforms/`

- `instagram.py` — instagrapi; `client_for(username, password, session_id=None)`:
  - If `session_id`: always deletes stale session file first (avoids corrupted auth state), calls `login_by_sessionid()`, dumps new session
  - If session file exists: loads settings, verifies via `cl.get_timeline_feed()` without re-login
  - Falls back to fresh `cl.login()` + dump settings
  - **Never call `cl.login()` repeatedly** — Instagram flags repeated logins as bot activity; prefer `session_id`
- `tiktok.py` — TikTok Content Posting API; falls back to staging folder if no session ID

---

## Route map

### Characters (`/api/characters`)

| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/api/characters` | List / create |
| GET/PUT/DELETE | `/api/characters/{id}` | Read / update / delete |
| POST | `/api/characters/{id}/profile-picture` | Upload a file as the character's profile picture (saves to `output/profiles/`) |
| POST | `/api/characters/{id}/profile-picture-from-path` | Assign an existing server file as profile picture |
| GET | `/api/characters/{id}/generated-images` | List all `PostMedia` photo paths generated for this character |
| POST | `/api/characters/{id}/push-profile/instagram` | Push `profile_bio` + `profile_picture` to Instagram via instagrapi |
| POST | `/api/characters/{id}/push-profile/twitter` | Push `profile_bio` + `profile_picture` to Twitter/X via tweepy v1.1 `api.update_profile()` + `api.update_profile_image()` |

### Media (`/api/media`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/media` | List PostMedia records |
| GET/PATCH/DELETE | `/api/media/{id}` | Read / update / delete a record (PATCH accepts `tags: list[str]`) |
| GET | `/api/media/library` | List all files in `OUTPUT_DIR` as a flat library with usage metadata and tags |
| POST | `/api/media/library/upload` | Upload an image or video directly to `OUTPUT_DIR` |
| GET | `/api/media/library/{filename}/usage` | Usage chain: where this file is referenced (`output_of`, `ref_of`, `char_media`, `place_media`) |
| GET | `/api/media/tags` | Sorted list of all unique tags across all `PostMedia` records |

---

## Image prompt assembly

When generating an image without a custom `image_prompt`, the prompt is assembled in order:

```
{global_positive}, {char.visual.base_prompt}, {char_media_references}, {outfit_tags}, {room.render_prompt or room.description}, {post.scene}, {char.visual.style}, {global_style}
```

Empty parts are omitted. `outfit_tags` is the `prompt_tag` field of each selected `ClothingItem` joined by `, `.

The `global_positive`, `global_style`, and `global_negative` come from the `PromptDefaults` singleton and are always merged in, so every character shares the same realism/quality baseline. Character `visual_style` should only contain lighting/mood specifics, not quality keywords.

## Content language

`persona_system_prompt(char)` reads `char["languages"]`, finds the primary language, and appends `"Write in {language}."` to every Claude system prompt. All caption, blog, and thread generation follows this language.

---

## Frontend (api/static/index.html)

Single HTML file, no build step, no framework. Dark theme, Bootstrap Icons, vanilla JS.

### File Manager

- Click any image card → opens `#mMediaEditor` modal (two-column: image left 380px fixed, form right flex:1)
- Edit panel: prompt textarea, reference images, usage chain (`<details>`), generation parameters (safety, quality, aspect ratio, format)
- **Tag system**: tags stored as JSON on `PostMedia.tags`; tag chips shown on each file card; tag filter bar above the grid; `GET /api/media/tags` populates a global `_mmeAllTags` array used for custom autocomplete dropdown (NOT native `<datalist>` — custom `<div id="mmeTagAc">` shown above input)
- **Usage chain**: `GET /api/media/library/{filename}/usage` → shows where image is used; supports removing references and opening the post that uses it
- Upload button: `POST /api/media/library/upload`
- `#mMediaEditor` container uses `height:88vh;display:flex;flex-direction:row` — do NOT add `.m-box` class (it hardcodes `flex-direction:column`)

### Character profile management

- Basic tab: `profile_bio` textarea, profile picture upload + gallery picker, circular preview
- Social tab: "Push Profile to Platforms" buttons (Instagram, X/Twitter)
- `#mProfilePicPicker` modal: grid of character's generated images (`GET /api/characters/{id}/generated-images`)

---

## Working Style

- **Think before coding.** State assumptions. Ask if ambiguous. Stop when confused — do not pick an interpretation and run.
- **Simplicity first.** Minimum code that solves the problem. No speculative abstractions.
- **Surgical changes.** Touch only what the task requires. Do not refactor neighboring code.
- **No commits in any AI agent's name.** All commits must be authored solely by the human developer. No `Co-Authored-By` trailers naming Claude, Codex, or any AI.

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

## Communication style
- Respond as briefly as possible. Caveman mode: shortest answer that works. No fluff, no summaries, no "here is what I did".

---

## Git safety (CRITICAL — read every session)

**DO NOT MESS WITH GIT.** DO NOT run `git checkout`, `git stash`, `git reset`, `git restore`,
`git clean`, or any command that discards or overwrites working-tree changes. These repos often
carry large amounts of **uncommitted** work, and these commands will destroy it irreversibly.

If you need to change the current branch: **commit the work first, or ask the user to commit.**
Never revert, discard, or overwrite changes via git without explicit permission from the user.
