import os
import random
import textwrap
from io import BytesIO

import requests
from dotenv import load_dotenv
from openai import OpenAI
from twilio.rest import Client
from PIL import Image, ImageDraw, ImageFont

import cloudinary
import cloudinary.uploader


# -------------------- ENV & CLIENT SETUP --------------------

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
WHATSAPP_FROM = os.getenv("WHATSAPP_FROM")
WHATSAPP_TO = os.getenv("WHATSAPP_TO")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set in .env")

if not UNSPLASH_ACCESS_KEY:
    raise RuntimeError("UNSPLASH_ACCESS_KEY is not set in .env")

if not CLOUDINARY_CLOUD_NAME or not CLOUDINARY_API_KEY or not CLOUDINARY_API_SECRET:
    raise RuntimeError("Cloudinary credentials are missing in .env")

if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
    raise RuntimeError("Twilio credentials are missing in .env")

if not WHATSAPP_FROM or not WHATSAPP_TO:
    raise RuntimeError("WhatsApp FROM/TO numbers are missing in .env")


oai = OpenAI(api_key=OPENAI_API_KEY)

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
)


# -------------------- FONT HELPERS --------------------

def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """
    Try a few common fonts so it works on Windows + GitHub Actions (Ubuntu).
    Fallback to default bitmap font if none are found.
    """
    candidates = []

    if bold:
        candidates.extend([
            "arialbd.ttf",  # Windows bold Arial
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ])
    else:
        candidates.extend([
            "arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ])

    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue

    # Last resort
    return ImageFont.load_default()


def wrap_text(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw):
    """
    Simple word-wrap so the quote stays nicely inside the card.
    """
    words = text.split()
    lines = []
    current = []

    for w in words:
        current.append(w)
        trial = " ".join(current)
        w_box = draw.textbbox((0, 0), trial, font=font)
        if w_box[2] - w_box[0] > max_width:  # too wide
            # remove last word and start new line
            current.pop()
            lines.append(" ".join(current))
            current = [w]

    if current:
        lines.append(" ".join(current))

    return lines


# -------------------- QUOTE GENERATION --------------------

TOPICS = [
    "life lessons and growth",
    "hardship, struggle, and resilience",
    "kindness and compassion",
    "integrity and doing the right thing",
    "friendship and meaningful connections",
    "humanity and empathy",
    "gratitude and contentment",
    "well-being, balance, and inner peace",
]


def get_quote_via_api() -> str:
    """
    Ask OpenAI for one short, original quote.
    No greetings, no day of week, no repeated template phrases.
    """
    topic = random.choice(TOPICS)

    system_prompt = (
        "You generate original, thoughtful quotes suitable for a good-morning image.\n"
        "Requirements:\n"
        "- 1 to 3 sentences only.\n"
        "- Focus on deep but simple wisdom about everyday life.\n"
        "- Today’s theme: " + topic + ".\n"
        "- Do NOT mention the time of day, morning, dawn, today, or any weekday.\n"
        "- Do NOT start with stock phrases like 'In the quiet...', "
        "'In the gentle embrace...', or similar repeated openings.\n"
        "- Avoid cliches and greeting phrases like 'Good morning', 'Have a great day'.\n"
        "- Write in clear, natural language — no quotes around the text, no author name.\n"
        "- Vary the rhythm and structure from one quote to another."
    )

    user_prompt = "Give me ONE quote that follows the rules. Return only the quote text."

    resp = oai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.9,
        max_tokens=80,
    )

    quote = resp.choices[0].message.content.strip()
    quote = quote.strip('"').strip("“”")
    print(f"QUOTE CHOSEN: {quote}")
    return quote


# -------------------- UNSPLASH + IMAGE COMPOSITION --------------------

UNSPLASH_QUERIES = [
    "soft sunrise over fields, pastel tones, bokeh",
    "misty mountains at dawn, warm light, calm",
    "wildflowers in soft focus, golden hour, dreamy",
    "gentle ocean waves at sunrise, pastel sky",
    "forest path with rays of light, tranquil morning",
    "wheat field in backlight, warm glow, bokeh",
    "calm lake reflections, mountains, early light",
    "wildflower meadow, soft blur, peaceful",
]


def fetch_unsplash_image() -> Image.Image:
    query = random.choice(UNSPLASH_QUERIES)
    print(f"[Unsplash API] Attempt 1/1, query='{query}'")

    url = "https://api.unsplash.com/photos/random"
    headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
    params = {
        "query": query,
        "orientation": "landscape",
        "content_filter": "high",
    }

    r = requests.get(url, headers=headers, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    img_url = data["urls"]["regular"]
    print(f"  ✔️ Got image URL: {img_url}")

    img_resp = requests.get(img_url, timeout=20)
    img_resp.raise_for_status()
    img = Image.open(BytesIO(img_resp.content)).convert("RGBA")

    # Normalize to 1024x1024 for consistency
    img = img.resize((1024, 1024), Image.LANCZOS)
    return img


def compose_image_with_quote(bg_img: Image.Image, quote: str) -> Image.Image:
    """
    Draw a translucent rounded card with:
      - BIG 'Good morning'
      - quote below it
    Card height and quote font size auto-adjust so text never overflows.
    """
    bg_img = bg_img.convert("RGBA")
    W, H = bg_img.size

    # ----- base fonts + limits -----
    max_card_height = int(H * 0.8)
    card_w = int(W * 0.86)
    padding_v = 40  # vertical padding inside card

    # initial font sizes
    title_font_size = int(W * 0.10)
    quote_font_size = int(W * 0.048)

    # temp draw just for measuring
    tmp_draw = ImageDraw.Draw(bg_img)

    # keep shrinking quote font until everything fits in 80% of height
    while True:
        title_font = load_font(title_font_size, bold=True)
        quote_font = load_font(quote_font_size, bold=False)

        # measure title
        t_box = tmp_draw.textbbox((0, 0), "Good morning", font=title_font)
        t_h = t_box[3] - t_box[1]

        # wrap quote with current font
        max_quote_width = int(card_w * 0.88)
        quote_lines = wrap_text(quote, quote_font, max_quote_width, tmp_draw)

        line_height = quote_font_size + 6
        total_q_height = line_height * len(quote_lines)

        content_h = t_h + 30 + total_q_height  # title + gap + quote
        card_h = content_h + padding_v * 2

        if card_h <= max_card_height or quote_font_size <= int(W * 0.032):
            # fits (or we hit minimum size)
            break

        # shrink quote font a bit and try again
        quote_font_size = int(quote_font_size * 0.9)

    # recompute with final sizes to be sure
    title_font = load_font(title_font_size, bold=True)
    quote_font = load_font(quote_font_size, bold=False)

    t_box = tmp_draw.textbbox((0, 0), "Good morning", font=title_font)
    t_w = t_box[2] - t_box[0]
    t_h = t_box[3] - t_box[1]

    max_quote_width = int(card_w * 0.88)
    quote_lines = wrap_text(quote, quote_font, max_quote_width, tmp_draw)
    line_height = quote_font_size + 6
    total_q_height = line_height * len(quote_lines)
    content_h = t_h + 30 + total_q_height
    card_h = content_h + padding_v * 2

    # clamp final card height
    if card_h > max_card_height:
        card_h = max_card_height

    # center card vertically
    card_x0 = (W - card_w) // 2
    card_y0 = (H - card_h) // 2
    card_x1 = card_x0 + card_w
    card_y1 = card_y0 + card_h

    # ----- draw translucent card -----
    overlay = Image.new("RGBA", bg_img.size, (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)

    draw_ov.rounded_rectangle(
        [card_x0, card_y0, card_x1, card_y1],
        radius=int(card_h * 0.2),
        fill=(255, 255, 255, 220),
    )

    bg_img = Image.alpha_composite(bg_img, overlay)
    draw = ImageDraw.Draw(bg_img)

    # ----- title -----
    title_text = "Good morning"

    title_x = card_x0 + (card_w - t_w) // 2
    title_y = card_y0 + padding_v

    draw.text(
        (title_x, title_y),
        title_text,
        font=title_font,
        fill=(65, 42, 94),        # soft purple
        stroke_width=2,
        stroke_fill="white",
    )

    # ----- quote -----
    quote_start_y = title_y + t_h + 30
    current_y = quote_start_y

    for line in quote_lines:
        q_box = draw.textbbox((0, 0), line, font=quote_font)
        q_w = q_box[2] - q_box[0]
        q_x = card_x0 + (card_w - q_w) // 2

        draw.text(
            (q_x, current_y),
            line,
            font=quote_font,
            fill=(60, 60, 80),
        )
        current_y += line_height

    return bg_img.convert("RGB")



# -------------------- CLOUDINARY UPLOAD --------------------

def upload_to_cloudinary(img: Image.Image) -> str:
    """
    Upload the composed PIL image to Cloudinary and return the URL.
    """
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=95)
    buffer.seek(0)

    result = cloudinary.uploader.upload(
        buffer,
        folder="whatsapp_agent_pillow",
        resource_type="image",
    )
    url = result["secure_url"]
    print(f"Image URL: {url}")
    return url


# -------------------- TWILIO SEND --------------------

def send_whatsapp(caption: str, media_url: str):
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    # Optional debug (doesn't print secrets)
    print(f"Sending WhatsApp from {WHATSAPP_FROM} to {WHATSAPP_TO} ...")

    msg = client.messages.create(
        from_=WHATSAPP_FROM,
        to=WHATSAPP_TO,
        body=caption,
        media_url=[media_url],
    )
    print(f"Twilio message SID: {msg.sid}")


# -------------------- MAIN --------------------

def main():
    quote = get_quote_via_api()
    bg = fetch_unsplash_image()
    final_img = compose_image_with_quote(bg, quote)
    url = upload_to_cloudinary(final_img)

    # Keep caption simple – no quote duplication
    caption = "🌞 Good morning!"
    send_whatsapp(caption, url)

