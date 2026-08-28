"""
ia-girl — AI persona content engine.

Usage:
  python main.py generate               # Generate one image + caption and print, no posting
  python main.py post                   # Generate + post immediately to all platforms
  python main.py ideas                  # Print 7 content ideas for the week
  python main.py dms                    # Process and reply to pending DMs
  python main.py reel <scene>           # Generate a slideshow reel for the given scene
  python main.py schedule               # Start the automated scheduler (runs forever)
  python main.py renders                # Generate all apartment renders (reference images)
  python main.py renders <room> ...     # Generate renders for specific rooms only
                                        # rooms: building_facade elevator hallway living_room
                                        #        office bedroom kitchen bathroom
"""

import sys
import os
from dotenv import load_dotenv

load_dotenv()

from core.character import load
from core.image_gen import generate
from core.content_gen import caption, dm_reply, content_ideas
from core.video_gen import slideshow

char = load()


def cmd_generate() -> None:
    import random
    scene = random.choice(char["visual"]["settings"])
    print(f"Scene: {scene}\n")
    image_path = generate(scene, char=char)
    cap = caption(scene, char=char)
    print(f"Caption:\n{cap}\n")
    print(f"Image: {image_path}")


def cmd_post() -> None:
    import random
    scene = random.choice(char["visual"]["settings"])
    image_path = generate(scene, char=char)
    cap = caption(scene, char=char)
    print(f"Caption:\n{cap}\n")

    if char["platforms"]["instagram"]["enabled"]:
        from platforms.instagram import post_photo
        post_photo(image_path, cap)

    print("Posted.")


def cmd_ideas() -> None:
    ideas = content_ideas(7, char=char)
    print("Content ideas for the week:\n")
    for i, idea in enumerate(ideas, 1):
        print(f"  {i}. {idea}")


def cmd_dms() -> None:
    if not char["platforms"]["instagram"]["enabled"]:
        print("Instagram is disabled in character.yaml")
        return
    from platforms.instagram import get_pending_dms, send_dm
    pending = get_pending_dms()
    if not pending:
        print("No pending DMs.")
        return
    for dm in pending:
        print(f"\n@{dm['username']}: {dm['message']}")
        reply = dm_reply(dm["message"], char=char)
        print(f"Reply: {reply}")
        confirm = input("Send? [y/N] ").strip().lower()
        if confirm == "y":
            send_dm(dm["thread_id"], reply)


def cmd_reel(scene: str) -> None:
    print(f"Generating 3 images for reel: {scene}")
    from core.image_gen import generate_batch
    images = generate_batch([scene] * 3, char=char, aspect_ratio="9:16")
    video = slideshow(images, duration_per_image=3.0)
    cap = caption(scene, mood="casual", char=char)
    print(f"\nCaption:\n{cap}")
    print(f"\nReel: {video}")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return

    cmd = args[0]
    if cmd == "generate":
        cmd_generate()
    elif cmd == "post":
        cmd_post()
    elif cmd == "ideas":
        cmd_ideas()
    elif cmd == "dms":
        cmd_dms()
    elif cmd == "reel":
        scene = " ".join(args[1:]) if len(args) > 1 else "beach walk at sunset, miami"
        cmd_reel(scene)
    elif cmd == "schedule":
        from scheduler import run
        run()
    elif cmd == "renders":
        from core.renders import generate_all, SCENES
        valid_keys = {s["key"] for s in SCENES}
        only = [a for a in args[1:] if a in valid_keys] or None
        if args[1:] and not only:
            print(f"Unknown room(s): {args[1:]}. Valid: {sorted(valid_keys)}")
        else:
            generate_all(only=only)
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
