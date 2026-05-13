
import base64
import csv
import json
import logging
import os
import smtplib
import ssl
import threading
import time
import uuid
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from utils.attendance_utils import (
    get_attendance_percentage_per_student,
    is_valid_attendance_name,
    normalize_student_key,
    read_attendance,
    read_students,
)


BASE_DIR = Path(__file__).resolve().parent.parent
NOTIFICATION_LOG_FILE = BASE_DIR / "notifications.csv"
ENV_FILE = BASE_DIR / ".env"
DEFAULT_COURSE_ID = "general"
NOTIFICATION_COLUMNS = [
    "AlertId",
    "Date",
    "Name",
    "Percentage",
    "Threshold",
    "Channel",
    "Recipient",
    "Status",
    "StudentId",
    "CourseId",
    "AlertType",
    "SentAt",
    "AcknowledgedAt",
]


def load_notification_env():
    """Load simple KEY=value notification settings from facial_attendance/.env."""
    if not ENV_FILE.exists():
        return

    try:
        with ENV_FILE.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        logging.exception("Unable to load notification settings from %s.", ENV_FILE)


load_notification_env()


def get_threshold():
    """Return the configured minimum attendance percentage."""
    try:
        return float(os.getenv("ATTENDANCE_THRESHOLD_PERCENT", "75"))
    except ValueError:
        return 75.0


def ensure_notification_log():
    """Create the notification log CSV when it does not exist."""
    if not NOTIFICATION_LOG_FILE.exists():
        with NOTIFICATION_LOG_FILE.open("w", newline="", encoding="utf-8") as file:
            csv.writer(file).writerow(NOTIFICATION_COLUMNS)
        return

    with NOTIFICATION_LOG_FILE.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        existing_columns = reader.fieldnames or []
        rows = list(reader)

    if existing_columns == NOTIFICATION_COLUMNS:
        return

    with NOTIFICATION_LOG_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=NOTIFICATION_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in NOTIFICATION_COLUMNS})


def read_notification_log():
    """Return notification log rows as dictionaries."""
    ensure_notification_log()
    with NOTIFICATION_LOG_FILE.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        return list(reader)


def append_notification_log(name, percentage, threshold, channel, recipient, status, student_id="", course_id=DEFAULT_COURSE_ID, alert_id=""):
    """Append a delivery attempt to the notification log."""
    ensure_notification_log()
    sent_at = datetime.now()
    alert_id = alert_id or uuid.uuid4().hex
    with NOTIFICATION_LOG_FILE.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=NOTIFICATION_COLUMNS)
        writer.writerow(
            {
                "AlertId": alert_id,
                "Date": sent_at.strftime("%Y-%m-%d"),
                "Name": name,
                "Percentage": f"{float(percentage):.1f}",
                "Threshold": f"{float(threshold):.1f}",
                "Channel": channel,
                "Recipient": recipient,
                "Status": status,
                "StudentId": student_id,
                "CourseId": course_id or DEFAULT_COURSE_ID,
                "AlertType": "attendance-threshold",
                "SentAt": sent_at.strftime("%Y-%m-%d %H:%M:%S"),
                "AcknowledgedAt": "",
            }
        )
    return alert_id


def get_public_base_url():
    """Return the externally reachable dashboard URL used in acknowledgement links."""
    return os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")


def build_acknowledgement_url(alert_id):
    """Build the receiver OK link when a public app URL is configured."""
    base_url = get_public_base_url()
    if not base_url or not alert_id:
        return ""
    return f"{base_url}/alert-ack/{alert_id}"


def acknowledge_alert(alert_id):
    """Mark a sent alert as acknowledged by the receiver."""
    alert_key = str(alert_id or "").strip()
    if not alert_key:
        return False

    ensure_notification_log()
    with NOTIFICATION_LOG_FILE.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    changed = False
    acknowledged_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for row in rows:
        if str(row.get("AlertId", "")).strip() == alert_key and not str(row.get("AcknowledgedAt", "")).strip():
            row["AcknowledgedAt"] = acknowledged_at
            changed = True

    if not changed:
        return False

    with NOTIFICATION_LOG_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=NOTIFICATION_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in NOTIFICATION_COLUMNS})

    return True


def get_pending_acknowledgements():
    """Return sent alerts that still need receiver acknowledgement."""
    if not get_public_base_url():
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    pending = []
    for row in read_notification_log():
        if row.get("Date") != today:
            continue
        if row.get("Status") not in {"sent", "dry-run"}:
            continue
        if not row.get("AlertId") or row.get("AcknowledgedAt"):
            continue
        pending.append(row)
    return pending


def was_alert_sent_today(name, threshold, channel, recipient, course_id=DEFAULT_COURSE_ID):
    """Avoid sending the same alert repeatedly on the same day."""
    today = datetime.now().strftime("%Y-%m-%d")
    recipient_key = str(recipient or "").strip().lower()
    name_key = str(name or "").strip().lower()
    threshold_key = f"{float(threshold):.1f}"

    for row in read_notification_log():
        if row.get("Date") != today:
            continue
        if row.get("Status") not in {"sent", "dry-run"}:
            continue
        if str(row.get("Name", "")).strip().lower() != name_key:
            continue
        if str(row.get("Recipient", "")).strip().lower() != recipient_key:
            continue
        row_course = str(row.get("CourseId", "") or DEFAULT_COURSE_ID).strip()
        if row.get("Channel") == channel and row.get("Threshold") == threshold_key and row_course == course_id:
            return True

    return False


def get_student_contacts():
    """Build a name-keyed contact lookup from students.csv."""
    students = read_students()
    contacts = {}
    for _, row in students.iterrows():
        student_name = str(row.get("Name", "") or "").strip()
        if not student_name or not is_valid_attendance_name(student_name):
            continue
        contacts[student_name.lower()] = {
            "StudentId": str(row.get("StudentId", "") or row.get("RollNumber", "") or "").strip(),
            "Name": student_name,
            "StudentEmail": str(row.get("StudentEmail", "") or "").strip(),
            "ParentEmail": str(row.get("ParentEmail", "") or "").strip(),
            "StudentPhone": str(row.get("StudentPhone", "") or "").strip(),
            "ParentPhone": str(row.get("ParentPhone", "") or "").strip(),
            "EnrolledCourses": str(row.get("EnrolledCourses", "") or DEFAULT_COURSE_ID).strip(),
        }
    return contacts


def get_student_by_id(student_id):
    """Return student data using StudentId, RollNumber, or Name as accepted identifiers."""
    students = read_students()
    target = str(student_id or "").strip()
    target_key = normalize_student_key(target)
    if not target_key:
        return None

    for _, row in students.iterrows():
        possible_values = [
            row.get("StudentId", ""),
            row.get("RollNumber", ""),
            row.get("Name", ""),
        ]
        if any(normalize_student_key(value) == target_key for value in possible_values):
            student = row.to_dict()
            student["StudentId"] = str(student.get("StudentId", "") or student.get("RollNumber", "") or student.get("Name", "")).strip()
            return student

    return None


def normalize_course_id(course_id):
    """Return a stable course id for old attendance records that do not store courses."""
    course = str(course_id or DEFAULT_COURSE_ID).strip()
    return course or DEFAULT_COURSE_ID


def calculateAttendancePercentage(studentId, courseId=DEFAULT_COURSE_ID):
    """
    Query attendance records for the student in a course and return attendance percentage.
    Late is counted as attended. Absent is not counted.
    """
    student = get_student_by_id(studentId)
    if student is None:
        return 0.0

    course_id = normalize_course_id(courseId)
    student_keys = {
        normalize_student_key(student.get("StudentId", "")),
        normalize_student_key(student.get("RollNumber", "")),
        normalize_student_key(student.get("Name", "")),
    }
    student_keys.discard("")

    attendance = read_attendance()
    if attendance.empty:
        return 0.0

    records = attendance.copy()
    records["Name"] = records["Name"].astype(str).str.strip()
    records["StudentId"] = records.get("StudentId", "").astype(str).str.strip()
    records["CourseId"] = records.get("CourseId", DEFAULT_COURSE_ID).astype(str).str.strip().replace("", DEFAULT_COURSE_ID)
    records["Date"] = records["Date"].astype(str).str.strip()
    records["Status"] = records["Status"].astype(str).str.lower().str.strip()

    records = records[
        (records["Date"] != "")
        & (records["Name"].apply(is_valid_attendance_name))
        & (records["CourseId"] == course_id)
    ]
    if records.empty:
        return 0.0

    match_mask = (
        records["StudentId"].apply(normalize_student_key).isin(student_keys)
        | records["Name"].apply(normalize_student_key).isin(student_keys)
    )
    student_records = records[match_mask].drop_duplicates(subset=["Date", "CourseId"], keep="last")
    if student_records.empty:
        return 0.0

    total_classes = int(records.drop_duplicates(subset=["Date", "CourseId"])["Date"].nunique())
    attended = int(student_records[student_records["Status"].isin({"present", "late"})]["Date"].nunique())
    if total_classes <= 0:
        return 0.0

    return round((attended / total_classes) * 100, 1)


def checkAttendanceThreshold(studentId, courseId=DEFAULT_COURSE_ID, threshold=75):
    """Compare current attendance percentage against the minimum threshold."""
    threshold_value = float(threshold)
    current_percentage = calculateAttendancePercentage(studentId, courseId)
    return {
        "isBelowThreshold": current_percentage < threshold_value,
        "currentPercentage": current_percentage,
        "deficit": round(max(threshold_value - current_percentage, 0), 1),
    }


def sendEmailAlert(recipient, studentData, attendanceData):
    """Send an email alert to a student or parent."""
    course = attendanceData.get("courseId", DEFAULT_COURSE_ID)
    threshold = float(attendanceData.get("threshold", get_threshold()))
    current_percentage = float(attendanceData.get("currentPercentage", 0))
    student_name = studentData.get("Name") or studentData.get("name") or "Student"
    subject = f"Attendance Alert: {student_name} is below {threshold:.1f}%"
    body = (
        f"Dear Student/Parent,\n\n"
        f"This is an automated attendance alert from FRAS.\n\n"
        f"Student: {student_name}\n"
        f"Course: {course}\n"
        f"Current Attendance: {current_percentage:.1f}%\n"
        f"Minimum Required: {threshold:.1f}%\n"
        f"Deficit: {float(attendanceData.get('deficit', 0)):.1f}%\n\n"
        f"Please contact the class teacher or attendance office if support is needed.\n"
    )
    send_email(recipient, subject, body)


def sendSMSAlert(phoneNumber, message):
    """Send a concise SMS alert."""
    send_sms(phoneNumber, message)


def build_sms_alert(student_data, attendance_data):
    """Build concise SMS text for Twilio."""
    student_name = student_data.get("Name") or student_data.get("name") or "Student"
    return (
        f"FRAS Alert: {student_name} attendance in {attendance_data.get('courseId', DEFAULT_COURSE_ID)} "
        f"is {float(attendance_data.get('currentPercentage', 0)):.1f}%, below "
        f"{float(attendance_data.get('threshold', get_threshold())):.1f}%."
    )


def get_defaulter_alerts(threshold=None, course_id=DEFAULT_COURSE_ID):
    """Return attendance rows below the notification threshold with contact metadata."""
    threshold = get_threshold() if threshold is None else float(threshold)
    course_id = normalize_course_id(course_id)
    contacts = get_student_contacts()
    alerts = []

    for contact in contacts.values():
        student_id = contact.get("StudentId") or contact.get("Name")
        threshold_result = checkAttendanceThreshold(student_id, course_id, threshold)
        if not threshold_result["isBelowThreshold"]:
            continue

        alerts.append(
            {
                "Name": contact.get("Name", ""),
                "StudentId": student_id,
                "CourseId": course_id,
                "Percentage": threshold_result["currentPercentage"],
                "Threshold": threshold,
                "Deficit": threshold_result["deficit"],
                "DaysPresent": "",
                "TotalDays": "",
                "StudentEmail": contact.get("StudentEmail", ""),
                "ParentEmail": contact.get("ParentEmail", ""),
                "StudentPhone": contact.get("StudentPhone", ""),
                "ParentPhone": contact.get("ParentPhone", ""),
            }
        )

    return alerts


def build_alert_message(alert, alert_id=""):
    """Create reusable subject/body text for email and SMS."""
    acknowledgement_url = build_acknowledgement_url(alert_id)
    acknowledgement_text = f"\nAcknowledge this alert: {acknowledgement_url}\n" if acknowledgement_url else ""
    acknowledgement_sms = f" OK: {acknowledgement_url}" if acknowledgement_url else ""
    subject = f"Attendance Alert: {alert['Name']} is below {alert['Threshold']:.1f}%"
    body = (
        f"Dear Student/Parent,\n\n"
        f"This is an automated attendance alert from FRAS.\n\n"
        f"Student: {alert['Name']}\n"
        f"Course: {alert.get('CourseId', DEFAULT_COURSE_ID)}\n"
        f"Current Attendance: {alert['Percentage']:.1f}%\n"
        f"Minimum Required: {alert['Threshold']:.1f}%\n"
        f"Deficit: {float(alert.get('Deficit', 0)):.1f}%\n\n"
        f"Please contact the class teacher or attendance office if you need help improving attendance.\n"
        f"{acknowledgement_text}"
    )
    sms = (
        f"FRAS Alert: {alert['Name']} attendance in {alert.get('CourseId', DEFAULT_COURSE_ID)} is {alert['Percentage']:.1f}%, "
        f"below required {alert['Threshold']:.1f}%. Deficit {float(alert.get('Deficit', 0)):.1f}%."
        f"{acknowledgement_sms}"
    )
    return subject, body, sms


def has_config_value(name):
    """Return True when an environment value is present and not a template placeholder."""
    value = os.getenv(name, "").strip()
    if not value:
        return False

    placeholder_tokens = {"paste_", "your_", "xxxxxxxx"}
    normalized = value.lower()
    return not any(token in normalized for token in placeholder_tokens)


def email_configured():
    """Return True when SMTP settings are available."""
    return has_config_value("SMTP_HOST") and has_config_value("SMTP_SENDER")


def get_email_config_status():
    """Return a dashboard-friendly SMTP configuration status."""
    required = ["SMTP_HOST", "SMTP_SENDER"]
    optional_auth = ["SMTP_USERNAME", "SMTP_PASSWORD"]
    missing = [name for name in required if not has_config_value(name)]
    auth_partial = any(has_config_value(name) for name in optional_auth) and not all(has_config_value(name) for name in optional_auth)
    if auth_partial:
        missing.extend([name for name in optional_auth if not has_config_value(name)])

    return {
        "configured": not missing,
        "missing": missing,
        "message": "Ready" if not missing else "Missing " + ", ".join(missing),
    }


def sms_configured():
    """Return True when Twilio settings are available."""
    return bool(
        has_config_value("TWILIO_ACCOUNT_SID")
        and has_config_value("TWILIO_AUTH_TOKEN")
        and has_config_value("TWILIO_FROM_PHONE")
    )


def get_sms_config_status():
    """Return a dashboard-friendly Twilio configuration status."""
    required = ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_PHONE"]
    missing = [name for name in required if not has_config_value(name)]
    return {
        "configured": not missing,
        "missing": missing,
        "message": "Ready" if not missing else "Missing " + ", ".join(missing),
    }


def is_dry_run():
    """Allow safe local testing without sending real messages."""
    return os.getenv("NOTIFICATION_DRY_RUN", "").strip().lower() in {"1", "true", "yes", "on"}


def send_email(recipient, subject, body):
    """Send one email alert through SMTP."""
    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_SENDER", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() != "false"

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    if use_tls:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls(context=ssl.create_default_context())
            if username:
                server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP_SSL(host, port, timeout=20) as server:
            if username:
                server.login(username, password)
            server.send_message(message)


def send_sms(recipient, message):
    """Send one SMS alert through Twilio's REST API."""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    from_phone = os.getenv("TWILIO_FROM_PHONE", "").strip()
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    payload = urlencode({"To": recipient, "From": from_phone, "Body": message}).encode("utf-8")
    auth = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("ascii")
    request = Request(url, data=payload, headers={"Authorization": f"Basic {auth}"}, method="POST")

    with urlopen(request, timeout=20) as response:
        json.loads(response.read().decode("utf-8"))


def scan_and_notify_defaulters(threshold=None, course_id=DEFAULT_COURSE_ID):
    """
    Send alerts for students below the attendance threshold.
    Returns a delivery summary for dashboard/API display.
    """
    threshold = get_threshold() if threshold is None else float(threshold)
    course_id = normalize_course_id(course_id)
    alerts = get_defaulter_alerts(threshold, course_id)
    summary = {
        "threshold": threshold,
        "alerts_found": len(alerts),
        "sent": 0,
        "skipped": 0,
        "failed": 0,
        "details": [],
    }

    email_ready = email_configured()
    sms_ready = sms_configured()
    dry_run = is_dry_run()
    email_status = get_email_config_status()
    sms_status = get_sms_config_status()

    acknowledgement_enabled = bool(get_public_base_url())

    for alert in alerts:
        recipients = [
            ("email", alert.get("StudentEmail", "")),
            ("email", alert.get("ParentEmail", "")),
            ("sms", alert.get("StudentPhone", "")),
            ("sms", alert.get("ParentPhone", "")),
        ]
        has_recipient = False

        for channel, recipient in recipients:
            recipient = str(recipient or "").strip()
            if not recipient:
                continue
            has_recipient = True

            detail = {"Name": alert["Name"], "Channel": channel, "Recipient": recipient}
            if was_alert_sent_today(alert["Name"], threshold, channel, recipient, course_id):
                detail["Status"] = "already-sent-today"
                summary["skipped"] += 1
                summary["details"].append(detail)
                continue

            if channel == "email" and not email_ready and not dry_run:
                detail["Status"] = "missing-email-config"
                detail["Reason"] = email_status["message"]
                summary["skipped"] += 1
                summary["details"].append(detail)
                continue

            if channel == "sms" and not sms_ready and not dry_run:
                detail["Status"] = "missing-sms-config"
                detail["Reason"] = sms_status["message"]
                summary["skipped"] += 1
                summary["details"].append(detail)
                continue

            try:
                alert_id = uuid.uuid4().hex
                subject, body, sms = build_alert_message(alert, alert_id)
                if dry_run:
                    append_notification_log(alert["Name"], alert["Percentage"], threshold, channel, recipient, "dry-run", alert.get("StudentId", ""), course_id, alert_id)
                    detail["Status"] = "dry-run"
                elif channel == "email":
                    send_email(recipient, subject, body)
                    append_notification_log(alert["Name"], alert["Percentage"], threshold, channel, recipient, "sent", alert.get("StudentId", ""), course_id, alert_id)
                    detail["Status"] = "sent"
                else:
                    send_sms(recipient, sms)
                    append_notification_log(alert["Name"], alert["Percentage"], threshold, channel, recipient, "sent", alert.get("StudentId", ""), course_id, alert_id)
                    detail["Status"] = "sent"
                detail["AlertId"] = alert_id
                detail["AcknowledgementEnabled"] = acknowledgement_enabled
                summary["sent"] += 1
            except (OSError, smtplib.SMTPException, URLError) as error:
                logging.exception("Notification failed for %s via %s", alert["Name"], channel)
                append_notification_log(alert["Name"], alert["Percentage"], threshold, channel, recipient, "failed", alert.get("StudentId", ""), course_id)
                detail["Status"] = f"failed: {error}"
                summary["failed"] += 1

            summary["details"].append(detail)

        if not has_recipient:
            summary["skipped"] += 1
            summary["details"].append(
                {
                    "Name": alert["Name"],
                    "Channel": "none",
                    "Recipient": "",
                    "Status": "missing-contact",
                }
            )

    return summary


def runAttendanceAlertJob(threshold=75, courseId=DEFAULT_COURSE_ID):
    """Cron/job entry point that scans students and sends alerts."""
    return scan_and_notify_defaulters(threshold=threshold, course_id=courseId)


def get_notification_summary():
    """Return notification status data for the dashboard."""
    alerts = get_defaulter_alerts()
    log_rows = read_notification_log()
    today = datetime.now().strftime("%Y-%m-%d")
    email_status = get_email_config_status()
    sms_status = get_sms_config_status()
    return {
        "threshold": get_threshold(),
        "alerts_found": len(alerts),
        "email_configured": email_status["configured"],
        "sms_configured": sms_status["configured"],
        "email_status": email_status,
        "sms_status": sms_status,
        "dry_run": is_dry_run(),
        "sent_today": len([row for row in log_rows if row.get("Date") == today and row.get("Status") in {"sent", "dry-run"}]),
        "acknowledgement_enabled": bool(get_public_base_url()),
        "pending_acknowledgements": len(get_pending_acknowledgements()),
        "last_checked": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def start_notification_worker(interval_seconds=None):
    """Start a lightweight background notification scan loop."""
    interval = int(interval_seconds or os.getenv("NOTIFICATION_CHECK_INTERVAL_SECONDS", "3600"))

    def worker():
        while True:
            try:
                scan_and_notify_defaulters()
            except Exception:
                logging.exception("Scheduled notification scan failed.")
            time.sleep(max(interval, 60))

    thread = threading.Thread(target=worker, daemon=True, name="attendance-notification-worker")
    thread.start()
    return thread
