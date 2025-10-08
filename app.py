# app.py
"""
DimlasDSAPortfolio Flask app (Flask 3.0.0)
- REST endpoints for folder/file management
- JSON cache (cache.json) for quick listing
- SQLite storage (portfolio.db)
"""

import sqlite3
import json
import time
import subprocess
from pathlib import Path
from flask import Flask, g, render_template, request, jsonify, send_from_directory, abort, url_for

APP_ROOT = Path(__file__).parent
UPLOAD_DIR = APP_ROOT / "uploads"
DB_PATH = APP_ROOT / "portfolio.db"
CACHE_PATH = APP_ROOT / "cache.json"

# Ensure upload dir exists
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["UPLOAD_DIR"] = str(UPLOAD_DIR)
app.config["DB_PATH"] = str(DB_PATH)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB upload limit

# -------------------------
# Database helpers
# -------------------------
def get_db():
    """Return sqlite3 connection (row access by name)."""
    db = getattr(g, "_database", None)
    if db is None:
        db = sqlite3.connect(app.config["DB_PATH"])
        db.row_factory = sqlite3.Row
        g._database = db
    return db

@app.teardown_appcontext
def close_connection(exc):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

def query_db(query, params=(), one=False):
    cur = get_db().execute(query, params)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows

def execute_db(query, params=()):
    conn = get_db()
    cur = conn.execute(query, params)
    conn.commit()
    lastrowid = cur.lastrowid
    cur.close()
    return lastrowid

# -------------------------
# JSON cache helper
# -------------------------
def load_cache():
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def write_cache(obj):
    CACHE_PATH.write_text(json.dumps(obj, indent=2), encoding="utf-8")

# -------------------------
# Profile data (static)
# -------------------------
PROFILE = {
    "name": "Dimla, Earl Jhon D.",
    "student_number": "2024-03779-MN-O",
    "profile_picture": "Profile.png",
    "subject": "Data Structure and Algorithms",
    "course": "BSCPE 2-3",
    "saying": "Cogito Ergo Sum"
}

# -------------------------
# Frontend pages
# -------------------------
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/profile")
def profile():
    # Get profile info
    profile = query_db("SELECT * FROM profile LIMIT 1", one=True)

    # Get all folders
    folders = query_db("SELECT * FROM folders ORDER BY name COLLATE NOCASE")

    # For each folder, load its files
    folder_files = {}
    for f in folders:
        files = query_db(
            "SELECT * FROM files WHERE folder_id = ? ORDER BY created_at DESC",
            (f["id"],)
        )
        folder_files[f["name"]] = files

    # Also load any files not in a folder
    uncategorized_files = query_db(
        "SELECT * FROM files WHERE folder_id IS NULL ORDER BY created_at DESC"
    )

    return render_template(
        "profile.html",
        profile=PROFILE,
        folder_files=folder_files,
        uncategorized_files=uncategorized_files
    )


@app.route("/works")
def works():
    # small helper to feed mini-nav items
    mini_nav = ["Uppercaser", "Area of Circle", "Area of Triangle"]
    return render_template("works.html", mini_nav=mini_nav)

@app.context_processor
def inject_contact():
    return dict(contact={
        "student_email": "earljhonddimla@iskolarngbayan.edu.ph",
        "contact_number": "09503910307",
        "work_email": "ddimlaearljhon@gmail.com",
        "github": "Earl-cmyk",
        "profile_picture": url_for('static', filename='image/Profile.png')
    })


# Serve profile picture if uploaded into uploads/ or static/images/
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    # first check uploads directory
    path = UPLOAD_DIR / filename
    if path.exists():
        return send_from_directory(str(UPLOAD_DIR), filename)
    # else static folder fallback
    static_path = APP_ROOT / "static" / "images" / filename
    if static_path.exists():
        return send_from_directory(str(static_path.parent), filename)
    abort(404)

# -------------------------
# REST API for folders & files
# -------------------------
@app.route("/api/folders", methods=["GET", "POST"])
def api_folders():
    if request.method == "GET":
        rows = query_db("SELECT * FROM folders ORDER BY created_at DESC")
        folders = [dict(r) for r in rows]
        return jsonify(folders)
    else:  # POST -> create folder
        data = request.json or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Folder name required"}), 400
        now = int(time.time())
        folder_id = execute_db("INSERT INTO folders (name, created_at) VALUES (?, ?)", (name, now))
        # update cache listing
        update_cache_listing()
        return jsonify({"id": folder_id, "name": name, "created_at": now}), 201

@app.route("/api/folders/<int:folder_id>", methods=["PUT", "DELETE"])
def api_folder_modify(folder_id):
    if request.method == "PUT":
        data = request.json or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Folder name required"}), 400
        execute_db("UPDATE folders SET name = ? WHERE id = ?", (name, folder_id))
        update_cache_listing()
        return jsonify({"id": folder_id, "name": name})
    else:
        # Delete folder and its files (DB has ON DELETE CASCADE)
        execute_db("DELETE FROM folders WHERE id = ?", (folder_id,))
        update_cache_listing()
        return jsonify({"deleted": True})

@app.route("/api/files", methods=["GET", "POST"])
def api_files():
    if request.method == "GET":
        folder_id = request.args.get("folder_id")
        if folder_id:
            rows = query_db("SELECT * FROM files WHERE folder_id = ? ORDER BY created_at DESC", (folder_id,))
        else:
            rows = query_db("SELECT * FROM files ORDER BY created_at DESC")
        files = [dict(r) for r in rows]
        return jsonify(files)
    else:
        # POST -> upload file
        if "file" not in request.files:
            return jsonify({"error": "No file part"}), 400
        file = request.files["file"]
        folder_id = request.form.get("folder_id")
        name_override = request.form.get("display_name", "").strip()
        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400
        # save file
        filename = secure_unique_filename(file.filename)
        filepath = UPLOAD_DIR / filename
        file.save(str(filepath))
        # record in DB
        display_name = name_override if name_override else file.filename
        file_ext = Path(filename).suffix.lower().lstrip(".")
        now = int(time.time())
        fid = execute_db(
            "INSERT INTO files (folder_id, name, filename, file_type, created_at) VALUES (?, ?, ?, ?, ?)",
            (folder_id, display_name, filename, file_ext, now)
        )
        update_cache_listing()
        return jsonify({"id": fid, "name": display_name, "filename": filename, "file_type": file_ext}), 201

@app.route("/api/files/<int:file_id>", methods=["GET", "PUT", "DELETE"])
def api_file_modify(file_id):
    if request.method == "GET":
        row = query_db("SELECT * FROM files WHERE id = ?", (file_id,), one=True)
        if not row:
            return jsonify({"error": "Not found"}), 404
        return jsonify(dict(row))
    elif request.method == "PUT":
        data = request.json or {}
        new_name = data.get("name", "").strip()
        new_folder = data.get("folder_id")
        if not new_name:
            return jsonify({"error": "name required"}), 400
        execute_db("UPDATE files SET name = ?, folder_id = ? WHERE id = ?", (new_name, new_folder, file_id))
        update_cache_listing()
        return jsonify({"id": file_id, "name": new_name, "folder_id": new_folder})
    else:
        # Delete file (remove disk file too)
        row = query_db("SELECT * FROM files WHERE id = ?", (file_id,), one=True)
        if not row:
            return jsonify({"error": "Not found"}), 404
        fname = row["filename"]
        filepath = UPLOAD_DIR / fname
        if filepath.exists():
            try:
                filepath.unlink()
            except Exception:
                pass
        execute_db("DELETE FROM files WHERE id = ?", (file_id,))
        update_cache_listing()
        return jsonify({"deleted": True})

@app.route("/api/file-content/<int:file_id>", methods=["GET", "PUT"])
def api_file_content(file_id):
    # allow reading/writing file content (for edit)
    row = query_db("SELECT * FROM files WHERE id = ?", (file_id,), one=True)
    if not row:
        return jsonify({"error": "Not found"}), 404
    filepath = UPLOAD_DIR / row["filename"]
    if request.method == "GET":
        if not filepath.exists():
            return jsonify({"error": "File missing"}), 404
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        return jsonify({"content": content})
    else:  # PUT update content
        data = request.json or {}
        content = data.get("content", "")
        filepath.write_text(content, encoding="utf-8")
        update_cache_listing()
        return jsonify({"saved": True})

# -------------------------
# Helper: unique filename
# -------------------------
from werkzeug.utils import secure_filename
from pathlib import Path

def secure_unique_filename(filename):
    filename = secure_filename(filename)
    base = Path(filename).stem
    ext = Path(filename).suffix
    dest = UPLOAD_DIR / filename
    counter = 1
    while dest.exists():
        filename = f"{base}_{counter}{ext}"
        dest = UPLOAD_DIR / filename
        counter += 1
    return filename

# -------------------------
# Execute a saved python file (simple "terminal")
# SECURITY: This runs code on the server. Use only locally and with trusted files.
# We'll impose a timeout and restrict execution directory to uploads/.
# -------------------------
@app.route("/api/exec/<int:file_id>", methods=["POST"])
def api_exec_file(file_id):
    """
    Executes a python file saved in uploads and returns output.
    WARNING: executing arbitrary code is dangerous. This endpoint includes:
     - timeout (5 seconds)
     - working dir locked to uploads/
     - only executes files with .py extension
    Use at your own risk and preferably run locally.
    """
    row = query_db("SELECT * FROM files WHERE id = ?", (file_id,), one=True)
    if not row:
        return jsonify({"error": "file not found"}), 404
    filename = row["filename"]
    if not filename.lower().endswith(".py"):
        return jsonify({"error": "only .py execution supported"}), 400
    filepath = UPLOAD_DIR / filename
    if not filepath.exists():
        return jsonify({"error": "file missing on disk"}), 404

    # Execute with subprocess.run, timeout
    try:
        # Use a safe python binary - assume system python3 available
        proc = subprocess.run(
            ["python3", str(filepath)],
            cwd=str(UPLOAD_DIR),
            capture_output=True,
            text=True,
            timeout=5  # seconds
        )
        return jsonify({
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr
        })
    except subprocess.TimeoutExpired:
        return jsonify({"error": "execution timed out"}), 504
    except Exception as e:
        return jsonify({"error": f"execution error: {str(e)}"}), 500

# -------------------------
# Utility: download a file by filename
# -------------------------
@app.route("/api/download/<int:file_id>", methods=["GET"])
def api_download(file_id):
    row = query_db("SELECT * FROM files WHERE id = ?", (file_id,), one=True)
    if not row:
        return jsonify({"error": "not found"}), 404
    filename = row["filename"]
    return send_from_directory(str(UPLOAD_DIR), filename, as_attachment=True)

# -------------------------
# Update cache listing helper
# -------------------------
def update_cache_listing():
    rows_f = query_db("SELECT * FROM folders ORDER BY created_at DESC")
    folders = []
    for f in rows_f:
        files = query_db("SELECT id, name, filename, file_type, created_at FROM files WHERE folder_id = ? ORDER BY created_at DESC", (f["id"],))
        folders.append({
            "id": f["id"],
            "name": f["name"],
            "created_at": f["created_at"],
            "files": [dict(x) for x in files]
        })
    # root files (no folder)
    root_files = query_db("SELECT id, name, filename, file_type, created_at FROM files WHERE folder_id IS NULL ORDER BY created_at DESC")
    cache_obj = {
        "folders": folders,
        "root_files": [dict(x) for x in root_files],
        "updated_at": int(time.time())
    }
    write_cache(cache_obj)
    return cache_obj

@app.route("/api/cache", methods=["GET"])
def api_cache():
    return jsonify(load_cache())

# -------------------------
# Small utilities (mini tools requested)
# These are accessible via /api/tool/...
# -------------------------
@app.route("/api/tool/uppercaser", methods=["POST"])
def api_uppercaser():
    data = request.json or {}
    text = data.get("text", "")
    return jsonify({"result": text.upper()})

@app.route("/api/tool/area/circle", methods=["POST"])
def api_area_circle():
    data = request.json or {}
    try:
        r = float(data.get("radius", 0))
        area = 3.141592653589793 * r * r
        return jsonify({"area": area})
    except Exception:
        return jsonify({"error": "invalid radius"}), 400

@app.route("/api/tool/area/triangle", methods=["POST"])
def api_area_triangle():
    data = request.json or {}
    try:
        base = float(data.get("base", 0))
        height = float(data.get("height", 0))
        area = 0.5 * base * height
        return jsonify({"area": area})
    except Exception:
        return jsonify({"error": "invalid base/height"}), 400

# -------------------------
# Run app
# -------------------------
if __name__ == "__main__":
    # Helpful message if DB missing
    if not Path(app.config["DB_PATH"]).exists():
        print("Database not found - run `python db_init.py` to create portfolio.db")
    app.run(debug=True, host="127.0.0.1", port=5000)
