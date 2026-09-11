# Code Architecture

## `db/`

- `database.py` — SQLAlchemy engine, `SessionLocal`, `get_db()` dependency, `Base`
- `models.py` — all ORM models with `Mapped[]` type annotations

## `core/`

- `character.py` — `load(character_id)` returns a dict; `persona_system_prompt(char)` builds Claude system prompt including primary language instruction; `load_yaml()` / `yaml_to_db_fields()` for seed
- `content_gen.py` — `caption()`, `dm_reply()`, `content_ideas()`, `story_text()`, `blog_post()`, `twitter_thread()` — all accept an optional `char` dict
- `image_gen.py` — Replicate/Flux wrapper; `generate(scene, char, aspect_ratio, full_prompt)`; always prepends character's `base_prompt` when no `full_prompt` supplied
- `audio_gen.py` — ElevenLabs TTS wrapper; `tts(text, voice_id)` returns a `Path`
- `video_gen.py` — `slideshow(images)` via ffmpeg; `animate_with_runway()` for AI video

## `api/`

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

## `worker/`

- `publisher.py` — runs every 60 s; queries `to_be_published` posts where `scheduled_at <= now`; reads media from `post.media_items` (position 0); checks character credentials before publishing — accepts `instagram_session_id` OR password for Instagram; if no credentials configured, marks post as `published` with a "no credentials" note (not `failed`) so posts accumulate safely without errors

## `platforms/`

- `instagram.py` — instagrapi; `client_for(username, password, session_id=None)`:
  - If `session_id`: always deletes stale session file first before calling `login_by_sessionid()`, then dumps the new session. Stale settings corrupt auth state and cause `LoginRequired` on write operations even after a successful login.
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

Other route files and their prefixes are listed under `api/` above (`apartments.py` → `/api/places`, `wardrobe.py` → `/api/wardrobe`, `podcast.py` → `/api/podcast`, `character_media.py` → `/api/characters/{id}/media`, `languages.py` → `/api/characters/{id}/languages`, `settings.py` → `/api/settings`, `relationships.py` → `/api/relationships`, `posts.py` → `/api/posts`).

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
