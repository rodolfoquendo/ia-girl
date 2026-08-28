# ia-girl

AI persona content engine — generates lifestyle images, captions, and DM replies for a fictional character and auto-posts to Instagram and TikTok.

## Stack

- **Image generation** — Replicate (Flux 1.1 Pro)
- **Text / captions / DMs** — Claude API (claude-sonnet-4-6)
- **Video / Reels** — ffmpeg slideshow or Runway ML Gen-3
- **Instagram** — instagrapi
- **TikTok** — TikTok Content Posting API
- **Scheduler** — APScheduler

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in your API keys in .env
```

You'll need:
- `ANTHROPIC_API_KEY` — from console.anthropic.com
- `REPLICATE_API_TOKEN` — from replicate.com
- `INSTAGRAM_USERNAME` + `INSTAGRAM_PASSWORD` — your IG account
- `TIKTOK_SESSION_ID` — optional, for TikTok API upload
- `RUNWAY_API_KEY` — optional, for animated videos

## Character

Edit `character.yaml` to define the persona: name, appearance, personality, posting schedule, and visual style.

## Usage

```bash
# Generate one image + caption (no posting)
python main.py generate

# Generate + post immediately
python main.py post

# Get 7 content ideas for the week
python main.py ideas

# Process and reply to pending Instagram DMs
python main.py dms

# Generate a reel for a specific scene
python main.py reel "morning yoga on rooftop, city skyline"

# Start the automated scheduler (runs forever, posts on schedule)
python main.py schedule
```

## Structure

```
ia-girl/
├── character.yaml          # Persona definition — edit this first
├── main.py                 # CLI entry point
├── scheduler.py            # APScheduler jobs
├── requirements.txt
├── .env.example
├── core/
│   ├── character.py        # YAML loader + prompt builders
│   ├── image_gen.py        # Replicate/Flux wrapper
│   ├── content_gen.py      # Claude API captions + DM replies
│   └── video_gen.py        # ffmpeg slideshow + Runway ML
├── platforms/
│   ├── instagram.py        # instagrapi adapter
│   └── tiktok.py           # TikTok upload adapter
└── output/                 # Generated images and videos land here
```
