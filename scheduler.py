"""
Content scheduler.

Runs a daily job that:
  1. Generates a scene idea (via Claude)
  2. Generates the image (via Replicate/Flux)
  3. Writes a caption (via Claude)
  4. Posts to enabled platforms

Also runs a DM reply job every 30 minutes.
"""

import os
import random
from pathlib import Path
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from core.character import load
from core.image_gen import generate
from core.content_gen import caption, dm_reply, content_ideas

char = load()


def post_job() -> None:
    """Generate and post one piece of content."""
    print("\n[scheduler] Running post job...")

    # Pick a random visual setting from character.yaml
    settings = char["visual"]["settings"]
    scene = random.choice(settings)

    # Generate image
    image_path = generate(scene, char=char, aspect_ratio="4:5")

    # Write caption
    cap = caption(scene, char=char)
    print(f"[scheduler] Caption:\n{cap}\n")

    # Post to enabled platforms
    if char["platforms"]["instagram"]["enabled"]:
        from platforms.instagram import post_photo
        post_photo(image_path, cap)

    print("[scheduler] Post job done.")


def dm_reply_job() -> None:
    """Fetch and reply to pending Instagram DMs."""
    if not char["platforms"]["instagram"]["enabled"]:
        return

    from platforms.instagram import get_pending_dms, send_dm

    pending = get_pending_dms(limit=10)
    if not pending:
        print("[scheduler] No pending DMs.")
        return

    for dm in pending:
        print(f"[scheduler] DM from @{dm['username']}: {dm['message'][:80]}")
        reply = dm_reply(dm["message"], char=char)
        send_dm(dm["thread_id"], reply)
        print(f"[scheduler] Replied: {reply[:80]}")


def run() -> None:
    sched = BlockingScheduler(timezone="UTC")

    # Post jobs — use times from character.yaml
    for time_str in char["posting"]["best_times_utc"]:
        hour, minute = map(int, time_str.split(":"))
        sched.add_job(
            post_job,
            CronTrigger(hour=hour, minute=minute),
            id=f"post_{hour}_{minute}",
            max_instances=1,
        )
        print(f"[scheduler] Scheduled post at {time_str} UTC")

    # DM reply job — every 30 minutes
    sched.add_job(
        dm_reply_job,
        "interval",
        minutes=30,
        id="dm_replies",
        max_instances=1,
    )
    print("[scheduler] DM reply job every 30 min")

    print("[scheduler] Starting. Press Ctrl+C to stop.\n")
    sched.start()
