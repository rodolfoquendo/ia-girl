from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from apscheduler.schedulers.background import BackgroundScheduler

from db.database import Base, engine
from api.routes.posts import router as posts_router
from api.routes.characters import router as characters_router
from api.routes.apartments import router as places_router
from api.routes.wardrobe import router as wardrobe_router
from api.routes.media import router as media_router
from api.routes.relationships import router as relationships_router
from api.routes.podcast import router as podcast_router
from api.routes.character_media import router as character_media_router
from api.routes.languages import router as languages_router
from api.routes.settings import router as settings_router
from api.routes.api_keys import router as api_keys_router
from api.routes.model_settings import router as model_settings_router
from api.routes.training import router as training_router
from api.routes.strategies import router as strategies_router
from api.routes.email import router as email_router
from api.routes.place_media import router as place_media_router
from api.routes.liveportrait import router as liveportrait_router

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")


def _migrate():
    """Idempotent column additions for existing tables."""
    from sqlalchemy import text
    with engine.begin() as conn:
        tables = {r[0] for r in conn.execute(text("SHOW TABLES")).fetchall()}
        if "posts" in tables:
            cols = {r[0] for r in conn.execute(text("SHOW COLUMNS FROM posts")).fetchall()}
            if "mood" not in cols:
                conn.execute(text("ALTER TABLE posts ADD COLUMN mood VARCHAR(50) NULL DEFAULT 'casual' AFTER scene"))
            if "character_id" not in cols:
                conn.execute(text("ALTER TABLE posts ADD COLUMN character_id INT NULL AFTER id"))
            if "character_ids" not in cols:
                conn.execute(text("ALTER TABLE posts ADD COLUMN character_ids JSON NULL AFTER character_id"))
            if "caption_prompt" not in cols:
                conn.execute(text("ALTER TABLE posts ADD COLUMN caption_prompt TEXT NULL AFTER mood"))
            if "image_prompt" not in cols:
                conn.execute(text("ALTER TABLE posts ADD COLUMN image_prompt TEXT NULL AFTER caption_prompt"))
            if "language" not in cols:
                conn.execute(text("ALTER TABLE posts ADD COLUMN language VARCHAR(100) NULL AFTER image_prompt"))
            if "caption_length_words" not in cols:
                conn.execute(text("ALTER TABLE posts ADD COLUMN caption_length_words INT NULL AFTER language"))
            conn.execute(text("ALTER TABLE posts MODIFY COLUMN caption TEXT NULL"))
        if "characters" in tables:
            char_cols = {r[0] for r in conn.execute(text("SHOW COLUMNS FROM characters")).fetchall()}
            if "gender" not in char_cols:
                conn.execute(text("ALTER TABLE characters ADD COLUMN gender ENUM('female','male','non_binary','other') NULL DEFAULT 'female' AFTER name"))
            if "voice_id" not in char_cols:
                conn.execute(text("ALTER TABLE characters ADD COLUMN voice_id VARCHAR(200) NULL"))
            if "trigger_word" not in char_cols:
                conn.execute(text("ALTER TABLE characters ADD COLUMN trigger_word VARCHAR(100) NULL"))
            if "replicate_model" not in char_cols:
                conn.execute(text("ALTER TABLE characters ADD COLUMN replicate_model VARCHAR(300) NULL"))
            if "replicate_training_id" not in char_cols:
                conn.execute(text("ALTER TABLE characters ADD COLUMN replicate_training_id VARCHAR(200) NULL"))
            if "training_status" not in char_cols:
                conn.execute(text("ALTER TABLE characters ADD COLUMN training_status VARCHAR(50) NULL"))
            if "training_place_id" not in char_cols:
                conn.execute(text("ALTER TABLE characters ADD COLUMN training_place_id INT NULL"))
            if "character_bible" not in char_cols:
                conn.execute(text("ALTER TABLE characters ADD COLUMN character_bible TEXT NULL"))
            if "email_address" not in char_cols:
                conn.execute(text("ALTER TABLE characters ADD COLUMN email_address VARCHAR(255) NULL"))
            if "email_password" not in char_cols:
                conn.execute(text("ALTER TABLE characters ADD COLUMN email_password VARCHAR(500) NULL"))
            if "email_imap_host" not in char_cols:
                conn.execute(text("ALTER TABLE characters ADD COLUMN email_imap_host VARCHAR(255) NULL"))
            if "email_imap_port" not in char_cols:
                conn.execute(text("ALTER TABLE characters ADD COLUMN email_imap_port INT NULL"))
            if "email_smtp_host" not in char_cols:
                conn.execute(text("ALTER TABLE characters ADD COLUMN email_smtp_host VARCHAR(255) NULL"))
            if "email_smtp_port" not in char_cols:
                conn.execute(text("ALTER TABLE characters ADD COLUMN email_smtp_port INT NULL"))
            if "instagram_session_id" not in char_cols:
                conn.execute(text("ALTER TABLE characters ADD COLUMN instagram_session_id VARCHAR(500) NULL"))
            if "profile_bio" not in char_cols:
                conn.execute(text("ALTER TABLE characters ADD COLUMN profile_bio TEXT NULL"))
            if "profile_picture" not in char_cols:
                conn.execute(text("ALTER TABLE characters ADD COLUMN profile_picture VARCHAR(500) NULL"))
        if "posts" in tables:
            post_cols = {r[0] for r in conn.execute(text("SHOW COLUMNS FROM posts")).fetchall()}
            if "script" not in post_cols:
                conn.execute(text("ALTER TABLE posts ADD COLUMN script JSON NULL"))
            if "wardrobe_items" not in post_cols:
                conn.execute(text("ALTER TABLE posts ADD COLUMN wardrobe_items JSON NULL"))
            if "place_id" not in post_cols:
                conn.execute(text("ALTER TABLE posts ADD COLUMN place_id INT NULL"))
            if "room_id" not in post_cols:
                conn.execute(text("ALTER TABLE posts ADD COLUMN room_id INT NULL"))
            # Widen MediaType enum to include audio
            conn.execute(text("ALTER TABLE posts MODIFY COLUMN media_type ENUM('photo','video','audio') NOT NULL DEFAULT 'photo'"))
            if "media_path" in post_cols:
                conn.execute(text("ALTER TABLE posts DROP COLUMN media_path"))
        if "post_media" in tables:
            conn.execute(text("ALTER TABLE post_media MODIFY COLUMN file_type ENUM('photo','video','audio') NOT NULL DEFAULT 'photo'"))
            pm_cols = {r[0] for r in conn.execute(text("SHOW COLUMNS FROM post_media")).fetchall()}
            if "reference_image" not in pm_cols:
                conn.execute(text("ALTER TABLE post_media ADD COLUMN reference_image VARCHAR(500) NULL"))
            if "provider" not in pm_cols:
                conn.execute(text("ALTER TABLE post_media ADD COLUMN provider VARCHAR(50) NULL"))
            if "gen_params" not in pm_cols:
                conn.execute(text("ALTER TABLE post_media ADD COLUMN gen_params JSON NULL"))
            if "tags" not in pm_cols:
                conn.execute(text("ALTER TABLE post_media ADD COLUMN tags JSON NULL"))
        # post_media_refs — multiple reference images per slot
        if "post_media_refs" not in tables:
            conn.execute(text("""
                CREATE TABLE post_media_refs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    post_media_id INT NOT NULL,
                    file_path VARCHAR(500) NOT NULL,
                    label VARCHAR(200) NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_pmr_media (post_media_id),
                    FOREIGN KEY (post_media_id) REFERENCES post_media(id) ON DELETE CASCADE
                )
            """))
            # migrate existing reference_image single values
            conn.execute(text("""
                INSERT INTO post_media_refs (post_media_id, file_path, label)
                SELECT id, reference_image, 'migrated'
                FROM post_media
                WHERE reference_image IS NOT NULL AND reference_image != ''
            """))
        # Model settings + usage log tables
        if "model_settings" not in tables:
            conn.execute(text("""
                CREATE TABLE model_settings (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    service VARCHAR(50) NOT NULL,
                    use_case VARCHAR(50) NOT NULL,
                    model_name VARCHAR(300) NOT NULL,
                    price_per_unit FLOAT NOT NULL DEFAULT 0,
                    price_per_output_unit FLOAT NOT NULL DEFAULT 0,
                    unit_label VARCHAR(50) NOT NULL DEFAULT 'image',
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_svc_uc (service, use_case)
                )
            """))
        if "usage_log" not in tables:
            conn.execute(text("""
                CREATE TABLE usage_log (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    service VARCHAR(50) NOT NULL,
                    use_case VARCHAR(50) NOT NULL,
                    model VARCHAR(300) NOT NULL,
                    units FLOAT NOT NULL DEFAULT 0,
                    output_units FLOAT NOT NULL DEFAULT 0,
                    cost_usd FLOAT NOT NULL DEFAULT 0,
                    meta JSON NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_created (created_at),
                    INDEX idx_service (service)
                )
            """))
        if "posts" in tables:
            conn.execute(text("ALTER TABLE posts MODIFY COLUMN network ENUM('instagram','tiktok','both','wordpress','twitter') NOT NULL DEFAULT 'instagram'"))
        if "apartments" in tables:
            apt_cols = {r[0] for r in conn.execute(text("SHOW COLUMNS FROM apartments")).fetchall()}
            if "place_type" not in apt_cols:
                conn.execute(text("ALTER TABLE apartments ADD COLUMN place_type VARCHAR(100) NULL AFTER name"))
            if "render_image" not in apt_cols:
                conn.execute(text("ALTER TABLE apartments ADD COLUMN render_image VARCHAR(500) NULL"))
        if "rooms" in tables:
            room_cols = {r[0] for r in conn.execute(text("SHOW COLUMNS FROM rooms")).fetchall()}
            if "render_image" not in room_cols:
                conn.execute(text("ALTER TABLE rooms ADD COLUMN render_image VARCHAR(500) NULL"))
        if "api_keys" not in tables:
            conn.execute(text("""
                CREATE TABLE api_keys (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    service VARCHAR(50) NOT NULL,
                    label VARCHAR(200) NOT NULL,
                    key_value VARCHAR(500) NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """))
            # Seed from env vars if present
            import os as _os
            for svc, env_var, lbl in [
                ("replicate",  "REPLICATE_API_TOKEN", "Default (from env)"),
                ("elevenlabs", "ELEVENLABS_API_KEY",  "Default (from env)"),
                ("anthropic",  "ANTHROPIC_API_KEY",   "Default (from env)"),
                ("openai",     "OPENAI_API_KEY",      "Default (from env)"),
            ]:
                val = _os.getenv(env_var, "")
                if val:
                    conn.execute(text(
                        "INSERT INTO api_keys (service, label, key_value, is_active) VALUES (:s, :l, :v, TRUE)"
                    ), {"s": svc, "l": lbl, "v": val})
        if "character_media" in tables:
            cm_cols = {r[0] for r in conn.execute(text("SHOW COLUMNS FROM character_media")).fetchall()}
            if "photo_type" not in cm_cols:
                conn.execute(text("ALTER TABLE character_media ADD COLUMN photo_type VARCHAR(50) NULL"))
        if "place_media" not in tables:
            conn.execute(text("""
                CREATE TABLE place_media (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    apartment_id INT NOT NULL,
                    photo_type VARCHAR(50) NULL,
                    file_path VARCHAR(500) NULL,
                    label VARCHAR(200) NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (apartment_id) REFERENCES apartments(id) ON DELETE CASCADE
                )
            """))
        if "room_media" not in tables:
            conn.execute(text("""
                CREATE TABLE room_media (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    room_id INT NOT NULL,
                    photo_type VARCHAR(50) NULL,
                    file_path VARCHAR(500) NULL,
                    label VARCHAR(200) NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE
                )
            """))
        if "prompt_defaults" in tables:
            pd_cols = {r[0] for r in conn.execute(text("SHOW COLUMNS FROM prompt_defaults")).fetchall()}
            if "text_provider" not in pd_cols:
                conn.execute(text("ALTER TABLE prompt_defaults ADD COLUMN text_provider VARCHAR(20) NOT NULL DEFAULT 'claude'"))
            if "safety_tolerance" not in pd_cols:
                conn.execute(text("ALTER TABLE prompt_defaults ADD COLUMN safety_tolerance INT NOT NULL DEFAULT 5"))
            if "output_quality" not in pd_cols:
                conn.execute(text("ALTER TABLE prompt_defaults ADD COLUMN output_quality INT NOT NULL DEFAULT 90"))
            if "output_format" not in pd_cols:
                conn.execute(text("ALTER TABLE prompt_defaults ADD COLUMN output_format VARCHAR(10) NOT NULL DEFAULT 'jpg'"))
            if "prompt_upsampling" not in pd_cols:
                conn.execute(text("ALTER TABLE prompt_defaults ADD COLUMN prompt_upsampling TINYINT(1) NOT NULL DEFAULT 0"))
            if "seed" not in pd_cols:
                conn.execute(text("ALTER TABLE prompt_defaults ADD COLUMN seed INT NULL"))
            if "aspect_ratio" not in pd_cols:
                conn.execute(text("ALTER TABLE prompt_defaults ADD COLUMN aspect_ratio VARCHAR(10) NOT NULL DEFAULT '4:5'"))
        if "clothing_items" in tables:
            ci_cols = {r[0] for r in conn.execute(text("SHOW COLUMNS FROM clothing_items")).fetchall()}
            if "gender" not in ci_cols:
                conn.execute(text("ALTER TABLE clothing_items ADD COLUMN gender ENUM('female','male','non_binary','other') NULL AFTER prompt_tag"))
        if "character_languages" not in tables:
            conn.execute(text("""
                CREATE TABLE character_languages (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    character_id INT NOT NULL,
                    language_code VARCHAR(10) NOT NULL,
                    language_name VARCHAR(100) NOT NULL,
                    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
                    proficiency VARCHAR(50) NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
                )
            """))
        if "character_media" not in tables:
            conn.execute(text("""
                CREATE TABLE character_media (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    character_id INT NOT NULL,
                    file_path VARCHAR(500) NULL,
                    file_type ENUM('photo','video','audio') NOT NULL DEFAULT 'photo',
                    prompt TEXT NULL,
                    label VARCHAR(200) NULL,
                    position INT NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
                )
            """))
        if "prompt_defaults" not in tables:
            conn.execute(text("""
                CREATE TABLE prompt_defaults (
                    id INT PRIMARY KEY DEFAULT 1,
                    positive TEXT NULL,
                    negative TEXT NULL,
                    style TEXT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("""
                INSERT INTO prompt_defaults (id, positive, negative, style) VALUES (
                    1,
                    'photorealistic, ultra-detailed, 8k resolution, professional photography, sharp focus, natural skin texture, cinematic lighting, real person',
                    'anime, cartoon, illustration, 3d render, cgi, painting, drawing, sketch, manga, unrealistic, deformed, disfigured, bad anatomy, extra limbs, watermark, text, logo',
                    'lifestyle photography, candid shot, natural colors'
                )
            """))
        if "strategies" not in tables:
            conn.execute(text("""
                CREATE TABLE strategies (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    character_id INT NULL,
                    name VARCHAR(255) NOT NULL,
                    goal TEXT NULL,
                    tone VARCHAR(255) NULL,
                    mix_photos INT NOT NULL DEFAULT 3,
                    mix_carousels INT NOT NULL DEFAULT 1,
                    mix_videos INT NOT NULL DEFAULT 1,
                    mix_tweets INT NOT NULL DEFAULT 1,
                    mix_blogs INT NOT NULL DEFAULT 0,
                    topics JSON NULL,
                    scene_guidelines TEXT NULL,
                    hashtags JSON NULL,
                    best_days JSON NULL,
                    best_times_utc JSON NULL,
                    notes TEXT NULL,
                    is_active TINYINT(1) NOT NULL DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """))


def _seed():
    """Seed Alex and her apartment/rooms/wardrobe if the DB is empty."""
    from db.database import SessionLocal
    from db.models import Character, Place, Room, ClothingItem
    from core.character import load_yaml, yaml_to_db_fields

    db = SessionLocal()
    try:
        if db.query(Character).count() > 0:
            return

        # ── Character ──────────────────────────────────────────────────────
        try:
            y = load_yaml("character.yaml")
        except FileNotFoundError:
            print("[seed] character.yaml not found, skipping")
            return

        char = Character(**yaml_to_db_fields(y))
        db.add(char)
        db.flush()
        print(f"[seed] Character '{char.name}' id={char.id}")

        # ── Place ──────────────────────────────────────────────────────────
        apt_yaml = y.get("apartment", {})
        apt = Place(
            character_id=char.id,
            name="Buenos Aires apartment",
            place_type="apartment",
            location=apt_yaml.get("location", "Buenos Aires, Argentina"),
            building_style="Classic porteño pre-war residential",
            building_notes=(
                "Ornate stone facade, iron balconies, tall windows with wood shutters. "
                "Old hydraulic cage elevator: ornate iron outer gate, folding inner wood door, "
                "small cabin with mirror, brass fittings. "
                "Hallway: black-and-white hexagonal tile floor, decorative plaster moldings, "
                "warm incandescent wall sconces."
            ),
            is_primary=True,
        )
        db.add(apt)
        db.flush()
        print(f"[seed] Place '{apt.name}' id={apt.id}")

        # ── Rooms ──────────────────────────────────────────────────────────
        rooms_yaml = apt_yaml.get("rooms", {})
        room_seeds = [
            ("bedroom", "Bedroom", rooms_yaml.get("bedroom", {}).get("description",
                "Queen bed centered against wall, two white minimalist nightstands, "
                "large wooden dresser with 50-inch flat screen TV, parquet floor, "
                "tall windows with wood shutters"),
                rooms_yaml.get("bedroom", {}).get("mood", "cozy, warm, minimal clutter")),
            ("office", "Office / Study", rooms_yaml.get("office", {}).get("description",
                "Floor-to-ceiling wooden bookshelf filled with books, white modern standing desk, "
                "large comfortable armchair, round ottoman puff, parquet floor, good natural window light"),
                rooms_yaml.get("office", {}).get("mood", "intellectual, focused, warm light")),
            ("bathroom", "Bathroom", rooms_yaml.get("bathroom", {}).get("description",
                "Between the two bedrooms, subway tiles, pedestal sink, chrome fittings, "
                "frameless mirror with warm sconce"),
                "minimal, functional"),
            ("kitchen", "Kitchen / Breakfast nook", rooms_yaml.get("kitchen", {}).get("description",
                "Open kitchen connected to living room, breakfast nook with small table and two chairs "
                "by the window, modern appliances, tile backsplash"),
                rooms_yaml.get("kitchen", {}).get("mood", "morning light, warm, practical")),
            ("living_room", "Living Room", rooms_yaml.get("living_room", {}).get("description",
                "Round industrial dining table with metal legs near kitchen, large light gray corner sofa, "
                "rectangular coffee table on a fluffy shaggy rug, flat screen TV on black industrial rack, "
                "parquet floor, tall windows, high ceilings with decorative plaster moldings"),
                rooms_yaml.get("living_room", {}).get("mood", "lived-in, industrial meets classic BA")),
        ]
        for rtype, rname, rdesc, rmood in room_seeds:
            r = Room(apartment_id=apt.id, room_type=rtype, name=rname, description=rdesc, mood=rmood)
            db.add(r)
        print(f"[seed] {len(room_seeds)} rooms added")

        # ── Wardrobe ───────────────────────────────────────────────────────
        from db.models import ClothingCategory, ClothingStyle
        wardrobe_seeds = [
            ("Nike Pro gym leggings", ClothingCategory.activewear, ClothingStyle.gym,
             "Nike", "black", "high-waist compression leggings", "black Nike Pro gym leggings"),
            ("Sports bra", ClothingCategory.activewear, ClothingStyle.gym,
             None, "black", "basic sports bra for gym and yoga", "black sports bra"),
            ("Oversized hoodie", ClothingCategory.top, ClothingStyle.casual,
             None, "grey", "soft oversized hoodie worn at home", "grey oversized hoodie"),
            ("White linen shirt", ClothingCategory.top, ClothingStyle.casual,
             None, "white", "relaxed fit linen shirt for everyday", "white linen shirt"),
            ("Tailored blazer", ClothingCategory.suit, ClothingStyle.business,
             None, "navy", "fitted navy blazer for meetings", "fitted navy blazer"),
            ("Tailored trousers", ClothingCategory.bottom, ClothingStyle.business,
             None, "navy", "matching trousers for the navy blazer", "navy tailored trousers"),
            ("Running shoes", ClothingCategory.shoes, ClothingStyle.outdoor,
             "Nike", "white/grey", "everyday running shoes", "white Nike running shoes"),
            ("Noise-cancelling headphones", ClothingCategory.accessory, ClothingStyle.casual,
             "Sony", "black", "Sony WH-1000XM5, always around her neck or on her head",
             "black Sony WH-1000XM5 headphones"),
            ("Kindle", ClothingCategory.accessory, ClothingStyle.casual,
             "Amazon", "black", "Kindle Paperwhite, used daily on the sofa", "Kindle Paperwhite"),
            ("iPhone", ClothingCategory.accessory, ClothingStyle.casual,
             "Apple", "black", "iPhone, always in hand or on the table", "iPhone"),
        ]
        for name, cat, sty, brand, color, desc, prompt_tag in wardrobe_seeds:
            db.add(ClothingItem(
                character_id=char.id, name=name, category=cat, style=sty,
                brand=brand, color=color, description=desc, prompt_tag=prompt_tag,
            ))
        print(f"[seed] {len(wardrobe_seeds)} wardrobe items added")

        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrate()
    _seed()

    from worker.publisher import publish_due_posts
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(publish_due_posts, "interval", seconds=60, id="publisher", max_instances=1)
    scheduler.start()
    print("[app] Publisher cron started (every 60 s).")

    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="ia-girl API",
    description="AI persona content engine — multiple characters, apartments, wardrobe, scheduled posts.",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(characters_router)
app.include_router(places_router)
app.include_router(wardrobe_router)
app.include_router(posts_router)
app.include_router(media_router)
app.include_router(relationships_router)
app.include_router(podcast_router)
app.include_router(character_media_router)
app.include_router(languages_router)
app.include_router(settings_router)
app.include_router(api_keys_router)
app.include_router(training_router)
app.include_router(place_media_router)
app.include_router(liveportrait_router)
app.include_router(model_settings_router)
app.include_router(strategies_router)
app.include_router(email_router)

import pathlib
pathlib.Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=OUTPUT_DIR), name="media")

STATIC_DIR = pathlib.Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))
