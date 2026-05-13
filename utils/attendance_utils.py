import csv
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent
ATTENDANCE_FILE = BASE_DIR / "attendance.csv"
STUDENTS_FILE = BASE_DIR / "students.csv"
DATASET_DIR = BASE_DIR / "dataset"
LOG_FILE = BASE_DIR / "system.log"
ATTENDANCE_COLUMNS = ["Name", "Date", "Time", "Status", "Image"]
OPTIONAL_ATTENDANCE_COLUMNS = ["StudentId", "CourseId", "RollNumber", "Class"]
STUDENT_COLUMNS = [
    "StudentId",
    "Name",
    "RollNumber",
    "Class",
    "PhotoPath",
    "StudentEmail",
    "ParentEmail",
    "StudentPhone",
    "ParentPhone",
    "EnrolledCourses",
]
PROFILE_FILE_NAME = "profile.csv"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
INVALID_ATTENDANCE_NAMES = {
    "open start attendance",
    "start attendance",
    "register face",
    "open dashboard",
    "start jarvis voice",
    "exit",
    "none",
    "",
}


def setup_logging():
    """Configure application logging once for the whole project."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=False,
    )


def ensure_attendance_file():
    """Create the attendance CSV with headers when it does not exist."""
    ATTENDANCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not ATTENDANCE_FILE.exists():
        with ATTENDANCE_FILE.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(ATTENDANCE_COLUMNS)


def sanitize_student_folder_name(name):
    """Create a file-safe folder name for student image directories."""
    cleaned = re.sub(r"[^a-zA-Z0-9 _-]", "", str(name)).strip()
    safe_name = cleaned.replace(" ", "_")
    return safe_name or "student"


def normalize_student_key(value):
    """Normalize student names and folder names for reliable matching."""
    return "".join(character.lower() for character in str(value) if character.isalnum())


def is_valid_attendance_name(value):
    """Return True when a name looks like a real attendance subject."""
    return str(value or "").strip().lower() not in INVALID_ATTENDANCE_NAMES


def ensure_students_file():
    """Create the student registry CSV with headers when it does not exist."""
    STUDENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not STUDENTS_FILE.exists():
        with STUDENTS_FILE.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(STUDENT_COLUMNS)


def read_csv_or_empty(path, columns):
    """Read a CSV file, returning an empty table when it is missing, empty, or locked."""
    try:
        return pd.read_csv(path, dtype=str).fillna("")
    except (pd.errors.EmptyDataError, FileNotFoundError):
        return pd.DataFrame(columns=columns)
    except PermissionError:
        logging.warning("Unable to read %s because permission was denied.", path)
        return pd.DataFrame(columns=columns)


def write_dataframe_csv(dataframe, path, columns):
    """Write a DataFrame to CSV and report whether the write succeeded."""
    try:
        dataframe[columns].to_csv(path, index=False)
        return True
    except PermissionError:
        logging.warning("Unable to write %s because permission was denied.", path)
        return False


def read_students():
    """Return student registry data with fallbacks from attendance records and dataset folders."""
    ensure_students_file()
    students_df = read_csv_or_empty(STUDENTS_FILE, STUDENT_COLUMNS)
    attendance_df = read_attendance()
    student_rows = {}

    for _, row in students_df.iterrows():
        student_name = str(row.get("Name", "")).strip()
        if not student_name:
            continue
        student_rows[normalize_student_key(student_name)] = {
            "StudentId": str(row.get("StudentId", "") or row.get("RollNumber", "") or "").strip(),
            "Name": student_name,
            "RollNumber": str(row.get("RollNumber", "") or "").strip(),
            "Class": str(row.get("Class", "") or "").strip(),
            "PhotoPath": str(row.get("PhotoPath", "") or "").strip(),
            "StudentEmail": str(row.get("StudentEmail", "") or "").strip(),
            "ParentEmail": str(row.get("ParentEmail", "") or "").strip(),
            "StudentPhone": str(row.get("StudentPhone", "") or "").strip(),
            "ParentPhone": str(row.get("ParentPhone", "") or "").strip(),
            "EnrolledCourses": str(row.get("EnrolledCourses", "") or "general").strip(),
        }

    if not attendance_df.empty:
        for _, row in attendance_df.iterrows():
            student_name = str(row.get("Name", "")).strip()
            if not student_name:
                continue

            target_key = normalize_student_key(student_name)
            existing_row = student_rows.get(
                target_key,
                {
                    "StudentId": str(row.get("StudentId", "") or row.get("RollNumber", "") or "").strip(),
                    "Name": student_name,
                    "RollNumber": "",
                    "Class": "",
                    "PhotoPath": "",
                    "StudentEmail": "",
                    "ParentEmail": "",
                    "StudentPhone": "",
                    "ParentPhone": "",
                    "EnrolledCourses": "general",
                },
            )

            image_path = str(row.get("Image", "") or "").strip()
            if image_path and not existing_row["PhotoPath"]:
                existing_row["PhotoPath"] = image_path

            roll_number = str(row.get("RollNumber", "") or "").strip()
            if roll_number and not existing_row["RollNumber"]:
                existing_row["RollNumber"] = roll_number

            class_name = str(row.get("Class", "") or "").strip()
            if class_name and not existing_row["Class"]:
                existing_row["Class"] = class_name

            student_id = str(row.get("StudentId", "") or row.get("RollNumber", "") or "").strip()
            if student_id and not existing_row["StudentId"]:
                existing_row["StudentId"] = student_id

            student_rows[target_key] = existing_row

    if DATASET_DIR.exists():
        for folder in DATASET_DIR.iterdir():
            if not folder.is_dir() or folder.name.lower() == "unknown":
                continue

            student_name = folder.name.replace("_", " ").strip()
            if not student_name:
                continue

            profile_path = folder / PROFILE_FILE_NAME
            profile_row = {}
            if profile_path.exists():
                profile_df = read_csv_or_empty(profile_path, STUDENT_COLUMNS)
                if not profile_df.empty:
                    profile_row = profile_df.iloc[0].to_dict()
                    student_name = str(profile_row.get("Name", student_name) or student_name).strip()

            target_key = normalize_student_key(student_name)
            existing_row = student_rows.get(
                target_key,
                {
                    "StudentId": "",
                    "Name": student_name,
                    "RollNumber": "",
                    "Class": "",
                    "PhotoPath": "",
                    "StudentEmail": "",
                    "ParentEmail": "",
                    "StudentPhone": "",
                    "ParentPhone": "",
                    "EnrolledCourses": "general",
                },
            )

            if profile_row:
                roll_number = str(profile_row.get("RollNumber", "") or "").strip()
                if roll_number and not existing_row["RollNumber"]:
                    existing_row["RollNumber"] = roll_number

                student_id = str(profile_row.get("StudentId", "") or roll_number or "").strip()
                if student_id and not existing_row["StudentId"]:
                    existing_row["StudentId"] = student_id

                class_name = str(profile_row.get("Class", "") or "").strip()
                if class_name and not existing_row["Class"]:
                    existing_row["Class"] = class_name

                profile_photo_path = str(profile_row.get("PhotoPath", "") or "").strip()
                if profile_photo_path and not existing_row["PhotoPath"]:
                    existing_row["PhotoPath"] = profile_photo_path

                for column in ["StudentEmail", "ParentEmail", "StudentPhone", "ParentPhone"]:
                    contact_value = str(profile_row.get(column, "") or "").strip()
                    if contact_value and not existing_row[column]:
                        existing_row[column] = contact_value

                enrolled_courses = str(profile_row.get("EnrolledCourses", "") or "").strip()
                if enrolled_courses and not existing_row["EnrolledCourses"]:
                    existing_row["EnrolledCourses"] = enrolled_courses

            photo_path = find_student_photo_path(student_name)
            if photo_path and not existing_row["PhotoPath"]:
                existing_row["PhotoPath"] = photo_path

            student_rows[target_key] = existing_row

    dataframe = pd.DataFrame(student_rows.values(), columns=STUDENT_COLUMNS)
    if dataframe.empty:
        return pd.DataFrame(columns=STUDENT_COLUMNS)

    dataframe = dataframe.fillna("").sort_values("Name").reset_index(drop=True)
    return dataframe[STUDENT_COLUMNS]


def ensure_student_folder(name):
    """Create and return the dataset folder for a student."""
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    folder_path = DATASET_DIR / sanitize_student_folder_name(name)
    folder_path.mkdir(parents=True, exist_ok=True)
    return folder_path


def find_student_photo_path(name):
    """Return the first available dataset image path for a student as a relative path."""
    if not DATASET_DIR.exists():
        return ""

    target_key = normalize_student_key(name)
    for folder in DATASET_DIR.iterdir():
        if not folder.is_dir() or normalize_student_key(folder.name) != target_key:
            continue

        for image_path in sorted(folder.iterdir()):
            if image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTENSIONS:
                return image_path.relative_to(BASE_DIR).as_posix()

    return ""


def resolve_project_path(path_value):
    """Return an absolute path for a project-relative path value."""
    raw_path = str(path_value or "").strip()
    if not raw_path:
        return None

    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return BASE_DIR / candidate


def copy_photo_to_student_folder(student_name, photo_path):
    """Copy a profile photo into the student's dataset folder and return its relative path."""
    source_path = resolve_project_path(photo_path)
    if source_path is None or not source_path.exists() or not source_path.is_file():
        return ""
    if source_path.suffix.lower() not in IMAGE_EXTENSIONS:
        return ""

    folder_path = ensure_student_folder(student_name)
    try:
        source_path.resolve().relative_to(folder_path.resolve())
        return source_path.relative_to(BASE_DIR).as_posix()
    except ValueError:
        pass

    safe_name = sanitize_student_folder_name(student_name)
    target_suffix = ".jpg" if source_path.suffix.lower() in {".jpg", ".jpeg"} else source_path.suffix.lower()
    target_path = folder_path / f"{safe_name}_1{target_suffix}"
    suffix_number = 2
    while target_path.exists():
        target_path = folder_path / f"{safe_name}_{suffix_number}{target_suffix}"
        suffix_number += 1

    shutil.copy2(source_path, target_path)
    return target_path.relative_to(BASE_DIR).as_posix()


def get_profile_photo_path(student_name, photo_path=""):
    """Prefer a real image inside dataset/<student> for profile metadata."""
    requested_photo_path = str(photo_path or "").strip()
    source_path = resolve_project_path(requested_photo_path)
    folder_path = ensure_student_folder(student_name)
    if source_path is not None and source_path.exists() and source_path.suffix.lower() in IMAGE_EXTENSIONS:
        try:
            source_path.resolve().relative_to(folder_path.resolve())
            return source_path.relative_to(BASE_DIR).as_posix()
        except ValueError:
            pass

    dataset_photo_path = find_student_photo_path(student_name)
    if dataset_photo_path:
        return dataset_photo_path

    copied_photo_path = copy_photo_to_student_folder(student_name, requested_photo_path)
    if copied_photo_path:
        return copied_photo_path

    return requested_photo_path


def ensure_student_record(name, roll_number="", class_name="", photo_path=""):
    """Create or update a student registry row while preserving existing details."""
    student_name = str(name).strip()
    if not student_name:
        return None

    folder_path = ensure_student_folder(student_name)
    profile_path = folder_path / PROFILE_FILE_NAME
    existing_profile = {}

    if profile_path.exists():
        profile_df = read_csv_or_empty(profile_path, STUDENT_COLUMNS)
        if not profile_df.empty:
            existing_profile = profile_df.iloc[0].to_dict()

    requested_photo_path = str(photo_path or existing_profile.get("PhotoPath", "") or "").strip()
    profile_photo_path = get_profile_photo_path(student_name, requested_photo_path)

    profile_row = {
        "StudentId": str(existing_profile.get("StudentId", "") or roll_number or "").strip(),
        "Name": student_name,
        "RollNumber": str(roll_number or existing_profile.get("RollNumber", "") or "").strip(),
        "Class": str(class_name or existing_profile.get("Class", "") or "").strip(),
        "PhotoPath": profile_photo_path,
        "StudentEmail": str(existing_profile.get("StudentEmail", "") or "").strip(),
        "ParentEmail": str(existing_profile.get("ParentEmail", "") or "").strip(),
        "StudentPhone": str(existing_profile.get("StudentPhone", "") or "").strip(),
        "ParentPhone": str(existing_profile.get("ParentPhone", "") or "").strip(),
        "EnrolledCourses": str(existing_profile.get("EnrolledCourses", "") or "general").strip(),
    }
    profile_changed = any(str(existing_profile.get(column, "") or "").strip() != profile_row[column] for column in STUDENT_COLUMNS)
    profile_saved = True
    if profile_changed:
        profile_saved = write_dataframe_csv(pd.DataFrame([profile_row], columns=STUDENT_COLUMNS), profile_path, STUDENT_COLUMNS)

    ensure_students_file()
    students_df = read_csv_or_empty(STUDENTS_FILE, STUDENT_COLUMNS)
    for column in STUDENT_COLUMNS:
        if column not in students_df.columns:
            students_df[column] = ""

    target_key = normalize_student_key(student_name)
    match_mask = students_df["Name"].astype(str).apply(normalize_student_key) == target_key
    registry_changed = False
    if match_mask.any():
        row_index = students_df.index[match_mask][0]
        if str(students_df.at[row_index, "Name"]).strip() != student_name:
            students_df.at[row_index, "Name"] = student_name
            registry_changed = True
        for column in ["StudentId", "RollNumber", "Class", "PhotoPath", "EnrolledCourses"]:
            if profile_row[column] and (column == "PhotoPath" or not str(students_df.at[row_index, column]).strip()):
                if str(students_df.at[row_index, column]).strip() != profile_row[column]:
                    students_df.at[row_index, column] = profile_row[column]
                    registry_changed = True
    else:
        students_df.loc[len(students_df)] = profile_row
        registry_changed = True

    if not registry_changed:
        return profile_saved

    return write_dataframe_csv(students_df, STUDENTS_FILE, STUDENT_COLUMNS) and profile_saved


def get_student_metadata(name):
    """Return the latest known roll number and class for a student."""
    attendance_df = read_attendance()
    student_name = str(name).strip()
    empty_metadata = {"RollNumber": "", "Class": ""}

    if not student_name:
        return empty_metadata

    profile_path = ensure_student_folder(student_name) / PROFILE_FILE_NAME
    if profile_path.exists():
        profile_df = read_csv_or_empty(profile_path, STUDENT_COLUMNS)
        if not profile_df.empty:
            profile_row = profile_df.iloc[0]
            roll_number = str(profile_row.get("RollNumber", "") or "").strip()
            class_name = str(profile_row.get("Class", "") or "").strip()
            if roll_number or class_name:
                return {"RollNumber": roll_number, "Class": class_name}

    if attendance_df.empty:
        return empty_metadata

    target_key = normalize_student_key(student_name)
    matches = attendance_df[attendance_df["Name"].astype(str).apply(normalize_student_key) == target_key].copy()
    if matches.empty:
        return empty_metadata

    matches["RollNumber"] = matches["RollNumber"].astype(str).str.strip()
    matches["Class"] = matches["Class"].astype(str).str.strip()
    matches = matches[(matches["RollNumber"] != "") | (matches["Class"] != "")]
    if matches.empty:
        return empty_metadata

    latest_row = matches.iloc[-1]
    return {
        "RollNumber": str(latest_row.get("RollNumber", "") or "").strip(),
        "Class": str(latest_row.get("Class", "") or "").strip(),
    }


def sync_students_from_attendance(attendance_df=None):
    """Ensure every attendance name has a matching dataset folder."""
    attendance_df = read_attendance() if attendance_df is None else attendance_df
    if attendance_df.empty:
        ensure_students_file()
        return []

    seen_names = []
    for name in attendance_df["Name"].dropna().astype(str):
        clean_name = name.strip()
        if not clean_name or not is_valid_attendance_name(clean_name):
            continue
        ensure_student_record(clean_name)
        seen_names.append(clean_name)

    return seen_names


def read_attendance():
    """Return the attendance data as a DataFrame."""
    ensure_attendance_file()
    dataframe = read_csv_or_empty(ATTENDANCE_FILE, ATTENDANCE_COLUMNS)

    for column in ATTENDANCE_COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = ""
    for column in OPTIONAL_ATTENDANCE_COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = ""

    dataframe = dataframe.fillna("")
    return dataframe[OPTIONAL_ATTENDANCE_COLUMNS + ATTENDANCE_COLUMNS]


def has_marked_today(name):
    """Check whether the given person already has attendance for today."""
    df = read_attendance()
    today = datetime.now().strftime("%Y-%m-%d")
    matches = df[(df["Name"] == name) & (df["Date"] == today)]
    return not matches.empty


def mark_attendance(name, status="Present", image_path="", roll_number="", class_name=""):
    """
    Store attendance only once per day for each person.
    Returns True when a new row was added, otherwise False.
    """
    ensure_attendance_file()

    if has_marked_today(name):
        logging.info("Attendance already marked today for %s", name)
        return False

    metadata = get_student_metadata(name)
    roll_value = str(roll_number or metadata["RollNumber"]).strip()
    class_value = str(class_name or metadata["Class"]).strip()
    student_id = roll_value
    now = datetime.now()
    row = {
        "Name": name,
        "StudentId": student_id,
        "CourseId": "general",
        "RollNumber": roll_value,
        "Class": class_value,
        "Date": now.strftime("%Y-%m-%d"),
        "Time": now.strftime("%H:%M:%S"),
        "Status": status,
        "Image": str(image_path or ""),
    }

    attendance_df = read_attendance()
    attendance_df.loc[len(attendance_df)] = row
    write_columns = OPTIONAL_ATTENDANCE_COLUMNS + ATTENDANCE_COLUMNS
    if not write_dataframe_csv(attendance_df, ATTENDANCE_FILE, write_columns):
        return False

    ensure_student_record(name, roll_number=roll_value, class_name=class_value, photo_path=image_path)
    logging.info("Attendance marked for %s", name)
    return True


def get_summary_counts():
    """Return attendance totals per student for the dashboard."""
    df = read_attendance()
    if df.empty:
        return []

    df = df.copy()
    df["Name"] = df["Name"].astype(str).str.strip()
    df = df[df["Name"].apply(is_valid_attendance_name)]
    if df.empty:
        return []

    summary = df.groupby("Name").size().reset_index(name="Count")
    return summary.to_dict(orient="records")


def get_today_count():
    """Return count of unique students who attended today."""
    try:
        attendance_df = read_attendance()
        if attendance_df.empty:
            return 0

        today = datetime.now().strftime("%Y-%m-%d")
        clean_attendance = attendance_df.copy()
        clean_attendance["Name"] = clean_attendance["Name"].astype(str).str.strip()
        clean_attendance["Date"] = clean_attendance["Date"].astype(str).str.strip()
        today_rows = clean_attendance[(clean_attendance["Date"] == today) & (clean_attendance["Name"].apply(is_valid_attendance_name))]

        return int(today_rows["Name"].nunique())
    except Exception:
        logging.exception("Unable to calculate today's attendance count.")
        return 0


def get_overall_percentage():
    """Return overall attendance percentage across all students."""
    try:
        attendance_df = read_attendance()
        if attendance_df.empty:
            return 0.0

        clean_attendance = attendance_df.copy()
        clean_attendance["Name"] = clean_attendance["Name"].astype(str).str.strip()
        clean_attendance["Date"] = clean_attendance["Date"].astype(str).str.strip()
        clean_attendance = clean_attendance[(clean_attendance["Name"].apply(is_valid_attendance_name)) & (clean_attendance["Date"] != "")]
        if clean_attendance.empty:
            return 0.0

        total_days = int(clean_attendance["Date"].nunique())
        total_students = int(clean_attendance["Name"].nunique())
        if total_days == 0 or total_students == 0:
            return 0.0

        days_present = clean_attendance.drop_duplicates(subset=["Name", "Date"]).groupby("Name")["Date"].nunique()
        overall = (int(days_present.sum()) / (total_students * total_days)) * 100
        return round(float(overall), 1)
    except Exception:
        logging.exception("Unable to calculate overall attendance percentage.")
        return 0.0


def get_attendance_percentage_per_student():
    """Return attendance % for each student."""
    try:
        attendance_df = read_attendance()
        if attendance_df.empty:
            return []

        clean_attendance = attendance_df.copy()
        clean_attendance["Name"] = clean_attendance["Name"].astype(str).str.strip()
        clean_attendance["Date"] = clean_attendance["Date"].astype(str).str.strip()
        clean_attendance = clean_attendance[(clean_attendance["Name"].apply(is_valid_attendance_name)) & (clean_attendance["Date"] != "")]
        if clean_attendance.empty:
            return []

        total_days = int(clean_attendance["Date"].nunique())
        if total_days == 0:
            return []

        percentage_df = clean_attendance.drop_duplicates(subset=["Name", "Date"])
        percentage_df = percentage_df.groupby("Name")["Date"].nunique().reset_index(name="DaysPresent")
        percentage_df["TotalDays"] = total_days
        percentage_df["Percentage"] = ((percentage_df["DaysPresent"] / total_days) * 100).round(1)
        percentage_df = percentage_df.sort_values(["Percentage", "DaysPresent", "Name"], ascending=[False, False, True])

        return percentage_df[["Name", "DaysPresent", "TotalDays", "Percentage"]].to_dict(orient="records")
    except Exception:
        logging.exception("Unable to calculate attendance percentage per student.")
        return []


def get_summary_stats():
    """Return high-level attendance analytics for dashboard cards and API responses."""
    attendance_df = read_attendance()
    students_df = read_students()
    percentage_rows = get_attendance_percentage_per_student()

    clean_students = students_df.copy()
    clean_students["Name"] = clean_students["Name"].astype(str).str.strip()
    clean_students = clean_students[clean_students["Name"].apply(is_valid_attendance_name)]

    clean_attendance = attendance_df.copy()
    clean_attendance["Name"] = clean_attendance["Name"].astype(str).str.strip()
    clean_attendance["Date"] = clean_attendance["Date"].astype(str).str.strip()
    clean_attendance = clean_attendance[(clean_attendance["Name"].apply(is_valid_attendance_name)) & (clean_attendance["Date"] != "")]

    total_students = int(len(clean_students))
    total_records = int(len(clean_attendance))
    today_attendance_count = get_today_count()
    return {
        "total_students": total_students,
        "total_attendance_records": total_records,
        "today_attendance_count": today_attendance_count,
        "overall_attendance_percentage": get_overall_percentage(),
        "defaulters_count": len([row for row in percentage_rows if float(row["Percentage"]) < 75]),
    }


def get_daily_trend():
    """Return number of unique students present per day."""
    try:
        attendance_df = read_attendance()
        if attendance_df.empty:
            return []

        clean_attendance = attendance_df.copy()
        clean_attendance["Name"] = clean_attendance["Name"].astype(str).str.strip()
        clean_attendance["Date"] = clean_attendance["Date"].astype(str).str.strip()
        clean_attendance = clean_attendance[(clean_attendance["Name"].apply(is_valid_attendance_name)) & (clean_attendance["Date"] != "")]
        if clean_attendance.empty:
            return []

        trend_df = clean_attendance.drop_duplicates(subset=["Name", "Date"])
        trend_df = trend_df.groupby("Date")["Name"].nunique().reset_index(name="Count")
        trend_df = trend_df.sort_values("Date").reset_index(drop=True)

        return trend_df[["Date", "Count"]].to_dict(orient="records")
    except Exception:
        logging.exception("Unable to calculate daily trend.")
        return []


def get_defaulters(threshold=75):
    """Return students with attendance below threshold %."""
    try:
        threshold_value = float(threshold)
    except (TypeError, ValueError):
        threshold_value = 75.0

    percentage_rows = get_attendance_percentage_per_student()
    return [
        {"Name": row["Name"], "Percentage": row["Percentage"]}
        for row in percentage_rows
        if float(row["Percentage"]) < threshold_value
    ]


def get_defaulters_list(threshold=75):
    """Return students below the threshold using the older helper name."""
    return get_defaulters(threshold=threshold)


def get_top_attenders(top_n=5, threshold=75):
    """Return top students who meet the attendance threshold."""
    try:
        limit = int(top_n)
    except (TypeError, ValueError):
        limit = 5
    try:
        threshold_value = float(threshold)
    except (TypeError, ValueError):
        threshold_value = 75.0

    percentage_rows = get_attendance_percentage_per_student()
    eligible_rows = [
        row for row in percentage_rows
        if float(row["Percentage"]) >= threshold_value
    ]
    return [{"Name": row["Name"], "Percentage": row["Percentage"]} for row in eligible_rows[:limit]]


def normalize_attendance_dataframe(dataframe):
    """Validate and normalize imported attendance data."""
    required_columns = ["Name", "Date", "Time", "Status"]
    normalized = dataframe.copy()

    normalized.columns = [str(column).strip() for column in normalized.columns]
    missing = [column for column in required_columns if column not in normalized.columns]
    if missing:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(missing)
            + ". Expected columns are Name, Date, Time, Status."
        )

    if "Image" not in normalized.columns:
        normalized["Image"] = ""
    if "StudentId" not in normalized.columns:
        normalized["StudentId"] = ""
    if "CourseId" not in normalized.columns:
        normalized["CourseId"] = "general"
    if "RollNumber" not in normalized.columns:
        normalized["RollNumber"] = ""
    if "Class" not in normalized.columns:
        normalized["Class"] = ""

    normalized = normalized[OPTIONAL_ATTENDANCE_COLUMNS + ATTENDANCE_COLUMNS].copy()
    normalized["Name"] = normalized["Name"].astype(str).str.strip()
    normalized["StudentId"] = normalized["StudentId"].fillna("").astype(str).str.strip()
    normalized["CourseId"] = normalized["CourseId"].fillna("general").astype(str).str.strip().replace("", "general")
    normalized["RollNumber"] = normalized["RollNumber"].fillna("").astype(str).str.strip()
    normalized["Class"] = normalized["Class"].fillna("").astype(str).str.strip()
    normalized["Date"] = pd.to_datetime(normalized["Date"], errors="coerce").dt.strftime("%Y-%m-%d")

    time_values = pd.to_datetime(normalized["Time"].astype(str), errors="coerce")
    fallback_time_values = pd.to_datetime(normalized["Time"].astype(str), format="%H:%M:%S", errors="coerce")
    normalized["Time"] = time_values.fillna(fallback_time_values).dt.strftime("%H:%M:%S")

    normalized["Status"] = normalized["Status"].astype(str).str.strip().replace("", "Present")
    normalized["Image"] = normalized["Image"].fillna("").astype(str).str.strip()
    normalized = normalized.dropna(subset=["Name", "Date", "Time", "Status"])
    normalized = normalized[normalized["Name"] != ""]

    if normalized.empty:
        raise ValueError("The uploaded file does not contain any valid attendance rows.")

    return normalized


def import_attendance_file(file_stream, filename):
    """
    Import attendance from CSV or Excel and merge with the existing CSV.
    Duplicate rows are removed based on Name, Date, Time, and Status.
    """
    ensure_attendance_file()

    extension = Path(filename).suffix.lower()
    if extension == ".csv":
        imported_df = pd.read_csv(file_stream)
    elif extension in {".xlsx", ".xls"}:
        try:
            imported_df = pd.read_excel(file_stream)
        except ImportError as error:
            raise RuntimeError(
                "Excel import requires the openpyxl package. Install it with: pip install openpyxl"
            ) from error
    else:
        raise ValueError("Unsupported file type. Please upload a CSV, XLSX, or XLS file.")

    imported_df = normalize_attendance_dataframe(imported_df)
    existing_df = read_attendance()

    if existing_df.empty:
        combined_df = imported_df.copy()
    else:
        existing_df = normalize_attendance_dataframe(existing_df)
        combined_df = pd.concat([existing_df, imported_df], ignore_index=True)

    before_count = len(combined_df)
    combined_df = combined_df.drop_duplicates(subset=["Name", "Date", "Time", "Status"], keep="first")
    after_count = len(combined_df)
    imported_count = len(imported_df)
    added_count = after_count - (0 if existing_df.empty else len(existing_df.drop_duplicates(subset=["Name", "Date", "Time", "Status"], keep="first")))

    write_columns = OPTIONAL_ATTENDANCE_COLUMNS + ATTENDANCE_COLUMNS
    if not write_dataframe_csv(combined_df, ATTENDANCE_FILE, write_columns):
        raise PermissionError(f"Unable to write attendance data to {ATTENDANCE_FILE}")
    sync_students_from_attendance(combined_df)
    logging.info("Imported %s attendance rows from %s", imported_count, filename)

    return {
        "imported_rows": imported_count,
        "added_rows": max(added_count, 0),
        "skipped_rows": max(before_count - after_count, 0),
    }
