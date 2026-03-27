"""
Scheduled task for PythonAnywhere.
Checks if any user hasn't fed in 3+ hours and sends Telegram alert.

Setup in PythonAnywhere:
1. Go to Tasks tab
2. Add a scheduled task that runs every hour:
   python3 /home/tuusuario/baby_tracker/check_alerts.py
"""
import urllib.request
import os

BASE_URL = os.environ.get("BASE_URL", "https://tuusuario.pythonanywhere.com")

try:
    response = urllib.request.urlopen(f"{BASE_URL}/api/check_alerts")
    print(response.read().decode())
except Exception as e:
    print(f"Error: {e}")
