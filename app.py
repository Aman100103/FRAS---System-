import threading
import webbrowser
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, url_for

from utils.attendance_utils import (
    ensure_student_record,
    get_attendance_percentage_per_student,
    get_daily_trend,
    get_defaulters,
    get_overall_percentage,
    get_summary_counts,
    get_summary_stats,
    get_today_count,
    get_top_attenders,
    import_attendance_file,
    read_attendance,
    read_students,
    setup_logging,
    sync_students_from_attendance,
)
from utils.notification_utils import (
    acknowledge_alert,
    get_notification_summary,
    scan_and_notify_defaulters,
    start_notification_worker,
)


BASE_DIR = Path(__file__).resolve().parent
DATASET_DIR = BASE_DIR / "dataset"
INVALID_NAMES = {
    "open start attendance",
    "start attendance",
    "register face",
    "open dashboard",
    "start jarvis voice",
    "exit",
    "none",
    "",
}

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"))
app.secret_key = "facial-attendance-dashboard-secret"
setup_logging()
notification_worker_started = False


def normalize_student_key(value):
    """Normalize names and folder names so attendance rows can match dataset folders."""
    return "".join(character.lower() for character in str(value) if character.isalnum())


def is_valid_person_name(value):
    """Return True when a record name is a real student/person name."""
    return str(value or "").strip().lower() not in INVALID_NAMES


def find_student_image(student_name):
    """Return the first available dataset image path for a student."""
    students_df = read_students()
    target_key = normalize_student_key(student_name)
    matches = students_df[students_df["Name"].astype(str).apply(normalize_student_key) == target_key]
    if not matches.empty:
        photo_path = str(matches.iloc[0].get("PhotoPath", "") or "").strip()
        if photo_path:
            resolved_path = (BASE_DIR / photo_path).resolve()
            if resolved_path.exists() and resolved_path.is_file():
                return resolved_path

    if not DATASET_DIR.exists():
        return None

    for folder in DATASET_DIR.iterdir():
        if not folder.is_dir() or normalize_student_key(folder.name) != target_key:
            continue

        for image_path in sorted(folder.iterdir()):
            if image_path.is_file() and image_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                return image_path

    return None


def build_media_url(relative_path):
    """Convert a stored relative media path into a dashboard URL."""
    relative_path = str(relative_path or "").strip().replace("\\", "/")
    if not relative_path:
        return None
    return url_for("media_file", relative_path=relative_path)


def get_fallback_image_url(student_name):
    """Return a student's dataset image URL when a row has no direct image path."""
    image_path = find_student_image(student_name)
    if image_path is None:
        return None
    return url_for("student_image", student_name=student_name)


def serialize_attendance_records(attendance_df):
    """Prepare attendance rows for templates and APIs."""
    records = []
    students_df = read_students()
    metadata_lookup = {
        normalize_student_key(row["Name"]): row
        for _, row in students_df.iterrows()
        if is_valid_person_name(row.get("Name", ""))
    }

    for row in attendance_df.to_dict(orient="records"):
        student_name = str(row.get("Name", "") or "").strip()
        if not is_valid_person_name(student_name):
            continue

        metadata = metadata_lookup.get(normalize_student_key(student_name))
        roll_number = str(row.get("RollNumber", "") or "").strip()
        class_name = str(row.get("Class", "") or "").strip()
        if metadata is not None:
            roll_number = roll_number or str(metadata.get("RollNumber", "") or "").strip()
            class_name = class_name or str(metadata.get("Class", "") or "").strip()

        row["Name"] = student_name
        row["RollNumber"] = roll_number
        row["Class"] = class_name
        row["Image"] = str(row.get("Image", "") or "")
        row["ImageUrl"] = build_media_url(row["Image"]) or get_fallback_image_url(student_name)
        records.append(row)

    return records


def build_student_profiles(attendance_df, students_df, attendance_pct_lookup=None):
    """Build per-student dashboard cards with attendance stats and registry details."""
    attendance_pct_lookup = attendance_pct_lookup or {}
    student_profiles = []
    summary_lookup = {}

    if not attendance_df.empty:
        for student_name, student_rows in attendance_df.groupby("Name", sort=True):
            if not is_valid_person_name(student_name):
                continue
            summary_lookup[normalize_student_key(student_name)] = student_rows.sort_values(["Date", "Time"], ascending=[False, False]).iloc[0]

    for _, student_row in students_df.sort_values("Name").iterrows():
        student_name = str(student_row["Name"]).strip()
        if not is_valid_person_name(student_name):
            continue

        latest_row = summary_lookup.get(normalize_student_key(student_name))
        image_path = find_student_image(student_name)
        latest_image_url = build_media_url(latest_row.get("Image", "")) if latest_row is not None else None
        photo_path = str(student_row.get("PhotoPath", "") or "").strip()
        student_profiles.append(
            {
                "Name": student_name,
                "RollNumber": str(student_row.get("RollNumber", "") or "").strip(),
                "Class": str(student_row.get("Class", "") or "").strip(),
                "PhotoPath": photo_path,
                "Count": int(len(attendance_df[attendance_df["Name"] == student_name])) if not attendance_df.empty else 0,
                "LastDate": latest_row["Date"] if latest_row is not None else "",
                "LastTime": latest_row["Time"] if latest_row is not None else "",
                "Status": latest_row["Status"] if latest_row is not None else "No Attendance Yet",
                "AttendancePct": attendance_pct_lookup.get(student_name, 0.0),
                "StudentEmail": str(student_row.get("StudentEmail", "") or "").strip(),
                "ParentEmail": str(student_row.get("ParentEmail", "") or "").strip(),
                "StudentPhone": str(student_row.get("StudentPhone", "") or "").strip(),
                "ParentPhone": str(student_row.get("ParentPhone", "") or "").strip(),
                "ImageUrl": latest_image_url or build_media_url(photo_path) or (url_for("student_image", student_name=student_name) if image_path else None),
            }
        )

    return student_profiles


def build_latest_highlight(records):
    """Return the most recent valid attendance record with an image for the hero panel."""
    if not records:
        return None

    for record in reversed(records):
        if not is_valid_person_name(record.get("Name", "")):
            continue
        ensure_student_record(record["Name"], photo_path=record.get("Image", ""))
        record["ImageUrl"] = record.get("ImageUrl") or get_fallback_image_url(record["Name"])
        if record["ImageUrl"]:
            return record

    for record in reversed(records):
        if is_valid_person_name(record.get("Name", "")):
            record["ImageUrl"] = record.get("ImageUrl") or get_fallback_image_url(record["Name"])
            return record

    return None


def build_dashboard_payload():
    """Build dashboard data for initial page load and live refreshes."""
    attendance_df = read_attendance()
    sync_students_from_attendance(attendance_df)
    students_df = read_students()

    attendance_percentages = get_attendance_percentage_per_student()
    attendance_percentages = [
        item for item in attendance_percentages
        if is_valid_person_name(item.get("Name", ""))
    ]
    attendance_pct_lookup = {
        item["Name"]: item["Percentage"]
        for item in attendance_percentages
    }

    records = serialize_attendance_records(attendance_df)
    summary = [item for item in get_summary_counts() if is_valid_person_name(item.get("Name", ""))]
    for item in summary:
        item["Percentage"] = attendance_pct_lookup.get(item["Name"], 0.0)

    recent_records = list(reversed([record for record in records if is_valid_person_name(record.get("Name", ""))][-10:]))
    student_profiles = build_student_profiles(attendance_df, students_df, attendance_pct_lookup)
    latest_highlight = build_latest_highlight(records)
    summary_stats = get_summary_stats()

    return {
        "records": records,
        "recent_records": recent_records,
        "summary": summary,
        "student_profiles": student_profiles,
        "latest_highlight": latest_highlight,
        "total_records": len(records),
        "total_students": len(student_profiles),
        "today_count": get_today_count(),
        "overall_percentage": get_overall_percentage(),
        "defaulters_count": len([row for row in attendance_percentages if float(row["Percentage"]) < 75]),
        "notification_status": get_notification_summary(),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.route("/")
def index():
    """Dashboard home page with attendance records and quick analytics."""
    return render_template("index.html", **build_dashboard_payload())


@app.route("/api/live-data")
def live_data():
    """Return dashboard data for client-side live refreshes."""
    return jsonify(build_dashboard_payload())


@app.route("/api/analytics-data")
def analytics_data():
    """Return attendance analytics data for charts and tables."""
    attendance_per_student = [
        row for row in get_attendance_percentage_per_student()
        if is_valid_person_name(row.get("Name", ""))
    ]
    defaulters = [
        {"Name": row["Name"], "Percentage": row["Percentage"]}
        for row in attendance_per_student
        if float(row["Percentage"]) < 75
    ]
    top_attenders = [
        {"Name": row["Name"], "Percentage": row["Percentage"]}
        for row in attendance_per_student
        if float(row["Percentage"]) >= 75
    ][:5]
    return jsonify(
        {
            "attendance_per_student": attendance_per_student,
            "attendance_percentage_per_student": attendance_per_student,
            "daily_trend": get_daily_trend(),
            "defaulters": defaulters,
            "top_attenders": top_attenders,
        }
    )


@app.route("/api/notification-status")
def notification_status():
    """Return notification system configuration and delivery status."""
    return jsonify(get_notification_summary())


@app.route("/api/send-notifications", methods=["POST"])
def send_notifications():
    """Scan at-risk students and send attendance alerts now."""
    try:
        return jsonify(scan_and_notify_defaulters())
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@app.route("/alert-ack/<alert_id>", methods=["GET", "POST"])
def acknowledge_notification(alert_id):
    """Let a receiver confirm an attendance alert and stop the sender alarm."""
    if request.method == "POST":
        acknowledged = acknowledge_alert(alert_id)
        message = "Alert acknowledged. Thank you." if acknowledged else "This alert was already acknowledged or was not found."
        return f"""
        <!doctype html>
        <html lang="en">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Alert Acknowledged</title>
            <style>
                body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: Arial, sans-serif; background: #0d0a12; color: #f1eeff; }}
                main {{ width: min(520px, 92vw); text-align: center; }}
                h1 {{ margin-bottom: 10px; }}
                p {{ color: #c8bee6; font-size: 18px; }}
            </style>
        </head>
        <body><main><h1>OK</h1><p>{message}</p></main></body>
        </html>
        """

    return """
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Acknowledge Attendance Alert</title>
        <style>
            body { margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: Arial, sans-serif; background: #0d0a12; color: #f1eeff; }
            main { width: min(520px, 92vw); text-align: center; }
            p { color: #c8bee6; font-size: 18px; }
            button { border: 0; border-radius: 14px; padding: 14px 28px; background: #fbbf24; color: #0d0a12; font-weight: 800; font-size: 18px; cursor: pointer; }
        </style>
    </head>
    <body>
        <main>
            <h1>Attendance Alert</h1>
            <p>Press OK to confirm that you received this alert.</p>
            <form method="post"><button type="submit">OK</button></form>
        </main>
    </body>
    </html>
    """


@app.route("/media/<path:relative_path>")
def media_file(relative_path):
    """Serve locally stored attendance images referenced by relative path."""
    requested_path = (BASE_DIR / relative_path).resolve()
    base_resolved = BASE_DIR.resolve()

    if base_resolved not in requested_path.parents:
        abort(404)

    if not requested_path.exists() or not requested_path.is_file():
        abort(404)

    return send_file(requested_path)


@app.route("/student-image/<path:student_name>")
def student_image(student_name):
    """Serve a student's dataset image to the dashboard."""
    image_path = find_student_image(student_name)
    if image_path is None or not image_path.exists():
        abort(404)

    return send_file(image_path)


@app.route("/import", methods=["POST"])
def import_attendance():
    """Import attendance data from a CSV or Excel file."""
    uploaded_file = request.files.get("attendance_file")
    if uploaded_file is None or not uploaded_file.filename:
        flash("Please choose a CSV or Excel file to import.", "error")
        return redirect(url_for("index"))

    try:
        result = import_attendance_file(uploaded_file, uploaded_file.filename)
        flash(
            f"Import complete. Added {result['added_rows']} rows, skipped {result['skipped_rows']} duplicates.",
            "success",
        )
    except Exception as error:
        flash(str(error), "error")

    return redirect(url_for("index"))


@app.route("/analytics")
def analytics():
    """Render the attendance analytics page."""
    return render_template("analytics.html", **build_dashboard_payload())


@app.route("/download-report")
def download_report():
    """Generate and download the attendance PDF report."""
    from utils.report_generator import generate_pdf_report

    output_path = BASE_DIR / "attendance_report.pdf"
    generate_pdf_report(str(output_path))
    return send_file(
        str(output_path),
        as_attachment=True,
        download_name="FRAS_Attendance_Report.pdf",
        mimetype="application/pdf",
    )


def start_dashboard(host="127.0.0.1", port=5000, debug=False, open_browser=False):
    """Run the Flask dashboard server."""
    global notification_worker_started
    if not notification_worker_started:
        start_notification_worker()
        notification_worker_started = True

    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    app.run(host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    start_dashboard(open_browser=True)
