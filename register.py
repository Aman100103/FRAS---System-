from utils.face_utils import register_face_from_camera


def register_face(name, camera_source=0, samples=10, roll_number="", class_name=""):
    """Register a new face and return the result for other modules."""
    return register_face_from_camera(
        name=name,
        camera_source=camera_source,
        samples=samples,
        roll_number=roll_number,
        class_name=class_name,
    )


if __name__ == "__main__":
    entered_name = input("Enter the person's name: ").strip()
    entered_roll_number = input("Enter roll number (optional): ").strip()
    entered_class = input("Enter class (optional): ").strip()
    entered_source = input("Enter webcam index or IP camera URL (press Enter for default webcam): ").strip()
    source = entered_source if entered_source else 0

    result = register_face(entered_name, source, roll_number=entered_roll_number, class_name=entered_class)
    print(result["message"])
