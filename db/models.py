import enum
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Enum, String, Text, DateTime, Integer, Boolean, ForeignKey, JSON, Float, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


class ModelSetting(Base):
    """Active model + pricing for each service/use-case combination."""
    __tablename__ = "model_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service: Mapped[str] = mapped_column(String(50), nullable=False)    # replicate | xai | anthropic | openai
    use_case: Mapped[str] = mapped_column(String(50), nullable=False)   # base_image | kontext_image | grok_image | caption | content
    model_name: Mapped[str] = mapped_column(String(300), nullable=False)
    price_per_unit: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)        # per image or per 1M input tokens
    price_per_output_unit: Mapped[float] = mapped_column(Float, nullable=False, default=0.0) # per 1M output tokens (0 for images)
    unit_label: Mapped[str] = mapped_column(String(50), nullable=False, default="image")     # 'image' | '1M tokens'
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class UsageLog(Base):
    """One row per AI generation call — tracks model used and estimated cost."""
    __tablename__ = "usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service: Mapped[str] = mapped_column(String(50), nullable=False)
    use_case: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(300), nullable=False)
    units: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)         # images: 1; text: input_tokens/1M
    output_units: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # text: output_tokens/1M
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ApiKey(Base):
    """A named API key for an external service. Only one key per service can be active."""
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service: Mapped[str] = mapped_column(String(50), nullable=False)   # replicate | elevenlabs
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    key_value: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class PromptDefaults(Base):
    """
    Singleton row (id=1) — global prompt components merged into every image generation.

    positive: prepended before the character's base prompt (quality/realism baseline)
    negative: merged with the character's negative prompt (things to always avoid)
    style:    appended after the character's style (overarching style qualifier)
    """
    __tablename__ = "prompt_defaults"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    positive: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    negative: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    style: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text_provider: Mapped[str] = mapped_column(String(20), nullable=False, server_default="claude")
    # Replicate / Flux generation defaults
    safety_tolerance: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    output_quality: Mapped[int] = mapped_column(Integer, nullable=False, server_default="90")
    output_format: Mapped[str] = mapped_column(String(10), nullable=False, server_default="jpg")
    prompt_upsampling: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    aspect_ratio: Mapped[str] = mapped_column(String(10), nullable=False, server_default="4:5")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class MediaType(str, enum.Enum):
    photo = "photo"
    video = "video"
    audio = "audio"


class Network(str, enum.Enum):
    instagram = "instagram"
    tiktok = "tiktok"
    both = "both"
    wordpress = "wordpress"
    twitter = "twitter"


class PostStatus(str, enum.Enum):
    pending = "pending"
    to_be_published = "to_be_published"
    published = "published"
    failed = "failed"


class Gender(str, enum.Enum):
    female = "female"
    male = "male"
    non_binary = "non_binary"
    other = "other"


class RelationshipType(str, enum.Enum):
    friend = "friend"
    colleague = "colleague"
    podcast_co_host = "podcast_co_host"
    partner = "partner"
    family = "family"
    rival = "rival"
    mentor = "mentor"
    other = "other"


class ClothingCategory(str, enum.Enum):
    top = "top"
    bottom = "bottom"
    dress = "dress"
    outerwear = "outerwear"
    shoes = "shoes"
    accessory = "accessory"
    bag = "bag"
    activewear = "activewear"
    suit = "suit"
    other = "other"


class ClothingStyle(str, enum.Enum):
    casual = "casual"
    gym = "gym"
    formal = "formal"
    business = "business"
    loungewear = "loungewear"
    outdoor = "outdoor"
    other = "other"


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    nationality: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    gender: Mapped[Optional[Gender]] = mapped_column(Enum(Gender), nullable=True, default=Gender.female)
    voice_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    personality_traits: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    personality_interests: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    language_style: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    visual_base_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    visual_style: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    visual_negative_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    visual_settings: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    posting_frequency: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    posting_times_utc: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    instagram_username: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    instagram_password: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    instagram_session_id: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    instagram_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tiktok_session_id: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    tiktok_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    email_address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email_password: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    email_imap_host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email_imap_port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    email_smtp_host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email_smtp_port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    profile_bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    profile_picture: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    character_bible: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trigger_word: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    replicate_model: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    replicate_training_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    training_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    training_place_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    posts: Mapped[List["Post"]] = relationship("Post", back_populates="character")
    places: Mapped[List["Place"]] = relationship("Place", back_populates="character", cascade="all, delete-orphan")
    wardrobe: Mapped[List["ClothingItem"]] = relationship("ClothingItem", back_populates="character")
    relationships_as_a: Mapped[List["CharacterRelationship"]] = relationship(
        "CharacterRelationship", foreign_keys="CharacterRelationship.character_a_id", cascade="all, delete-orphan"
    )
    relationships_as_b: Mapped[List["CharacterRelationship"]] = relationship(
        "CharacterRelationship", foreign_keys="CharacterRelationship.character_b_id", cascade="all, delete-orphan"
    )
    media: Mapped[List["CharacterMedia"]] = relationship(
        "CharacterMedia", back_populates="character", cascade="all, delete-orphan",
        order_by="CharacterMedia.position",
    )
    languages: Mapped[List["CharacterLanguage"]] = relationship(
        "CharacterLanguage", back_populates="character", cascade="all, delete-orphan",
    )


class CharacterLanguage(Base):
    """Junction table: which languages a character speaks, with proficiency and whether it's primary."""
    __tablename__ = "character_languages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(Integer, ForeignKey("characters.id"), nullable=False)
    language_code: Mapped[str] = mapped_column(String(10), nullable=False)  # ISO 639-1 e.g. 'es', 'en', 'pt'
    language_name: Mapped[str] = mapped_column(String(100), nullable=False)  # 'Spanish', 'English', 'Portuguese'
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    proficiency: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # native, fluent, conversational, basic
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    character: Mapped["Character"] = relationship("Character", back_populates="languages")


class CharacterRelationship(Base):
    __tablename__ = "character_relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    character_a_id: Mapped[int] = mapped_column(Integer, ForeignKey("characters.id"), nullable=False)
    character_b_id: Mapped[int] = mapped_column(Integer, ForeignKey("characters.id"), nullable=False)
    relationship_type: Mapped[RelationshipType] = mapped_column(Enum(RelationshipType), nullable=False, default=RelationshipType.friend)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    character_a: Mapped["Character"] = relationship("Character", foreign_keys=[character_a_id])
    character_b: Mapped["Character"] = relationship("Character", foreign_keys=[character_b_id])


class Place(Base):
    """A location a character owns or frequents: apartment, office, park, studio, café, etc."""
    __tablename__ = "apartments"  # keep DB table name for backward compatibility

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(Integer, ForeignKey("characters.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    place_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # apartment, office, park, café, studio…
    location: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    building_style: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    building_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    render_image: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    character: Mapped["Character"] = relationship("Character", back_populates="places")
    rooms: Mapped[List["Room"]] = relationship("Room", back_populates="place", cascade="all, delete-orphan")
    media: Mapped[List["PlaceMedia"]] = relationship("PlaceMedia", back_populates="place", cascade="all, delete-orphan")


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    apartment_id: Mapped[int] = mapped_column(Integer, ForeignKey("apartments.id"), nullable=False)
    room_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mood: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    render_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    render_image: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    place: Mapped["Place"] = relationship("Place", back_populates="rooms")
    media: Mapped[List["RoomMedia"]] = relationship("RoomMedia", back_populates="room", cascade="all, delete-orphan")


class ClothingItem(Base):
    __tablename__ = "clothing_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(Integer, ForeignKey("characters.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[ClothingCategory] = mapped_column(Enum(ClothingCategory), nullable=False)
    style: Mapped[ClothingStyle] = mapped_column(Enum(ClothingStyle), nullable=False, default=ClothingStyle.casual)
    brand: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_tag: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)  # text to inject into image prompts
    gender: Mapped[Optional[Gender]] = mapped_column(Enum(Gender), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    character: Mapped["Character"] = relationship("Character", back_populates="wardrobe")


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    character_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("characters.id"), nullable=True)
    character_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    scene: Mapped[str] = mapped_column(String(500), nullable=False)
    mood: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="casual")
    caption_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    caption_length_words: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    script: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    wardrobe_items: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # list of ClothingItem IDs
    place_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)       # FK to apartments.id (no constraint for simplicity)
    room_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)        # FK to rooms.id
    media_type: Mapped[MediaType] = mapped_column(Enum(MediaType), nullable=False, default=MediaType.photo)
    network: Mapped[Network] = mapped_column(Enum(Network), nullable=False, default=Network.instagram)
    status: Mapped[PostStatus] = mapped_column(Enum(PostStatus), nullable=False, default=PostStatus.pending)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    publish_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    character: Mapped[Optional["Character"]] = relationship("Character", back_populates="posts")
    media_items: Mapped[List["PostMedia"]] = relationship(
        "PostMedia", back_populates="post", cascade="all, delete-orphan",
        order_by="PostMedia.position",
    )


class CharacterMedia(Base):
    __tablename__ = "character_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(Integer, ForeignKey("characters.id"), nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_type: Mapped[MediaType] = mapped_column(Enum(MediaType), nullable=False, default=MediaType.photo)
    photo_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # face|body|feet|hair|…
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    character: Mapped["Character"] = relationship("Character", back_populates="media")


class PlaceMedia(Base):
    """Real photos of a building/location, typed by angle/area."""
    __tablename__ = "place_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    apartment_id: Mapped[int] = mapped_column(Integer, ForeignKey("apartments.id"), nullable=False)
    photo_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    place: Mapped["Place"] = relationship("Place", back_populates="media")


class RoomMedia(Base):
    """Real photos of a room, typed by angle/area."""
    __tablename__ = "room_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(Integer, ForeignKey("rooms.id"), nullable=False)
    photo_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    room: Mapped["Room"] = relationship("Room", back_populates="media")


class PostMedia(Base):
    __tablename__ = "post_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("posts.id", ondelete="SET NULL"), nullable=True)
    character_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("characters.id"), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    reference_image: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_type: Mapped[MediaType] = mapped_column(Enum(MediaType), nullable=False, default=MediaType.photo)
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    gen_params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    post: Mapped[Optional["Post"]] = relationship("Post", back_populates="media_items")
    refs: Mapped[List["PostMediaRef"]] = relationship(
        "PostMediaRef", back_populates="post_media", cascade="all, delete-orphan",
        order_by="PostMediaRef.created_at",
    )


class Strategy(Base):
    """Marketing strategy linked to a character — defines post mix, topics, scene guidelines, and schedule."""
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    character_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("characters.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    goal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tone: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Weekly post mix
    mix_photos: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    mix_carousels: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    mix_videos: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    mix_tweets: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    mix_blogs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Content guidance
    topics: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    scene_guidelines: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hashtags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Scheduling
    best_days: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    best_times_utc: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    character: Mapped[Optional["Character"]] = relationship("Character", backref="strategies")


class PostMediaRef(Base):
    """One reference image attached to a PostMedia slot (many refs per slot)."""
    __tablename__ = "post_media_refs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_media_id: Mapped[int] = mapped_column(Integer, ForeignKey("post_media.id", ondelete="CASCADE"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    post_media: Mapped["PostMedia"] = relationship("PostMedia", back_populates="refs")
