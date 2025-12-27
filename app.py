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
UPLOAD_DIR.mkdir(exist_ok=True)
app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["UPLOAD_DIR"] = str(UPLOAD_DIR)
app.config["DB_PATH"] = str(DB_PATH)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  

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

def load_cache():
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def write_cache(obj):
    CACHE_PATH.write_text(json.dumps(obj, indent=2), encoding="utf-8")

PROFILE = {
    "name": "Dimla, Earl Jhon D.",
    "student_number": "2024-03779-MN-O",
    "profile_picture": "Profile.png",
    "subject": "Data Structure and Algorithms",
    "course": "BSCPE 2-3",
    "saying": "Cogito Ergo Sum"
}

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


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    path = UPLOAD_DIR / filename
    if path.exists():
        return send_from_directory(str(UPLOAD_DIR), filename)
    static_path = APP_ROOT / "static" / "images" / filename
    if static_path.exists():
        return send_from_directory(str(static_path.parent), filename)
    abort(404)

@app.route("/api/folders", methods=["GET", "POST"])
def api_folders():
    if request.method == "GET":
        rows = query_db("SELECT * FROM folders ORDER BY created_at DESC")
        folders = [dict(r) for r in rows]
        return jsonify(folders)
    else:  
        data = request.json or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Folder name required"}), 400
        now = int(time.time())
        folder_id = execute_db("INSERT INTO folders (name, created_at) VALUES (?, ?)", (name, now))
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
        if "file" not in request.files:
            return jsonify({"error": "No file part"}), 400
        file = request.files["file"]
        folder_id = request.form.get("folder_id")
        name_override = request.form.get("display_name", "").strip()
        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400
        filename = secure_unique_filename(file.filename)
        filepath = UPLOAD_DIR / filename
        file.save(str(filepath))
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

@app.route("/api/exec/<int:file_id>", methods=["POST"])
def api_exec_file(file_id):
    row = query_db("SELECT * FROM files WHERE id = ?", (file_id,), one=True)
    if not row:
        return jsonify({"error": "file not found"}), 404
    filename = row["filename"]
    if not filename.lower().endswith(".py"):
        return jsonify({"error": "only .py execution supported"}), 400
    filepath = UPLOAD_DIR / filename
    if not filepath.exists():
        return jsonify({"error": "file missing on disk"}), 404

    try:
        proc = subprocess.run(
            ["python3", str(filepath)],
            cwd=str(UPLOAD_DIR),
            capture_output=True,
            text=True,
            timeout=5 
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

@app.route("/api/download/<int:file_id>", methods=["GET"])
def api_download(file_id):
    row = query_db("SELECT * FROM files WHERE id = ?", (file_id,), one=True)
    if not row:
        return jsonify({"error": "not found"}), 404
    filename = row["filename"]
    return send_from_directory(str(UPLOAD_DIR), filename, as_attachment=True)

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

linked_list = []

def init_db():
    conn = sqlite3.connect("linkedlist.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS linkedlist_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT,
            value TEXT,
            position TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()


@app.route("/api/tool/linkedlist", methods=["GET"])
def api_linkedlist_get():
    """Return the current linked list and full history from DB"""
    conn = sqlite3.connect("linkedlist.db")
    c = conn.cursor()
    c.execute("SELECT action, value, position, timestamp FROM linkedlist_history ORDER BY id DESC")
    conn.close()
    return jsonify({"list": linked_list})


@app.route("/api/tool/linkedlist/add", methods=["POST"])
def api_linkedlist_add():
    """Add an element to the linked list (begin or end)"""
    data = request.json or {}
    value = data.get("value", "")
    position = data.get("position", "end")

    if not value:
        return jsonify({"error": "value is required"}), 400

    if position == "begin":
        linked_list.insert(0, value)
    else:
        linked_list.append(value)

    conn = sqlite3.connect("linkedlist.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO linkedlist_history (action, value, position) VALUES (?, ?, ?)",
        ("add", value, position)
    )
    conn.commit()
    conn.close()

    return jsonify({"message": f"Added {value} at {position}", "list": linked_list})


@app.route("/api/tool/linkedlist/remove", methods=["POST"])
def api_linkedlist_remove():
    """Remove an element from the linked list (begin or end)"""
    data = request.json or {}
    position = data.get("position", "end")

    if not linked_list:
        return jsonify({"error": "list is empty"}), 400

    value = linked_list.pop(0) if position == "begin" else linked_list.pop()

    conn = sqlite3.connect("linkedlist.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO linkedlist_history (action, value, position) VALUES (?, ?, ?)",
        ("remove", value, position)
    )
    conn.commit()
    conn.close()

    return jsonify({"message": f"Removed {value} from {position}", "list": linked_list})

def infix_to_postfix(expression):
    precedence = {'+':1, '-':1, '*':2, '/':2, '^':3}
    stack = []
    output = ""

    for char in expression:
        if char.isalnum():  
            output += char
        elif char == '(':
            stack.append(char)
        elif char == ')':
            while stack and stack[-1] != '(':
                output += stack.pop()
            stack.pop() 
        else: 
            while stack and stack[-1] != '(' and precedence[char] <= precedence.get(stack[-1], 0):
                output += stack.pop()
            stack.append(char)

    while stack:
        output += stack.pop()

    return output

@app.route("/api/tool/stack/infix_to_postfix", methods=["POST"])
def api_stack_infix_to_postfix():
    data = request.json or {}
    expression = data.get("expression", "")
    try:
        result = infix_to_postfix(expression)
        return jsonify({"postfix": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    if not Path(app.config["DB_PATH"]).exists():
        print("Database not found - run `python db_init.py` to create portfolio.db")
    app.run(debug=True, host="127.0.0.1", port=5000)
