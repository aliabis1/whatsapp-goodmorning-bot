# send_text_only.py
import os
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()
client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

msg = client.messages.create(
    from_=os.getenv("WHATSAPP_FROM"),
    to=os.getenv("WHATSAPP_TO"),
    body="🌞 Good morning! (text-only test)"
)
print("Sent SID:", msg.sid)
