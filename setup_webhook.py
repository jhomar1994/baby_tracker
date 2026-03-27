"""
Run this script ONCE to register the Telegram webhook.

Usage:
    python setup_webhook.py <BOT_TOKEN> <YOUR_PYTHONANYWHERE_URL>

Example:
    python setup_webhook.py 123456:ABC-DEF https://tuusuario.pythonanywhere.com
"""
import sys
import urllib.request
import json

if len(sys.argv) < 3:
    print("Usage: python setup_webhook.py <BOT_TOKEN> <BASE_URL>")
    print("Example: python setup_webhook.py 123456:ABC-DEF https://tuusuario.pythonanywhere.com")
    sys.exit(1)

token = sys.argv[1]
base_url = sys.argv[2].rstrip("/")
webhook_url = f"{base_url}/webhook/telegram"

url = f"https://api.telegram.org/bot{token}/setWebhook?url={webhook_url}"
response = urllib.request.urlopen(url)
result = json.loads(response.read())

if result.get("ok"):
    print(f"Webhook configurado: {webhook_url}")
else:
    print(f"Error: {result}")
