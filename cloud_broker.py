from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
import requests
import psycopg2
from datetime import datetime
from dotenv import load_dotenv
from google import genai

# -------------------------------------------------
# ENV
# -------------------------------------------------
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

PI_BASE = os.getenv("PI_BASE")  # example: http://192.168.1.50
PI_AUTOMATION = f"{PI_BASE}:5001"
PI_CAMERA = f"{PI_BASE}:5002"

# -------------------------------------------------
# APP
# -------------------------------------------------
app = Flask(__name__)
CORS(app)

# -------------------------------------------------
# DB
# -------------------------------------------------
db = psycopg2.connect(DATABASE_URL)
cur = db.cursor()

# -------------------------------------------------
# GEMINI
# -------------------------------------------------
gemini = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """
You are a HOME AUTOMATION AI.

You control:
- Bedroom light (led_id=1)
- Living room light (led_id=2)
- Temperature sensor
- Security camera

Rules:
- Do not use personal language
- Do not invent devices or times
- Respond in system-style language only

Return STRICT JSON only.

FORMAT:
{
  "commands": [
    {"type":"led","led_id":1,"action":"on"},
    {"type":"temperature"},
    {"type":"camera"}
  ],
  "spoken_response": "System status message"
}
"""

# -------------------------------------------------
# HELPERS
# -------------------------------------------------
def ask_gemini(user_text, system_state):
    prompt = SYSTEM_PROMPT + f"""
SYSTEM STATE:
{json.dumps(system_state)}

USER INPUT:
{user_text}
"""
    r = gemini.models.generate_content(
        model="gemini-flash-lite-latest",
        contents=[prompt]
    )
    return json.loads(r.text)


def dispatch_led(cmd):
    requests.post(
        f"{PI_AUTOMATION}/execute",
        json=cmd,
        timeout=3
    )


def dispatch_temperature():
    r = requests.get(f"{PI_AUTOMATION}/temperature", timeout=3)
    return r.json().get("temperature")


def dispatch_camera():
    r = requests.post(f"{PI_CAMERA}/capture", timeout=10)
    return r.json().get("image_url")


def log_command(cmd):
    cur.execute(
        "INSERT INTO command_log(type, payload, executed_at) VALUES (%s,%s,%s)",
        (cmd["type"], json.dumps(cmd), datetime.now())
    )
    db.commit()

# -------------------------------------------------
# MAIN AI ENDPOINT
# -------------------------------------------------
@app.route("/ai", methods=["POST"])
def ai():
    user_text = request.json["text"]

    # --- system state for Gemini ---
    cur.execute("SELECT name, scheduled_time FROM routines WHERE enabled=true")
    routines = cur.fetchall()

    cur.execute("""
        SELECT r.name, e.executed_at, e.status
        FROM routine_executions e
        JOIN routines r ON r.id=e.routine_id
        ORDER BY executed_at DESC
        LIMIT 5
    """)
    history = cur.fetchall()

    system_state = {
        "routines": routines,
        "recent_executions": history,
        "time": str(datetime.now())
    }

    # --- Gemini decides ---
    result = ask_gemini(user_text, system_state)

    temperature_value = None
    camera_image = None

    # --- Execute commands ---
    for cmd in result.get("commands", []):

        if cmd["type"] == "led":
            dispatch_led(cmd)

        elif cmd["type"] == "temperature":
            temperature_value = dispatch_temperature()

        elif cmd["type"] == "camera":
            camera_image = dispatch_camera()

        log_command(cmd)

    # --- Enhance spoken response with facts ---
    response_text = result.get("spoken_response", "Command executed.")

    if temperature_value:
        response_text += f" Temperature is {temperature_value} degrees."

    if camera_image:
        response_text += " Camera image captured."

    return jsonify({
        "spoken_response": response_text,
        "temperature": temperature_value,
        "image_url": camera_image
    })

# -------------------------------------------------
# HEALTH CHECK
# -------------------------------------------------
@app.route("/")
def health():
    return "Cloud broker running"

# -------------------------------------------------
# START
# -------------------------------------------------
if __name__ == "__main__":
    print("☁️ Cloud broker running on port 5000")
    app.run(host="0.0.0.0", port=5000)
