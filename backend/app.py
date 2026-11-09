import os
import uuid
import sqlite3
import logging
import json
import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

from defect_detection import detect_defects
from rag_retrieval import retrieve_procedure
from report_generator import generate_nrf_report
from amm_data import AMM_DATABASE

# ── Structured Logging ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger("AeroScribe-Backend")

# ── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

DB_PATH = os.path.join(os.path.dirname(__file__), "aeroscribe.db")
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


# ── Database ──────────────────────────────────────────────────────────────────

def init_db():
    """Initialize SQLite database; create tables if they don't exist."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inspections (
                id TEXT PRIMARY KEY,
                timestamp TEXT,
                aircraft_id TEXT,
                defect_type TEXT,
                confidence REAL,
                bbox TEXT,
                amm_id TEXT,
                inspector_notes TEXT,
                inspector_name TEXT,
                report_id TEXT,
                image_path TEXT
            )
        """)
        # Migrate: add inspector_name column if it doesn't exist (safe for existing DBs)
        try:
            cursor.execute("ALTER TABLE inspections ADD COLUMN inspector_name TEXT")
            logger.info("DB migration: added inspector_name column.")
        except Exception:
            pass  # Column already exists
        conn.commit()
        conn.close()
        logger.info(f"SQLite audit database initialized: {DB_PATH}")
    except Exception as e:
        logger.error(f"Failed to initialize SQLite database: {e}")


init_db()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ok(data: dict, status: int = 200):
    """Return a standardized success JSON response."""
    return jsonify({"status": "success", **data}), status


def _err(message: str, code: str = "ERR_GENERIC", status: int = 400):
    """Return a standardized error JSON response."""
    return jsonify({"status": "error", "error": message, "code": code}), status


def validate_image_file(file):
    """Validate uploaded inspection image for format and size."""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Unsupported extension '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > 10 * 1024 * 1024:
        return False, f"File exceeds 10 MB limit ({size / (1024*1024):.2f} MB uploaded)"
    return True, ""


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(r):
    return {
        "id": r["id"],
        "timestamp": r["timestamp"],
        "aircraft_id": r["aircraft_id"],
        "defect_type": r["defect_type"],
        "confidence": r["confidence"],
        "bbox": json.loads(r["bbox"]),
        "amm_id": r["amm_id"],
        "inspector_notes": r["inspector_notes"],
        "inspector_name": r["inspector_name"] or "",
        "report_id": r["report_id"],
        "image_path": r["image_path"],
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.after_request
def add_request_id(response):
    """Attach a unique X-Request-ID header to every response for audit tracing."""
    response.headers["X-Request-ID"] = str(uuid.uuid4())
    response.headers["X-Service"] = "AeroScribe/1.0"
    return response


@app.route("/api/health", methods=["GET"])
def health():
    """System health check: confirms Flask and DB availability."""
    db_ok = os.path.exists(DB_PATH)
    return _ok({
        "service": "AeroScribe Backend",
        "version": "1.0.0",
        "database": "connected" if db_ok else "unavailable",
        "timestamp": datetime.datetime.now().isoformat(),
    })


@app.route("/api/scan", methods=["POST"])
def scan():
    """
    Step 1–2: Camera Capture → AI Defect Detection.
    Validates the uploaded image, runs YOLOv8 inference, and returns
    annotated detections enriched with AMM severity data.
    """
    if "image" not in request.files:
        logger.warning("Scan: no 'image' field in request.")
        return _err("No image file uploaded. Include an 'image' field in multipart form.", "ERR_NO_IMAGE")

    image = request.files["image"]
    if not image.filename:
        return _err("Empty filename received.", "ERR_EMPTY_FILENAME")

    is_valid, err_msg = validate_image_file(image)
    if not is_valid:
        logger.warning(f"Scan validation failed for '{image.filename}': {err_msg}")
        return _err(err_msg, "ERR_INVALID_FILE")

    ext = os.path.splitext(image.filename)[1] or ".jpg"
    image_id = str(uuid.uuid4())
    image_path = os.path.join(UPLOAD_DIR, f"{image_id}{ext}")
    image.save(image_path)
    logger.info(f"Saved inspection image: {image_path}")

    try:
        detections, using_custom_weights = detect_defects(image_path)
        logger.info(
            f"Inference complete. Mode: {'custom' if using_custom_weights else 'fallback'}. "
            f"Detections: {len(detections)}"
        )
    except Exception as e:
        logger.error(f"Inference error: {e}")
        return _err("AI detection pipeline encountered an error.", "ERR_INFERENCE", 500)

    # Enrich detections with severity info from AMM database
    for d in detections:
        amm_match = next((e for e in AMM_DATABASE if e["defect_type"] == d["label"]), None)
        if amm_match:
            d["severity_class"] = amm_match["severity_class"]
            d["risk_level"] = amm_match["risk_level"]
        else:
            d["severity_class"] = "Category 3 — Monitor"
            d["risk_level"] = 3

    return _ok({
        "image_id": image_id,
        "detections": detections,
        "model_mode": "custom_trained" if using_custom_weights else "demo_fallback",
    })


@app.route("/api/retrieve", methods=["POST"])
def retrieve():
    """
    Step 3: AMM Retrieval via offline RAG.
    Accepts a defect_type string and returns the best-matching AMM directive.
    """
    data = request.get_json(silent=True) or {}
    defect_type = data.get("defect_type", "").strip()
    if not defect_type:
        return _err("'defect_type' field is required.", "ERR_MISSING_FIELD")

    logger.info(f"AMM RAG query: '{defect_type}'")
    try:
        results = retrieve_procedure(defect_type, top_k=1)
        procedure = results[0] if results else None
        if procedure:
            logger.info(f"Retrieved: {procedure['id']} (score: {procedure.get('retrieval_score', 1.0):.3f})")
        else:
            logger.warning(f"No AMM match for: '{defect_type}'")
        return _ok({"procedure": procedure})
    except Exception as e:
        logger.error(f"RAG retrieval failure: {e}")
        return _err("Retrieval pipeline failed.", "ERR_RAG", 500)


@app.route("/api/generate-report", methods=["POST"])
def generate_report():
    """
    Step 5: NRF Report Generation after inspector verification.
    Logs signoff to SQLite audit database and generates a compliance PDF.
    """
    data = request.get_json(silent=True) or {}
    defect = data.get("defect")
    amm_id = data.get("amm_id")
    inspector_notes = data.get("inspector_notes", "")
    inspector_name = data.get("inspector_name", "")
    aircraft_id = data.get("aircraft_id", "N/A")

    amm_entry = next((e for e in AMM_DATABASE if e["id"] == amm_id), None)
    if not amm_entry or defect is None:
        logger.warning(f"Invalid report inputs — AMM ref: {amm_id}, defect: {defect}")
        return _err("Invalid defect or AMM reference provided.", "ERR_INVALID_INPUT")

    try:
        filepath, report_id = generate_nrf_report(
            defect, amm_entry, inspector_notes, aircraft_id, inspector_name=inspector_name
        )
        logger.info(f"PDF compiled: {filepath}")
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        return _err("PDF compilation engine failed.", "ERR_PDF", 500)

    # Persist audit record to SQLite
    try:
        conn = _get_db()
        conn.execute(
            """
            INSERT INTO inspections (
                id, timestamp, aircraft_id, defect_type, confidence, bbox,
                amm_id, inspector_notes, inspector_name, report_id, image_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                aircraft_id,
                defect.get("label", "N/A"),
                float(defect.get("confidence", 0.0)),
                json.dumps(defect.get("bbox", [])),
                amm_id,
                inspector_notes,
                inspector_name,
                report_id,
                filepath,
            ),
        )
        conn.commit()
        conn.close()
        logger.info(f"Audit logged — Report ID: {report_id}, Aircraft: {aircraft_id}")
    except Exception as e:
        logger.error(f"Audit DB write failed: {e}")

    return _ok({
        "report_id": report_id,
        "download_url": f"/api/report/{report_id}",
    }, 201)


@app.route("/api/report/<report_id>", methods=["GET"])
def download_report(report_id):
    """Download a generated NRF compliance PDF by its report ID."""
    filepath = os.path.join(os.path.dirname(__file__), "reports", f"{report_id}.pdf")
    if not os.path.exists(filepath):
        logger.warning(f"Report not found: {report_id}")
        return _err(f"Report '{report_id}' not found.", "ERR_NOT_FOUND", 404)
    return send_file(filepath, as_attachment=True, download_name=f"{report_id}.pdf")


@app.route("/api/history", methods=["GET"])
def get_history():
    """
    Returns paginated inspection audit logs from the SQLite database.
    Query params: ?page=1&per_page=20&defect_type=crack
    """
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
        defect_filter = request.args.get("defect_type", "").strip()
    except ValueError:
        return _err("Invalid pagination parameters.", "ERR_INVALID_PARAMS")

    try:
        conn = _get_db()
        offset = (page - 1) * per_page

        if defect_filter:
            total = conn.execute(
                "SELECT COUNT(*) FROM inspections WHERE defect_type = ?", (defect_filter,)
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM inspections WHERE defect_type = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (defect_filter, per_page, offset),
            ).fetchall()
        else:
            total = conn.execute("SELECT COUNT(*) FROM inspections").fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM inspections ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (per_page, offset),
            ).fetchall()

        conn.close()
        return _ok({
            "history": [_row_to_dict(r) for r in rows],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page,
            },
        })
    except Exception as e:
        logger.error(f"History fetch failed: {e}")
        return _err("Failed to fetch inspection history.", "ERR_DB", 500)


@app.route("/api/history/<record_id>", methods=["DELETE"])
def delete_history(record_id):
    """Delete a single inspection audit record by ID."""
    try:
        conn = _get_db()
        result = conn.execute("DELETE FROM inspections WHERE id = ?", (record_id,))
        conn.commit()
        conn.close()
        if result.rowcount == 0:
            return _err(f"Record '{record_id}' not found.", "ERR_NOT_FOUND", 404)
        logger.info(f"Audit record deleted: {record_id}")
        return _ok({"deleted_id": record_id})
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        return _err("Failed to delete record.", "ERR_DB", 500)


@app.route("/api/stats", methods=["GET"])
def get_stats():
    """
    Returns fleet-wide defect frequency statistics from the audit database.
    Used to populate the dashboard summary panel.
    """
    try:
        conn = _get_db()
        total = conn.execute("SELECT COUNT(*) FROM inspections").fetchone()[0]
        by_defect = conn.execute(
            "SELECT defect_type, COUNT(*) as cnt FROM inspections GROUP BY defect_type ORDER BY cnt DESC"
        ).fetchall()
        avg_conf = conn.execute("SELECT AVG(confidence) FROM inspections").fetchone()[0]
        recent = conn.execute(
            "SELECT timestamp FROM inspections ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        conn.close()

        return _ok({
            "total_inspections": total,
            "avg_confidence": round(float(avg_conf or 0), 3),
            "most_recent": recent[0] if recent else None,
            "by_defect_type": [
                {"defect_type": r["defect_type"], "count": r["cnt"]} for r in by_defect
            ],
        })
    except Exception as e:
        logger.error(f"Stats fetch failed: {e}")
        return _err("Failed to compute statistics.", "ERR_DB", 500)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
