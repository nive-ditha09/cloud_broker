# cloud_broker.py
from flask import Flask, request, jsonify
from uuid import uuid4
import time
import os

app = Flask(__name__)

# In-memory store: for demo only
COMMANDS = {}  # device_id -> [cmd,...]

API_KEY = os.environ.get("CLOUD_API_KEY", "change_me_demo_secret")

def auth(req):
    key = req.headers.get("X-API-KEY") or req.args.get("api_key")
    return key == API_KEY

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "time": time.time()})

@app.route("/commands", methods=["POST"])
def post_command():
    if not auth(request):
        return ("unauthorized", 401)
    payload = request.get_json() or {}
    device = payload.get("device")
    if not device:
        return ("device required", 400)
    cmd = {
        "id": str(uuid4()),
        "intent": payload.get("intent"),
        "params": payload.get("params", {}),
        "created_at": time.time(),
        "ttl": payload.get("ttl", 300)
    }
    COMMANDS.setdefault(device, []).append(cmd)
    return jsonify({"ok": True, "id": cmd["id"], "queued_for": device})

@app.route("/commands/next", methods=["GET"])
def get_next():
    if not auth(request):
        return ("unauthorized", 401)
    device = request.args.get("device")
    if not device:
        return ("device required", 400)
    now = time.time()
    q = COMMANDS.get(device, [])
    # remove expired
    q = [c for c in q if c.get("ttl", 0) <= 0 or (now - c["created_at"] <= c.get("ttl", 300))]
    if not q:
        COMMANDS[device] = q
        return jsonify({"ok": True, "command": None})
    cmd = q.pop(0)
    COMMANDS[device] = q
    return jsonify({"ok": True, "command": cmd})

@app.route("/commands/list", methods=["GET"])
def list_commands():
    if not auth(request):
        return ("unauthorized", 401)
    device = request.args.get("device")
    if device:
        return jsonify({"ok": True, "commands": COMMANDS.get(device, [])})
    return jsonify({"ok": True, "commands": COMMANDS})

@app.route("/commands/clear", methods=["POST"])
def clear_cmds():
    if not auth(request):
        return ("unauthorized", 401)
    data = request.get_json() or {}
    device = data.get("device")
    if device:
        COMMANDS[device] = []
    else:
        COMMANDS.clear()
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
