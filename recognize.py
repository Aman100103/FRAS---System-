from utils.face_utils import recognize_faces


def start_attendance(camera_source=0):
    """Start the real-time attendance session."""
    recognize_faces(camera_source=camera_source, mark_attendance_enabled=True, save_unknown=True)


if __name__ == "__main__":
    entered_source = input("Enter webcam index or IP camera URL (press Enter for default webcam): ").strip()
    source = entered_source if entered_source else 0
    start_attendance(source)

