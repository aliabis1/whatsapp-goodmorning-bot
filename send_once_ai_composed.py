# send_once_ai_composed.py
import os, io, base64, datetime, re, random
from dotenv import load_dotenv
from twilio.rest import Client
from openai import OpenAI
import cloudinary
import cloudinary.uploader

load_dotenv()

# --- SETTINGS ---
CAPTION_MODE = "short"        # "none" | "short" | "full"
SCENE_MODE   = "random"       # "random" | "force"
SCENE_FORCED = "golden-hour forest with light rays"  # used only if SCENE_MODE="force"

# Optional: deterministic variety per day (same scene for the same weekday)
USE_DAY_SEED = True

# --- Clients ---
twilio = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
oai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

# --- Scene catalog (feel free to add/remove) ---
SCENES = [
    "ocean dawn with soft pastel sky, gentle waves, distant sun",
    "golden-hour forest with light rays through tall pines",
    "misty valley at sunrise with layered mountains",
    "blooming meadow with morning dew and warm sunlight",
    "desert dunes at dawn with long shadows and clear sky",
    "lakeside sunrise with faint fog and reflections",
    "cliffside coast at early morning with warm horizon glow",
    "rice terraces at sunrise with low mist and sunbeams",
    "rolling hills with morning haze and golden grass",
    "cherry blossoms at morning by a calm river",
]

def muscat_now():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=4)

def get_quote_via_api() -> str:
    """
    Generate a short morning quote (1–2 sentences), with NO emojis,
    so the image text stays clean.
    """
    SYS = (
        "Write one original morning quote. Randomly choose motivation, life lesson, or kindness. "
        "Constraints: 1–2 sentences, warm tone, NO emojis, no hashtags/links, avoid clichés."
    )
    weekday = muscat_now().strftime("%A")
    prompt = (
        f"Write a fresh good-morning quote for {weekday} (Muscat time). "
        f"Keep it inspiring, short, and elegant. Do not include the words 'Good morning'."
    )
    resp = oai.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.7,
        messages=[{"role":"system","content":SYS},{"role":"user","content":prompt}],
    )
    return resp.choices[0].message.content.strip()

def _strip_greeting(text: str) -> str:
    t = text.strip()
    t = re.sub(r'^\s*(good\s*morning[!.,\s]*)', '', t, flags=re.IGNORECASE).strip()
    t = re.sub(r'[🌞🌅🌄☀️✨⭐️🌟]+', '', t).strip()
    return t

def _pick_scene() -> str:
    if SCENE_MODE == "force":
        return SCENE_FORCED
    # random (optionally seeded by weekday so it feels curated)
    if USE_DAY_SEED:
        seed = int(muscat_now().strftime("%w"))  # 0..6
        rng = random.Random(seed)
        return rng.choice(SCENES)
    return random.choice(SCENES)

def compose_image_with_quote(quote_text: str) -> str:
    clean_quote = _strip_greeting(quote_text)
    scene = _pick_scene()

    img_prompt = (
        f"Realistic nature morning landscape photo: {scene}. "
        "Warm golden-hour tones, soft light, high dynamic range, crisp detail. "
        "Overlay the following quote with clear, correctly spelled typography; center-aligned, "
        "high contrast against the background, generous padding, balanced composition. "
        "Do NOT add emojis in the text.\n\n"
        f"Quote:\n\"{clean_quote}\""
    )

    img = oai.images.generate(model="gpt-image-1", prompt=img_prompt, size="1024x1024")
    b64 = img.data[0].b64_json
    img_bytes = base64.b64decode(b64)

    res = cloudinary.uploader.upload(
        io.BytesIO(img_bytes),
        folder="whatsapp_agent",
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
        "to": os.getenv("WHATSAPP_TO"),
        "media_url": [media_url],
    }
    if caption.strip():
        kwargs["body"] = caption
    msg = twilio.messages.create(**kwargs)
    print("Sent WhatsApp SID:", msg.sid)

if __name__ == "__main__":
    quote = get_quote_via_api()
    image_url = compose_image_with_quote(quote)
    caption = make_caption(quote)
    send_whatsapp(caption, image_url)
    print("✅ Sent image with randomized nature scene and non-duplicated caption.")
