import threading
import webbrowser

import pyttsx3
import speech_recognition as sr

from app import start_dashboard
from recognize import start_attendance
from register import register_face


engine = None


def get_engine():
    """Initialize the speech engine only when voice features are used."""
    global engine
    if engine is None:
        try:
            engine = pyttsx3.init()
        except Exception as error:
            raise RuntimeError(
                "Text-to-speech is unavailable on this system. "
                "The GUI can still be used without Jarvis voice control."
            ) from error
    return engine


def speak(text):
    """Speak text aloud using pyttsx3."""
    speech_engine = get_engine()
    speech_engine.say(text)
    speech_engine.runAndWait()


def listen(recognizer, microphone):
    """Capture speech and convert it into text."""
    with microphone as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        audio = recognizer.listen(source)

    try:
        return recognizer.recognize_google(audio).lower()
    except sr.UnknownValueError:
        return ""
    except sr.RequestError:
        speak("Speech service is not available right now.")
        return ""


def ask_name(recognizer, microphone):
    """Ask the user for a name during voice-based registration."""
    speak("Please say the name to register.")
    name = listen(recognizer, microphone)
    return name.strip().title()


def start_jarvis(camera_source=0, dashboard_url="http://127.0.0.1:5000"):
    """
    Voice assistant loop.
    Supported commands:
    - start attendance
    - register face
    - open dashboard
    - exit
    """
    recognizer = sr.Recognizer()
    microphone = sr.Microphone()
    dashboard_started = False

    speak("Jarvis voice assistant activated.")

    while True:
        speak("Waiting for your command.")
        command = listen(recognizer, microphone)

        if not command:
            speak("I did not catch that.")
            continue

        if "start attendance" in command:
            speak("Starting attendance system.")
            start_attendance(camera_source)

        elif "register face" in command:
            name = ask_name(recognizer, microphone)
            if not name:
                speak("I could not understand the name.")
                continue

            speak(f"Registering {name}. Please look at the camera.")
            result = register_face(name, camera_source)
            speak(result["message"])

        elif "open dashboard" in command:
            speak("Opening dashboard.")
            if not dashboard_started:
                threading.Thread(
                    target=start_dashboard,
                    kwargs={"host": "127.0.0.1", "port": 5000, "debug": False, "open_browser": False},
                    daemon=True,
                ).start()
                dashboard_started = True
            webbrowser.open(dashboard_url)

        elif "exit" in command:
            speak("Goodbye.")
            break

        else:
            speak("Command not recognized. Please try again.")


if __name__ == "__main__":
    source = input("Enter webcam index or IP camera URL (press Enter for default webcam): ").strip()
    camera_source = source if source else 0
    start_jarvis(camera_source=camera_source)
