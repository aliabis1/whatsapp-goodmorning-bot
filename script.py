# script.py
import os
from dotenv import load_dotenv
from twilio.rest import Client

# Load credentials from .env file
load_dotenv()

# Read environment variables
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
from_whatsapp = os.getenv("WHATSAPP_FROM")
to_whatsapp = os.getenv("WHATSAPP_TO")

# Initialize Twilio client
client = Client(account_sid, auth_token)

# Send a simple WhatsApp message
message = client.messages.create(
    body="👋 Hello from your WhatsApp agent setup test!",
    from_=from_whatsapp,
    to=to_whatsapp
)

print("✅ Message sent! SID:", message.sid)
