# send_once_ai_composed.py
import os, io, base64, datetime, random
from dotenv import load_dotenv
from twilio.rest import Client
from openai import OpenAI
import cloudinary
import cloudinary.uploader

load_dotenv()

# --- Clients ---
twilio = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
oai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

def muscat_now():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=4)

def get_quote_via_api() -> str:
    """Generate a short motivational/kindness/life-lesson quote."""
    SYS = (
        "Write one original morning quote. Theme randomly: motivation, life lesson, or kindness. "
        "Constraints: 1–2 sentences, warm tone, no hashtags or links, avoid clichés, one emoji max."
    )
    weekday = muscat_now().strftime("%A")
    prompt = (
        f"Write a fresh good-morning quote for {weekday} (Muscat time). "
        f"Keep it inspiring, short, and elegant."
    )
    resp = oai.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.7,
        messages=[
            {"role": "system", "content": SYS},
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content.strip()

def compose_image_with_quote(quote_text: str) -> str:
    """
    Generate a nature-themed realistic image (sunrise, mountains, forest, beach, etc.)
    with the quote overlaid in clean typography.
    """
    img_prompt = (
        "Create a **realistic nature landscape photograph** that feels peaceful and inspiring — "
        "for example sunrise over mountains, forest light rays, beach morning sky, blooming tree, or open fields. "
        "Blend the following quote elegantly into the scene with clear, legible white or dark text centered, "
        "balanced composition, soft light, high resolution, and phone-wallpaper aspect ratio.\n\n"
        f"Quote:\n\"{quote_text}\""
    )

    img = oai.images.generate(
        model="gpt-image-1",
        prompt=img_prompt,
        size="1024x1024"
    )

    b64 = img.data[0].b64_json
    img_bytes = base64.b64decode(b64)

    upload_result = cloudinary.uploader.upload(
        io.BytesIO(img_bytes),
        folder="whatsapp_agent",
        resource_type="image",
        overwrite=True
    )
    return upload_result["secure_url"]

def send_whatsapp(quote: str, media_url: str):
    """Send WhatsApp message with the image and single-line caption."""
    msg = twilio.messages.create(
        from_=os.getenv("WHATSAPP_FROM"),
        to=os.getenv("WHATSAPP_TO"),
        body=f"🌞 {quote}",  # only once, no duplication
        media_url=[media_url],
    )
    print("Sent WhatsApp SID:", msg.sid)

if __name__ == "__main__":
    quote = get_quote_via_api()
    image_url = compose_image_with_quote(quote)
    send_whatsapp(quote, image_url)
    print("✅ Sent realistic nature quote image + single caption.")
