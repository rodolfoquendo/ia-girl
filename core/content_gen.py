"""
Content generation — captions, DMs, ideas, blog posts, Twitter threads.

Provider is read from prompt_defaults.text_provider ('claude' or 'openai') on every call.
API keys come from the api_keys table (active row) with env-var fallback.
"""

from __future__ import annotations

from core.api_keys import get_key
from core.character import load, persona_system_prompt


# ── Provider resolution ───────────────────────────────────────────────────────

def _get_provider() -> str:
    try:
        from db.database import SessionLocal
        from db.models import PromptDefaults
        db = SessionLocal()
        try:
            row = db.get(PromptDefaults, 1)
            if row and row.text_provider:
                return row.text_provider
        finally:
            db.close()
    except Exception:
        pass
    return "claude"


def _chat(system: str, user: str, max_tokens: int = 512) -> str:
    provider = _get_provider()
    if provider == "openai":
        return _chat_openai(system, user, max_tokens)
    if provider == "grok":
        return _chat_grok(system, user, max_tokens)
    return _chat_claude(system, user, max_tokens)


def _chat_claude(system: str, user: str, max_tokens: int, use_case: str = "caption") -> str:
    import anthropic
    from core.usage import get_model, log_usage
    key = get_key("anthropic")
    if not key:
        raise RuntimeError("No Anthropic API key configured")
    model = get_model("anthropic", use_case) or "claude-sonnet-4-6"
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    in_tok = msg.usage.input_tokens / 1_000_000
    out_tok = msg.usage.output_tokens / 1_000_000
    log_usage("anthropic", use_case, model, units=in_tok, output_units=out_tok)
    return msg.content[0].text.strip()


def _chat_openai(system: str, user: str, max_tokens: int, use_case: str = "caption") -> str:
    from openai import OpenAI
    from core.usage import get_model, log_usage
    key = get_key("openai")
    if not key:
        raise RuntimeError("No OpenAI API key configured")
    model = get_model("openai", use_case) or "gpt-4o"
    client = OpenAI(api_key=key)
    resp = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    in_tok = resp.usage.prompt_tokens / 1_000_000
    out_tok = resp.usage.completion_tokens / 1_000_000
    log_usage("openai", use_case, model, units=in_tok, output_units=out_tok)
    return resp.choices[0].message.content.strip()


def _chat_grok(system: str, user: str, max_tokens: int, use_case: str = "caption") -> str:
    from openai import OpenAI
    from core.usage import get_model, log_usage
    key = get_key("xai")
    if not key:
        raise RuntimeError("No xAI API key configured")
    model = get_model("xai", use_case) or "grok-3"
    client = OpenAI(api_key=key, base_url="https://api.x.ai/v1")
    resp = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    in_tok = resp.usage.prompt_tokens / 1_000_000
    out_tok = resp.usage.completion_tokens / 1_000_000
    log_usage("xai", use_case, model, units=in_tok, output_units=out_tok)
    return resp.choices[0].message.content.strip()


def _chat_with_provider(provider: str, system: str, user: str, max_tokens: int = 512) -> str:
    if provider == "openai":
        return _chat_openai(system, user, max_tokens)
    if provider == "grok":
        return _chat_grok(system, user, max_tokens)
    return _chat_claude(system, user, max_tokens)


# ── Public functions ──────────────────────────────────────────────────────────

def caption(scene: str, mood: str = "casual", char: dict | None = None, text_length_words: int | None = None) -> str:
    if char is None:
        char = load()
    system = persona_system_prompt(char)
    length_note = f"Write about {text_length_words} words." if text_length_words else "Keep it under 150 words."
    max_tokens = min(4096, max(512, int((text_length_words or 150) * 2.2)))
    prompt = (
        f"Write a social media caption for this scene: {scene}\n"
        f"Mood: {mood}\n"
        f"Include 3–5 relevant hashtags at the end.\n"
        f"{length_note} Don't use quotation marks around the caption."
    )
    return _chat(system, prompt, max_tokens=max_tokens)


def dm_reply(incoming_message: str, char: dict | None = None) -> str:
    if char is None:
        char = load()
    system = persona_system_prompt(char)
    prompt = (
        f"A follower sent you this DM: \"{incoming_message}\"\n\n"
        f"Write a warm, natural reply in your voice. Keep it short (1–3 sentences). "
        f"Be friendly and genuine. Don't be overly enthusiastic or use exclamation marks excessively."
    )
    return _chat(system, prompt, max_tokens=256)


def content_ideas(n: int = 7, char: dict | None = None) -> list[str]:
    if char is None:
        char = load()
    system = persona_system_prompt(char)
    prompt = (
        f"Generate {n} distinct content ideas for the week. "
        f"For each idea, write one scene description (20–40 words) that describes exactly what "
        f"the photo should show — location, activity, lighting, vibe. "
        f"Output only the scene descriptions, one per line, no numbering or labels."
    )
    raw = _chat(system, prompt, max_tokens=1024)
    return [line.strip() for line in raw.splitlines() if line.strip()]


def story_text(scene: str, char: dict | None = None) -> str:
    if char is None:
        char = load()
    system = persona_system_prompt(char)
    prompt = (
        f"Write a very short text overlay for an Instagram Story showing: {scene}\n"
        f"Max 10 words. Punchy, in your voice. No hashtags. No quotes."
    )
    return _chat(system, prompt, max_tokens=64)


def blog_post(topic: str, mood: str = "casual", char: dict | None = None, min_words: int = 600) -> str:
    if char is None:
        char = load()
    system = persona_system_prompt(char)
    min_words = max(500, min_words)
    target_hi = max(min_words + 250, 900)
    prompt = (
        f"Write a full blog article about: {topic}\n"
        f"Tone/mood: {mood}\n\n"
        f"Format as clean HTML using only these tags: <h1>, <h2>, <p>, <ul>, <li>, <strong>, <em>.\n"
        f"Structure:\n"
        f"- <h1> with a catchy title\n"
        f"- Opening paragraph that hooks the reader\n"
        f"- 3-4 sections with <h2> headings and body paragraphs\n"
        f"- Closing paragraph with a personal call-to-action\n"
        f"Write in first person, in your voice. At least {min_words} words total; aim for {min_words}-{target_hi} words. No meta-commentary."
    )
    return _chat(system, prompt, max_tokens=min(4096, max(2048, int(target_hi * 2.2))))


def improve_prompt(prompt: str, provider: str | None = None) -> str:
    system = (
        "You are an expert at writing prompts for AI image generation (Flux, Grok image models). "
        "Your job is to improve the given prompt: make it more vivid, specific, and visually rich "
        "while keeping the original intent. Output ONLY the improved prompt text — no explanation, "
        "no preamble, no quotes."
    )
    user = f"Improve this image generation prompt:\n\n{prompt}"
    if provider:
        return _chat_with_provider(provider, system, user, max_tokens=600)
    return _chat(system, user, max_tokens=600)


def generate_scene_from_strategy(
    strategy: dict,
    topic: str,
    post_type: str,
    char: dict | None = None,
) -> str:
    """
    Generate a concrete scene description for a post, grounded in a strategy.
    Returns a short scene string suitable for image prompts and caption generation.
    """
    if char is None:
        char = load()

    type_hints = {
        "photo":    "a single lifestyle photograph",
        "carousel": "a series of 3-5 photos telling a visual story",
        "video":    "a short video or reel (15-30 seconds)",
        "tweet":    "a text-first Twitter/X post with an optional photo",
        "blog":     "a WordPress blog article header image",
    }
    type_hint = type_hints.get(post_type, "a social media post")

    guidelines = strategy.get("scene_guidelines") or ""
    tone = strategy.get("tone") or "casual"
    hashtags = ", ".join(strategy.get("hashtags") or [])

    system = (
        f"You are a creative director for {char.get('name','the character')}'s social media brand. "
        f"Your job is to write concrete, visual scene descriptions for post briefs. "
        f"Be specific about location, lighting, wardrobe details, action, and mood. "
        f"Output ONLY the scene description — 1-3 sentences, no preamble, no hashtags."
    )
    user = (
        f"Post type: {type_hint}\n"
        f"Topic: {topic}\n"
        f"Tone: {tone}\n"
        + (f"Scene guidelines: {guidelines}\n" if guidelines else "")
        + (f"Hashtag context: {hashtags}\n" if hashtags else "")
        + f"\nWrite the scene description:"
    )
    return _chat(system, user, max_tokens=200)


def twitter_thread(topic: str, mood: str = "casual", char: dict | None = None) -> str:
    if char is None:
        char = load()
    system = persona_system_prompt(char)
    prompt = (
        f"Write a Twitter/X thread about: {topic}\n"
        f"Tone/mood: {mood}\n\n"
        f"Rules:\n"
        f"- 6-10 tweets, numbered 1/, 2/, 3/ etc.\n"
        f"- Each tweet must be under 280 characters\n"
        f"- First tweet is the hook — bold, opinionated, stops the scroll\n"
        f"- Middle tweets build the argument or story with specific details\n"
        f"- Last tweet is the call-to-action or punchline\n"
        f"- Write in first person, in your natural voice\n"
        f"- No filler phrases like 'A thread:' or 'Let me explain'\n"
        f"Output only the numbered tweets, one per line."
    )
    return _chat(system, prompt, max_tokens=1024)
