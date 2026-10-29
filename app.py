import os, sqlite3
from datetime import datetime
from functools import wraps
from flask import Flask, jsonify, render_template, request, session, redirect, url_for, flash

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "parcelgo.db")
app = Flask(__name__)
app.secret_key = os.environ.get("PARCELGO_SECRET_KEY", "replace-this-secret-before-publishing")
ADMIN_USER = os.environ.get("PARCELGO_ADMIN_USERNAME", "Govardhan")
ADMIN_PASS = os.environ.get("PARCELGO_ADMIN_PASSWORD", "7396")
STATUSES = {"In Transit", "Picked Up", "Out for Delivery", "Delivered", "Cancelled"}

def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c

def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS orders(
          id TEXT PRIMARY KEY, sender TEXT NOT NULL, pickup TEXT NOT NULL,
          senderPhone TEXT NOT NULL, receiver TEXT NOT NULL, delivery TEXT NOT NULL,
          receiverPhone TEXT NOT NULL, description TEXT NOT NULL, weight TEXT NOT NULL,
          type TEXT NOT NULL, deliveryFee INTEGER NOT NULL, total INTEGER NOT NULL,
          status TEXT NOT NULL, date TEXT NOT NULL, created_at TEXT NOT NULL)""")
        c.commit()

def as_dict(row): return {k: row[k] for k in row.keys()}

def admin_only(fn):
    @wraps(fn)
    def wrapped(*a, **kw):
        if not session.get("admin"): return redirect(url_for("admin_login"))
        return fn(*a, **kw)
    return wrapped

@app.get("/")
def index(): return render_template("index.html")

@app.get("/api/orders")
def orders_list():
    with db() as c: rows = c.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    return jsonify([as_dict(r) for r in rows])

@app.get("/api/orders/<oid>")
def order_detail(oid):
    with db() as c: row = c.execute("SELECT * FROM orders WHERE id=?", (oid.upper(),)).fetchone()
    if not row: return jsonify(error="Parcel ID not found."), 404
    return jsonify(as_dict(row))

@app.post("/api/orders")
def create_order():
    d = request.get_json(silent=True) or {}
    required = ["sender","pickup","senderPhone","receiver","delivery","receiverPhone","description","weight","type"]
    if any(not str(d.get(k,"")).strip() for k in required):
        return jsonify(error="Please complete all parcel details."), 400
    for k in ("senderPhone","receiverPhone"):
        if not str(d[k]).isdigit() or len(str(d[k])) != 10:
            return jsonify(error="Enter valid 10-digit phone numbers."), 400
    if d["pickup"].strip().casefold() == d["delivery"].strip().casefold():
        return jsonify(error="Pickup and delivery addresses must be different."), 400
    if d["weight"] not in {"Up to 1 kg","1–5 kg","5–10 kg"} or d["type"] not in {"Standard","Express","Same Day"}:
        return jsonify(error="Invalid weight or delivery type."), 400
    fee = {"Up to 1 kg":0,"1–5 kg":30,"5–10 kg":60}[d["weight"]] + {"Standard":0,"Express":30,"Same Day":60}[d["type"]]
    with db() as c:
        row = c.execute("SELECT id FROM orders ORDER BY created_at DESC LIMIT 1").fetchone()
        try: n = int(row["id"][2:])+1 if row else 1001
        except Exception: n = 1001
        oid = f"PG{n}"
        while c.execute("SELECT 1 FROM orders WHERE id=?", (oid,)).fetchone():
            n += 1; oid = f"PG{n}"
        now = datetime.now()
        c.execute("""INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (oid,d["sender"].strip(),d["pickup"].strip(),d["senderPhone"],d["receiver"].strip(),
           d["delivery"].strip(),d["receiverPhone"],d["description"].strip(),d["weight"],d["type"],
           fee,70+fee,"In Transit",now.strftime("%d/%m/%Y"),now.isoformat(timespec="seconds")))
        c.commit()
        saved = c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    return jsonify(as_dict(saved)), 201

@app.get("/admin/login")
@app.route("/admin/login", methods=["POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("username") == ADMIN_USER and request.form.get("password") == ADMIN_PASS:
            session["admin"] = True; return redirect(url_for("dashboard"))
        flash("Incorrect username or password.")
    return render_template("admin_login.html")

@app.get("/admin")
@admin_only
def dashboard():
    with db() as c: rows = c.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    items = [as_dict(r) for r in rows]
    revenue = sum(o["total"] for o in items if o["status"] != "Cancelled")
    return render_template("admin.html", orders=items, revenue=revenue, statuses=sorted(STATUSES))

@app.post("/admin/logout")
def logout():
    session.clear(); return redirect(url_for("admin_login"))

@app.post("/admin/orders/<oid>/status")
@admin_only
def change_status(oid):
    status = request.form.get("status")
    if status not in STATUSES: flash("Invalid status.")
    else:
        with db() as c:
            cur = c.execute("UPDATE orders SET status=? WHERE id=?", (status,oid.upper())); c.commit()
        flash("Order status updated." if cur.rowcount else "Order not found.")
    return redirect(url_for("dashboard"))

@app.get("/health")
def health(): return jsonify(status="ok")

init_db()
if __name__ == "__main__":
    # 0.0.0.0 allows other devices on the same trusted Wi-Fi/LAN to connect.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT","5000")), debug=False)
