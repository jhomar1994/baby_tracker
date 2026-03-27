from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import timedelta, datetime
import sqlite3
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DB_PATH = os.path.join(os.path.dirname(__file__), "baby_tracker.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            baby_name TEXT DEFAULT 'Bebé',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS feedings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            breast_side TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            ounces REAL DEFAULT 0,
            notes TEXT,
            fed_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS telegram_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    conn.commit()
    conn.close()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        baby_name = request.form.get("baby_name", "Bebé").strip()

        if not username or not password:
            flash("Usuario y contraseña son obligatorios.", "error")
            return render_template("register.html")

        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users (username, password, baby_name) VALUES (?, ?, ?)",
                (username, generate_password_hash(password, method="pbkdf2:sha256"), baby_name),
            )
            conn.commit()
            flash("Registro exitoso. Inicia sesión.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Ese usuario ya existe.", "error")
        finally:
            conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        remember = request.form.get("remember")

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session.permanent = bool(remember)
            if remember:
                app.permanent_session_lifetime = timedelta(days=30)
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["baby_name"] = user["baby_name"]
            return redirect(url_for("dashboard"))

        flash("Usuario o contraseña incorrectos.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    summary = conn.execute(
        """SELECT COUNT(*) as total_feedings,
                  COALESCE(SUM(ounces), 0) as total_ounces,
                  COALESCE(SUM(duration_minutes), 0) as total_minutes
           FROM feedings WHERE user_id = ?""",
        (session["user_id"],),
    ).fetchone()
    today_summary = conn.execute(
        """SELECT COUNT(*) as total_feedings,
                  COALESCE(SUM(ounces), 0) as total_ounces,
                  COALESCE(SUM(duration_minutes), 0) as total_minutes
           FROM feedings WHERE user_id = ? AND date(fed_at) = date('now')""",
        (session["user_id"],),
    ).fetchone()
    conn.close()
    return render_template(
        "dashboard.html",
        baby_name=session.get("baby_name", "Bebé"),
        summary=summary,
        today=today_summary,
    )


@app.route("/record")
@login_required
def record():
    conn = get_db()
    feedings = conn.execute(
        "SELECT * FROM feedings WHERE user_id = ? ORDER BY fed_at DESC LIMIT 50",
        (session["user_id"],),
    ).fetchall()
    conn.close()
    return render_template("record.html", feedings=feedings, baby_name=session.get("baby_name", "Bebé"))


@app.route("/add_feeding", methods=["POST"])
@login_required
def add_feeding():
    breast_side = request.form["breast_side"]
    duration = int(request.form["duration_minutes"])
    ounces = float(request.form.get("ounces", 0) or 0)
    notes = request.form.get("notes", "").strip()
    fed_at = request.form["fed_at"]

    conn = get_db()
    conn.execute(
        "INSERT INTO feedings (user_id, breast_side, duration_minutes, ounces, notes, fed_at) VALUES (?, ?, ?, ?, ?, ?)",
        (session["user_id"], breast_side, duration, ounces, notes, fed_at),
    )
    conn.commit()
    conn.close()
    flash("Toma registrada correctamente.", "success")
    return redirect(url_for("record"))


@app.route("/delete_feeding/<int:feeding_id>", methods=["POST"])
@login_required
def delete_feeding(feeding_id):
    conn = get_db()
    conn.execute("DELETE FROM feedings WHERE id = ? AND user_id = ?", (feeding_id, session["user_id"]))
    conn.commit()
    conn.close()
    return redirect(url_for("record"))


@app.route("/api/chart_data")
@login_required
def chart_data():
    conn = get_db()
    rows = conn.execute(
        """SELECT date(fed_at) as day,
                  SUM(duration_minutes) as total_min,
                  COUNT(*) as count,
                  COALESCE(SUM(ounces), 0) as total_oz
           FROM feedings WHERE user_id = ?
           GROUP BY date(fed_at) ORDER BY day""",
        (session["user_id"],),
    ).fetchall()
    conn.close()

    data = {
        "labels": [r["day"] for r in rows],
        "durations": [r["total_min"] for r in rows],
        "counts": [r["count"] for r in rows],
        "ounces": [r["total_oz"] for r in rows],
    }
    return jsonify(data)


## --- Telegram Bot Webhook --- ##

import json
import urllib.request


def telegram_send(chat_id, text):
    """Send a message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req)
    except Exception:
        pass


def handle_telegram_message(chat_id, text):
    """Process incoming Telegram messages."""
    conn = get_db()
    parts = text.strip().split()
    command = parts[0].lower() if parts else ""

    # /start usuario contraseña
    if command == "/start":
        if len(parts) < 3:
            telegram_send(chat_id, (
                "Para vincular tu cuenta escribe:\n"
                "<code>/start usuario contraseña</code>\n\n"
                "Después podrás registrar tomas con:\n"
                "<code>/toma minutos onzas lado</code>\n\n"
                "Lados: izquierdo, derecho, ambos, biberon\n\n"
                "Ver resumen del día:\n"
                "<code>/resumen</code>"
            ))
            conn.close()
            return

        username = parts[1]
        password = parts[2]
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        if user and check_password_hash(user["password"], password):
            conn.execute(
                "INSERT OR REPLACE INTO telegram_links (telegram_id, user_id) VALUES (?, ?)",
                (chat_id, user["id"]),
            )
            conn.commit()
            telegram_send(chat_id, f"Vinculado a la cuenta de <b>{username}</b>. Ya puedes registrar tomas.")
        else:
            telegram_send(chat_id, "Usuario o contraseña incorrectos.")
        conn.close()
        return

    # Check if user is linked
    link = conn.execute("SELECT user_id FROM telegram_links WHERE telegram_id = ?", (chat_id,)).fetchone()
    if not link:
        telegram_send(chat_id, "Primero vincula tu cuenta con:\n<code>/start usuario contraseña</code>")
        conn.close()
        return

    user_id = link["user_id"]

    # /toma minutos onzas [lado] [nota...]
    if command == "/toma":
        if len(parts) < 3:
            telegram_send(chat_id, "Formato:\n<code>/toma minutos onzas [lado] [nota]</code>\n\nEjemplo:\n<code>/toma 15 2.5 derecho buena succión</code>")
            conn.close()
            return

        try:
            duration = int(parts[1])
            ounces = float(parts[2])
        except ValueError:
            telegram_send(chat_id, "Minutos debe ser un número entero y onzas un número.\n<code>/toma 15 2.5 derecho</code>")
            conn.close()
            return

        valid_sides = ["izquierdo", "derecho", "ambos", "biberon"]
        breast_side = parts[3].lower() if len(parts) > 3 and parts[3].lower() in valid_sides else "ambos"
        notes_start = 4 if len(parts) > 3 and parts[3].lower() in valid_sides else 3
        notes = " ".join(parts[notes_start:]) if len(parts) > notes_start else ""

        fed_at = datetime.now().strftime("%Y-%m-%dT%H:%M")

        conn.execute(
            "INSERT INTO feedings (user_id, breast_side, duration_minutes, ounces, notes, fed_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, breast_side, duration, ounces, notes, fed_at),
        )
        conn.commit()

        # Get today's summary
        today = conn.execute(
            """SELECT COUNT(*) as c, COALESCE(SUM(ounces),0) as oz, COALESCE(SUM(duration_minutes),0) as mins
               FROM feedings WHERE user_id = ? AND date(fed_at) = date('now')""",
            (user_id,),
        ).fetchone()

        telegram_send(chat_id, (
            f"Toma registrada:\n"
            f"  {duration} min | {ounces} oz | {breast_side}\n\n"
            f"Resumen de hoy:\n"
            f"  Tomas: {today['c']}\n"
            f"  Onzas: {today['oz']}\n"
            f"  Minutos: {today['mins']}"
        ))
        conn.close()
        return

    # /resumen
    if command == "/resumen":
        today = conn.execute(
            """SELECT COUNT(*) as c, COALESCE(SUM(ounces),0) as oz, COALESCE(SUM(duration_minutes),0) as mins
               FROM feedings WHERE user_id = ? AND date(fed_at) = date('now')""",
            (user_id,),
        ).fetchone()
        total = conn.execute(
            """SELECT COUNT(*) as c, COALESCE(SUM(ounces),0) as oz, COALESCE(SUM(duration_minutes),0) as mins
               FROM feedings WHERE user_id = ?""",
            (user_id,),
        ).fetchone()

        last = conn.execute(
            "SELECT * FROM feedings WHERE user_id = ? ORDER BY fed_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        last_text = f"\nÚltima toma: {last['fed_at'][:16].replace('T', ' ')} — {last['duration_minutes']} min, {last['ounces']} oz, {last['breast_side']}" if last else ""

        telegram_send(chat_id, (
            f"<b>Resumen de hoy:</b>\n"
            f"  Tomas: {today['c']}\n"
            f"  Onzas: {today['oz']}\n"
            f"  Minutos: {today['mins']}\n\n"
            f"<b>Total general:</b>\n"
            f"  Tomas: {total['c']}\n"
            f"  Onzas: {total['oz']}\n"
            f"  Minutos: {total['mins']}"
            f"{last_text}"
        ))
        conn.close()
        return

    telegram_send(chat_id, (
        "Comandos disponibles:\n"
        "<code>/toma minutos onzas [lado] [nota]</code>\n"
        "<code>/resumen</code>\n"
        "<code>/start usuario contraseña</code>"
    ))
    conn.close()


@app.route(f"/webhook/telegram", methods=["POST"])
def telegram_webhook():
    data = request.get_json(silent=True)
    if not data or "message" not in data:
        return jsonify({"ok": True})

    message = data["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    if text:
        handle_telegram_message(chat_id, text)

    return jsonify({"ok": True})


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5050)
