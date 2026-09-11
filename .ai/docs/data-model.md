# Data Model

All models are in `db/models.py`. Schema evolves via the idempotent `_migrate()` function in `api/app.py` — `ALTER TABLE … ADD/DROP COLUMN` with existence checks. No migration framework.

## Core entities

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

## Character fields (relevant additions)

| Field | Type | Purpose |
|---|---|---|
| `instagram_session_id` | `VARCHAR(500)` | Browser `sessionid` cookie; used by `login_by_sessionid()` to avoid bot detection |
| `profile_bio` | `TEXT` | Cross-platform bio for the character (pushed to Instagram, Twitter/X, etc.) |
| `profile_picture` | `VARCHAR(500)` | Server path to the character's current profile picture |

## PostMedia fields (relevant additions)

| Field | Type | Purpose |
|---|---|---|
| `tags` | `JSON` | List of string tags assigned to this media file; used for filtering in the file manager |

## Key enums

- `Network`: `instagram`, `tiktok`, `both`, `wordpress`, `twitter`
- `PostStatus`: `pending` → `to_be_published` → `published` / `failed`
- `MediaType`: `photo`, `video`, `audio`
- `Gender`: `female`, `male`, `non_binary`, `other`
- `ClothingCategory`, `ClothingStyle`, `RelationshipType`

## Post lifecycle

```
pending → to_be_published (via /api/posts/{id}/schedule) → published
                                                         → failed
```

`wordpress` and `twitter` network posts are text-only — no media required before scheduling.
