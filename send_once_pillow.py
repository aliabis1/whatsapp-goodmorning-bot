# send_once_pillow.py
# WhatsApp Good Morning bot with:
# - Unsplash API backgrounds (soft, aesthetic)
# - Deep varied quotes (life lessons, hardships, integrity, friendship, humanity, wellbeing, etc.)
# - Pillow text overlay (script "Good morning" + centered quote)

import os
import io
import time
import re
import random
import textwrap
import datetime

from dotenv import load_dotenv
from twilio.rest import Client
from openai import OpenAI
import cloudinary
import cloudinary.uploader
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

# -------------------------------------------------------------------
# Load environment
# -------------------------------------------------------------------
load_dotenv()

CAPTION_MODE = "short"        # "none" | "short" | "full"
MAX_RETRIES  = 8              # retries for Unsplash API

# Curated queries matching your aesthetic (soft, pastel, calm)
UNSPLASH_QUERIES = [
    "pastel sunrise ocean minimal",
    "lavender sky morning aesthetic",
    "pink sunrise beach soft focus",
    "calm ocean pastel horizon",
    "bokeh flowers morning light",
    "poppies field pastel aesthetic",
    "misty mountains soft light",
    "calm lake reflection sunrise",
    "foggy forest minimal morning",
    "soft floral background dreamy",
    "wheat field sunrise pastel",
]

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")

# -------------------------------------------------------------------
# Clients
# -------------------------------------------------------------------
twilio = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
oai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

# -------------------------------------------------------------------
# Time helper
# -------------------------------------------------------------------
def muscat_now():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=4)

# -------------------------------------------------------------------
# Quote generation (FINAL VERSION)
# -------------------------------------------------------------------
def get_quote_via_api() -> str:
    """
    Generate a deep, varied quote with strong anti-repetition rules.
    We ask for 5 quotes and randomly pick one.
    """

    SYS = """
You are a quote writer.

Write deep, meaningful, ORIGINAL motivational quotes.

STYLE:
- Practical and punchy, not dreamy or poetic.
- Feels like something a wise mentor or self-growth author would say.
- Simple language but emotionally strong.
- Max 18–22 words per quote.
- Must fit cleanly on a motivational image.

TOPICS (mix these, choose 1 per quote):
- Life lessons
- Hardship & resilience
- Integrity & character
- Humanity & kindness
- Friendship & loyalty
- Self-worth & boundaries
- Consistency & discipline
- Emotional strength
- Wellbeing & mental clarity

STRICT RULES for each quote:
- 1–2 sentences only.
- No emojis.
- Do NOT mention morning, sunrise, dawn, sunset, night, or any time of day.
- Do NOT mention weekdays or dates.
- Do NOT include the words "good morning".
- Avoid clichés such as “new beginnings”, “fresh start”, “rise and shine”, “follow your dreams”.
- Avoid starting with: "In the", "In this", "Sometimes", "When we", "When you", "As we", "As you", "There is", "Life is".
- Avoid metaphors about weather, sky, light, breeze, horizon, canvas, oceans of time, etc.
- No rhymes. No hashtags. No exclamation overload.
- Each quote must have a clearly different structure and wording from the others.

OUTPUT:
- Return exactly 5 different quotes.
- Each quote on its own separate line.
- No numbers, bullets, dashes or quote marks around them.
    """.strip()

    user_msg = "Write 5 different quotes now, following all the rules."

    resp = oai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYS},
            {"role": "user", "content": user_msg},
        ],
        temperature=1.0,  # higher temperature for more variety
    )

    raw = resp.choices[0].message.content.strip()

    # Split into individual lines / quotes
    lines = [line.strip() for line in raw.split("\n") if line.strip()]

    # Clean any accidental numbering/bullets
    cleaned = []
    for line in lines:
        # remove leading numbers / bullets like "1. ", "- ", "* "
        line = re.sub(r'^[\-\*\d\.\)\s]+', '', line).strip()
        if line:
            cleaned.append(line)

    if not cleaned:
        # fallback in the rare case the API misbehaves
        return "Discipline builds the life that motivation only talks about."

    # Randomly pick one so each run feels different
    return random.choice(cleaned)

# -------------------------------------------------------------------
# Background image via Unsplash API
# -------------------------------------------------------------------
def _fetch_unsplash_via_api() -> Image.Image:
    """
    Fetch a random aesthetic landscape from Unsplash API using curated queries.
    """
    if not UNSPLASH_ACCESS_KEY:
        raise RuntimeError("UNSPLASH_ACCESS_KEY is not set in .env")

    headers = {
        "Accept-Version": "v1",
        "Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        query = random.choice(UNSPLASH_QUERIES)
        params = {
            "query": query,
            "orientation": "landscape",
            "content_filter": "high",
        }
        print(f"[Unsplash API] Attempt {attempt}/{MAX_RETRIES}, query='{query}'")
        try:
            r = requests.get(
                "https://api.unsplash.com/photos/random",
                headers=headers,
                params=params,
                timeout=20,
            )
            if r.status_code != 200:
                print(f"  ❌ Status {r.status_code}: {r.text[:120]} ... Retrying...")
                time.sleep(0.8)
                continue

            data = r.json()
            if isinstance(data, list) and data:
                data = data[0]

            img_url = data["urls"].get("regular") or data["urls"]["full"]
            print("  ✔️ Got image URL:", img_url)

            img_resp = requests.get(img_url, timeout=20)
            img_resp.raise_for_status()
            img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
            return img

        except Exception as e:
            print(f"  ❌ Error: {e} — retrying...")
            time.sleep(0.8)

    raise RuntimeError("Failed to fetch an Unsplash image via API after retries.")

def _get_background_image() -> Image.Image:
    img = _fetch_unsplash_via_api()
    img = ImageOps.fit(img, (1024, 1024), Image.LANCZOS)
    return img

# -------------------------------------------------------------------
# Fonts & composition
# -------------------------------------------------------------------
def _load_font(size: int, script: bool = False) -> ImageFont.FreeTypeFont:
    """
    Try some common fonts. If not found, fall back to default.
    script=True -> for 'Good morning'
    script=False -> for body quote
    """
    if script:
        candidates = [
            "C:/Windows/Fonts/Segoe Script.ttf",
            "C:/Windows/Fonts/segoesc.ttf",
            "/System/Library/Fonts/Supplemental/SnellRoundhand.ttf",
            "/System/Library/Fonts/Supplemental/Brush Script.ttf",
        ]
    else:
        candidates = [
            "C:/Windows/Fonts/SegoeUI.ttf",
            "C:/Windows/Fonts/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ]

    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)

    return ImageFont.load_default()

def compose_image_with_pillow(quote_text: str) -> Image.Image:
    base = _get_background_image()

    W, H = base.size
    base_rgba = base.convert("RGBA")
    overlay = Image.new("RGBA", base_rgba.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Typography
    title_font = _load_font(max(48, W // 12), script=True)   # script-style "Good morning"
    body_font  = _load_font(max(32, W // 22), script=False)  # clean sans-serif

    title_text = "Good morning"

    # Wrap quote
    body_lines = textwrap.wrap(quote_text, width=26)

    # Colors
    TEXT_COLOR   = (70, 60, 130, 255)    # soft purple
    BOX_COLOR    = (255, 255, 255, 210)  # semi-transparent white
    SHADOW_COLOR = (0, 0, 0, 80)         # subtle shadow

    # Measure text
    title_box = draw.textbbox((0, 0), title_text, font=title_font)
    title_w = title_box[2] - title_box[0]
    title_h = title_box[3] - title_box[1]

    line_boxes   = [draw.textbbox((0, 0), line, font=body_font) for line in body_lines]
    line_sizes   = [(b[2] - b[0], b[3] - b[1]) for b in line_boxes]
    line_heights = [h for (_, h) in line_sizes]
    body_h = sum(line_heights) + 10 * max(0, (len(line_heights) - 1))

    margin    = int(W * 0.08)
    box_width = W - 2 * margin
    box_height = title_h + 30 + body_h + 40

    x0 = margin
    y0 = H // 2 - box_height // 2  # center vertically

    # Rounded semi-transparent box
    draw.rounded_rectangle(
        (x0, y0, x0 + box_width, y0 + box_height),
        radius=35,
        fill=BOX_COLOR,
    )

    # Title (centered)
    title_x = W // 2 - title_w // 2
    title_y = y0 + 20

    draw.text((title_x + 2, title_y + 2), title_text, font=title_font, fill=SHADOW_COLOR)
    draw.text((title_x,       title_y),    title_text, font=title_font, fill=TEXT_COLOR)

    # Body (centered)
    text_y = title_y + title_h + 15
    for (line, (lw, lh)) in zip(body_lines, line_sizes):
        line_x = W // 2 - lw // 2
        draw.text((line_x + 1, text_y + 1), line, font=body_font, fill=SHADOW_COLOR)
        draw.text((line_x,       text_y),    line, font=body_font, fill=TEXT_COLOR)
        text_y += lh + 10

    composed = Image.alpha_composite(base_rgba, overlay).convert("RGB")
    return composed

# -------------------------------------------------------------------
# Cloudinary + WhatsApp
# -------------------------------------------------------------------
def upload_to_cloudinary(pil_image: Image.Image) -> str:
    buf = io.BytesIO()
    pil_image.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    res = cloudinary.uploader.upload(
        buf,
        folder="whatsapp_agent_pillow",
        resource_type="image",
        overwrite=True,
    )
    return res["secure_url"]

def make_caption(quote: str) -> str:
    if CAPTION_MODE == "none":
        return ""
    if CAPTION_MODE == "short":
        return "🌞 Good morning!"
    return f"🌞 {quote}"

def send_whatsapp(caption: str, media_url: str):
    kwargs = {
        "from_": os.getenv("WHATSAPP_FROM"),
        "to":   os.getenv("WHATSAPP_TO"),
        "media_url": [media_url],
    }
    if caption.strip():
        kwargs["body"] = caption
    msg = twilio.messages.create(**kwargs)
    print("✔️ WhatsApp SID:", msg.sid)

# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------
if __name__ == "__main__":
    quote  = get_quote_via_api()
    print("QUOTE CHOSEN:", quote)
    img    = compose_image_with_pillow(quote)
    url    = upload_to_cloudinary(img)
    caption = make_caption(quote)

    print("Image URL:", url)
    send_whatsapp(caption, url)
    print("🎉 Sent upgraded aesthetic image + varied quote.")
