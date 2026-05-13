# AI Facial Recognition Attendance System

A desktop and web-based attendance management system using facial recognition, webcam registration, live attendance marking, dashboard analytics, and optional voice control.

## Project Overview

This project captures and recognizes student faces to mark attendance automatically. It provides:

- Face registration through webcam or IP camera
- Live attendance capture with OpenCV and face recognition
- A Flask dashboard for attendance analytics and student profiles
- A Tkinter GUI control panel
- Optional Jarvis voice assistant commands
- Notification support for low attendance thresholds

## Key Features

- Register students using the camera
- Save face encodings and profile data in `dataset/`
- Automatically mark attendance in `attendance.csv`
- Store captured attendance face images in `attendance_images/`
- Support for unknown face saving under `dataset/unknown/`
- View analytics using a browser dashboard
- Send email/SMS alerts using `.env` configuration

## Repository Structure

- `app.py` - Flask dashboard server and analytics APIs
- `gui.py` - Tkinter desktop control panel
- `register.py` - Command-line face registration helper
- `recognize.py` - Command-line attendance capture helper
- `voice.py` - Speech assistant for basic voice commands
- `utils/` - Helper modules for face processing, attendance storage, and notifications
- `dataset/` - Stored student face folders and profiles
- `attendance.csv` - Attendance log
- `students.csv` - Student registry
- `notifications.csv` - Notification history
- `templates/` - Flask HTML templates

## Setup

### Prerequisites

- Python 3.8+ recommended
- Windows with webcam support
- Camera drivers installed
- Optionally, a virtual environment

### Install dependencies

The project does not include a locked requirements file, but the core dependencies are:

- Flask
- pandas
- opencv-python
- face_recognition
- numpy
- pyttsx3
- SpeechRecognition

Install dependencies manually or in a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install flask pandas opencv-python face-recognition numpy pyttsx3 SpeechRecognition
```

> Note: `face_recognition` depends on `dlib`, which may require additional build tools on Windows.

### Optional notification setup

Copy `.env.example` to `.env` and configure your alert settings if you want email or SMS notifications:

```powershell
copy .env.example .env
```

Configure values such as `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and Twilio settings.

## Usage

### Run the desktop GUI

```powershell
python gui.py
```

Use the GUI to:

- Register Face
- Start Attendance
- Open Dashboard
- Start Jarvis Voice

### Register a new student by CLI

```powershell
python register.py
```

Enter the student name, roll number, class, and camera source when prompted.

### Start live attendance by CLI

```powershell
python recognize.py
```

Press `q` in the OpenCV window to stop the attendance session.

### Open the dashboard

The dashboard runs on:

```
http://127.0.0.1:5000
```

The dashboard shows attendance metrics, student profiles, and analytics.

### Start Jarvis voice assistant

```powershell
python voice.py
```

Supported voice commands include:

- "start attendance"
- "register face"
- "open dashboard"
- "exit"

## Data files and folders

- `attendance.csv` - main attendance log
- `students.csv` - student registry and profile metadata
- `dataset/` - per-student folders containing face images and `profile.csv`
- `dataset/unknown/` - captured unknown faces
- `attendance_images/` - saved attendance face captures
- `system.log` - application logs
- `notifications.csv` - notification delivery history

## Notes

- For reliable recognition, register students with well-lit, centered face images.
- Use webcam index `0` for the default integrated camera or `1`/`2` for additional cameras.
- IP camera URLs may be used as the camera source when supported.

## License

This repository does not include a license file. Add one if you want to clarify reuse rules.
