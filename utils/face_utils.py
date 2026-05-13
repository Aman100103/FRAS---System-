import logging
import pickle
import re
import time
from datetime import datetime
from pathlib import Path

import cv2
import face_recognition
import numpy as np

from utils.attendance_utils import (
    ensure_student_folder,
    ensure_student_record,
    has_marked_today,
    mark_attendance,
    setup_logging,
)


BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = BASE_DIR / "dataset"
UNKNOWN_DIR = DATASET_DIR / "unknown"
ATTENDANCE_IMAGE_DIR = BASE_DIR / "attendance_images"
ENCODINGS_FILE = BASE_DIR / "encodings.pkl"


setup_logging()


def sanitize_name(name):
    """Convert names into a file-safe format while keeping them readable."""
    cleaned = re.sub(r"[^a-zA-Z0-9 _-]", "", name).strip()
    return cleaned.replace(" ", "_")


def ensure_project_dirs():
    """Create required directories used by the application."""
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    UNKNOWN_DIR.mkdir(parents=True, exist_ok=True)
    ATTENDANCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)


def get_camera_source(camera_source):
    """
    Accept webcam index or IP webcam URL.
    Numeric values are converted to integers for local webcams.
    """
    if camera_source is None:
        return 0

    if isinstance(camera_source, int):
        return camera_source

    text_source = str(camera_source).strip()
    if text_source.isdigit():
        return int(text_source)
    return text_source


def open_camera(camera_source=0):
    """Open a camera and raise a helpful error when it fails."""
    source = get_camera_source(camera_source)
    camera = cv2.VideoCapture(source)

    if not camera.isOpened():
        raise RuntimeError(
            f"Unable to access camera source: {source}. "
            "Check the webcam connection or verify the IP camera URL."
        )

    return camera


def load_encodings():
    """Load saved face encodings and names from disk."""
    ensure_project_dirs()

    if not ENCODINGS_FILE.exists():
        return {"encodings": [], "names": []}

    try:
        with ENCODINGS_FILE.open("rb") as file:
            data = pickle.load(file)
    except (EOFError, pickle.PickleError):
        data = {"encodings": [], "names": []}

    data.setdefault("encodings", [])
    data.setdefault("names", [])
    return data


def save_encodings(data):
    """Persist face encodings to the project file."""
    ensure_project_dirs()
    with ENCODINGS_FILE.open("wb") as file:
        pickle.dump(data, file)


def save_unknown_face(frame, face_location=None):
    """Store unknown faces for later review."""
    ensure_project_dirs()
    filename = UNKNOWN_DIR / f"unknown_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"

    image_to_save = frame
    if face_location is not None:
        top, right, bottom, left = face_location
        height, width = frame.shape[:2]
        top = max(0, top)
        right = min(width, right)
        bottom = min(height, bottom)
        left = max(0, left)
        if bottom > top and right > left:
            image_to_save = frame[top:bottom, left:right]

    cv2.imwrite(str(filename), image_to_save)
    logging.info("Unknown face saved: %s", filename.name)
    return filename


def save_attendance_face(frame, name, face_location=None):
    """Save a cropped face image for a recognized attendance event."""
    ensure_project_dirs()
    safe_name = sanitize_name(name)
    filename = ATTENDANCE_IMAGE_DIR / f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"

    image_to_save = frame
    if face_location is not None:
        top, right, bottom, left = face_location
        height, width = frame.shape[:2]
        top = max(0, top)
        right = min(width, right)
        bottom = min(height, bottom)
        left = max(0, left)
        if bottom > top and right > left:
            image_to_save = frame[top:bottom, left:right]

    cv2.imwrite(str(filename), image_to_save)
    logging.info("Attendance image saved: %s", filename.name)
    return filename.relative_to(BASE_DIR).as_posix()


def distance_to_confidence(distance, threshold=0.5):
    """Convert face distance into a simple percentage for the live overlay."""
    normalized_distance = max(0.0, min(1.0, float(distance)))
    confidence = max(0.0, min(1.0, 1 - (normalized_distance / max(threshold, 1e-6))))
    return int(round(confidence * 100))


def register_face_from_camera(name, camera_source=0, samples=10, roll_number="", class_name=""):
    """
    Capture multiple frames for one person and save their encodings.
    Returns a dictionary describing the registration result.
    """
    ensure_project_dirs()

    if not name or not name.strip():
        raise ValueError("Name cannot be empty.")

    display_name = name.strip().title()
    safe_name = sanitize_name(display_name)
    person_dir = ensure_student_folder(display_name)

    known_data = load_encodings()
    new_encodings = []

    camera = open_camera(camera_source)
    captured = 0
    frame_count = 0

    try:
        while captured < samples:
            success, frame = camera.read()
            if not success:
                raise RuntimeError("Camera frame could not be read during registration.")

            frame_count += 1
            display_frame = frame.copy()

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_frame)

            for top, right, bottom, left in face_locations:
                cv2.rectangle(display_frame, (left, top), (right, bottom), (0, 200, 0), 2)

            message = f"Registering {safe_name}: {captured}/{samples} images | Press Q to stop"
            cv2.putText(
                display_frame,
                message,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
            )
            cv2.imshow("Face Registration", display_frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

            if frame_count % 8 != 0:
                continue

            if len(face_locations) != 1:
                continue

            face_encoding = face_recognition.face_encodings(rgb_frame, face_locations)
            if not face_encoding:
                continue

            captured += 1
            new_encodings.append(face_encoding[0])
            image_path = person_dir / f"{safe_name}_{captured}.jpg"
            cv2.imwrite(str(image_path), frame)
            time.sleep(0.2)

        if not new_encodings:
            logging.warning("No face encodings captured for %s", safe_name)
            return {
                "success": False,
                "message": "No clear single-face images were captured. Please try again.",
                "captured": 0,
            }

        known_data["encodings"].extend(new_encodings)
        known_data["names"].extend([display_name] * len(new_encodings))
        save_encodings(known_data)
        ensure_student_record(
            display_name,
            roll_number=roll_number,
            class_name=class_name,
            photo_path=(person_dir / f"{safe_name}_1.jpg").relative_to(BASE_DIR).as_posix(),
        )

        logging.info("Registered %s with %s samples", display_name, len(new_encodings))
        return {
            "success": True,
            "message": f"{display_name} registered with {len(new_encodings)} face samples.",
            "captured": len(new_encodings),
        }

    finally:
        camera.release()
        cv2.destroyAllWindows()


def recognize_faces(camera_source=0, mark_attendance_enabled=True, save_unknown=True):
    """
    Run live recognition from webcam or IP camera.
    Press Q in the OpenCV window to stop the attendance session.
    """
    known_data = load_encodings()
    known_encodings = known_data["encodings"]
    known_names = known_data["names"]

    if not known_encodings:
        raise RuntimeError("No face encodings found. Please register at least one face first.")

    camera = open_camera(camera_source)
    last_unknown_save = 0
    required_confirmation_frames = 3
    recognition_streaks = {}
    attendance_session_status = {}

    try:
        while True:
            success, frame = camera.read()
            if not success:
                raise RuntimeError("Camera frame could not be read during recognition.")

            small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            face_locations = face_recognition.face_locations(rgb_small_frame)
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)
            detected_known_names = set()

            for face_encoding, face_location in zip(face_encodings, face_locations):
                matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.5)
                face_distances = face_recognition.face_distance(known_encodings, face_encoding)

                name = "Unknown"
                confidence_label = ""
                status_text = "Unknown face"
                if len(face_distances) > 0:
                    best_match_index = int(np.argmin(face_distances))
                    confidence_label = f"{distance_to_confidence(face_distances[best_match_index])}%"
                    if matches[best_match_index]:
                        name = known_names[best_match_index]
                        detected_known_names.add(name)
                        recognition_streaks[name] = recognition_streaks.get(name, 0) + 1
                        confirmed = recognition_streaks[name] >= required_confirmation_frames

                        if confirmed:
                            if mark_attendance_enabled and name not in attendance_session_status:
                                image_path = ""
                                if not has_marked_today(name):
                                    image_path = save_attendance_face(frame, name, (top, right, bottom, left))
                                was_marked = mark_attendance(name, image_path=image_path)
                                attendance_session_status[name] = "Attendance Marked" if was_marked else "Already Marked Today"

                            status_text = attendance_session_status.get(name, "Verified")
                        else:
                            status_text = f"Verifying {recognition_streaks[name]}/{required_confirmation_frames}"

                top, right, bottom, left = [value * 4 for value in face_location]
                color = (0, 200, 0) if name != "Unknown" else (0, 0, 255)
                cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                cv2.rectangle(frame, (left, bottom - 55), (right, bottom), color, cv2.FILLED)
                cv2.putText(
                    frame,
                    f"{name} {f'({confidence_label})' if confidence_label else ''}".strip(),
                    (left + 6, bottom - 28),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    2,
                )
                cv2.putText(
                    frame,
                    status_text,
                    (left + 6, bottom - 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    1,
                )

                if name == "Unknown" and save_unknown:
                    current_time = time.time()
                    if current_time - last_unknown_save > 5:
                        save_unknown_face(frame, (top, right, bottom, left))
                        last_unknown_save = current_time

            stale_names = [name for name in recognition_streaks if name not in detected_known_names]
            for stale_name in stale_names:
                recognition_streaks.pop(stale_name, None)

            cv2.putText(
                frame,
                f"Attendance running | Stable match: {required_confirmation_frames} frames | Press Q to quit",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 255, 255),
                2,
            )
            cv2.imshow("AI Facial Recognition Attendance", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    finally:
        camera.release()
        cv2.destroyAllWindows()
