import threading
import webbrowser
from tkinter import Canvas, StringVar, Tk, messagebox
from tkinter import ttk

from app import start_dashboard
from recognize import start_attendance
from register import register_face
from voice import start_jarvis


class AttendanceGUI:
    """Desktop control panel for the attendance system."""

    def __init__(self, root):
        self.root = root
        self.root.title("AI Facial Recognition Attendance System")
        self.root.geometry("900x640")
        self.root.minsize(820, 600)
        self.root.configure(bg="#0f4f4c")
        self.root.resizable(True, True)

        self.dashboard_started = False
        self.camera_source = StringVar(value="0")
        self.person_name = StringVar()
        self.roll_number = StringVar()
        self.class_name = StringVar()
        self.background_canvas = None

        self.configure_styles()
        self.build_layout()
        self.root.bind("<Configure>", self.handle_resize)

    def configure_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Hero.TFrame", background="#296863")
        style.configure("Card.TFrame", background="#f8fafc")
        style.configure("Header.TLabel", background="#1d766f", foreground="#ffffff", font=("Segoe UI", 24, "bold"))
        style.configure("SubHeader.TLabel", background="#1d766f", foreground="#d6f3ee", font=("Segoe UI", 11))
        style.configure("CardTitle.TLabel", background="#f8fafc", foreground="#1e293b", font=("Segoe UI", 16, "bold"))
        style.configure("Body.TLabel", background="#f8fafc", foreground="#475569", font=("Segoe UI", 10))
        style.configure(
            "TButton",
            font=("Segoe UI", 11, "bold"),
            padding=10,
            background="#1a8f86",
            foreground="#ffffff",
            borderwidth=0,
        )
        style.map(
            "TButton",
            background=[("active", "#23a094"), ("pressed", "#136f68")],
            foreground=[("active", "#ffffff"), ("pressed", "#ffffff")],
        )
        style.configure(
            "TEntry",
            padding=8,
            fieldbackground="#ffffff",
            foreground="#1e293b",
            bordercolor="#bfd5df",
            lightcolor="#bfd5df",
            darkcolor="#bfd5df",
        )

    def build_layout(self):
        self.background_canvas = Canvas(self.root, highlightthickness=0, borderwidth=0)
        self.background_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.draw_gradient_background(900, 640)

        title_frame = ttk.Frame(self.root, style="Hero.TFrame", padding=(18, 14))
        title_frame.place(relx=0.5, rely=0.14, anchor="center", relwidth=0.92, height=110)

        ttk.Label(title_frame, text="AI Facial Recognition Attendance", style="Header.TLabel").pack(pady=(0, 4))
        ttk.Label(
            title_frame,
            text="Real-time face recognition, attendance marking, dashboard analytics, and Jarvis voice control",
            style="SubHeader.TLabel",
            wraplength=720,
            justify="center",
        ).pack()

        container = ttk.Frame(self.root, style="Card.TFrame", padding=24)
        container.place(relx=0.5, rely=0.62, anchor="center", relwidth=0.88, height=430)

        ttk.Label(container, text="Control Center", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 16))

        ttk.Label(container, text="Person Name", style="Body.TLabel").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(container, textvariable=self.person_name, width=36).grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(container, text="Roll Number", style="Body.TLabel").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Entry(container, textvariable=self.roll_number, width=36).grid(row=2, column=1, sticky="ew", pady=6)

        ttk.Label(container, text="Class", style="Body.TLabel").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Entry(container, textvariable=self.class_name, width=36).grid(row=3, column=1, sticky="ew", pady=6)

        ttk.Label(container, text="Camera Source", style="Body.TLabel").grid(row=4, column=0, sticky="w", pady=6)
        ttk.Entry(container, textvariable=self.camera_source, width=36).grid(row=4, column=1, sticky="ew", pady=6)

        note_text = "Use 0 for laptop webcam, 1 for external webcam, or paste an IP Webcam URL from your phone."
        ttk.Label(container, text=note_text, style="Body.TLabel", wraplength=520).grid(row=5, column=0, columnspan=2, sticky="w", pady=(2, 18))

        ttk.Button(container, text="Register Face", command=self.handle_register).grid(row=6, column=0, sticky="ew", pady=8, padx=(0, 10))
        ttk.Button(container, text="Start Attendance", command=self.handle_attendance).grid(row=6, column=1, sticky="ew", pady=8)
        ttk.Button(container, text="Open Dashboard", command=self.handle_dashboard).grid(row=7, column=0, sticky="ew", pady=8, padx=(0, 10))
        ttk.Button(container, text="Start Jarvis Voice", command=self.handle_voice).grid(row=7, column=1, sticky="ew", pady=8)

        ttk.Label(
            container,
            text="Tip: keep your face centered and well-lit during registration for better recognition accuracy.",
            style="Body.TLabel",
            wraplength=520,
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(18, 0))

        container.columnconfigure(1, weight=1)

    def draw_gradient_background(self, width, height):
        if self.background_canvas is None or width < 2 or height < 2:
            return

        self.background_canvas.delete("all")

        top_color = (10, 55, 57)
        upper_mid_color = (18, 102, 99)
        lower_mid_color = (78, 146, 156)
        bottom_color = (174, 215, 214)

        for y in range(height):
            progress = y / max(height - 1, 1)
            if progress < 0.4:
                blend = progress / 0.4
                red = int(top_color[0] + (upper_mid_color[0] - top_color[0]) * blend)
                green = int(top_color[1] + (upper_mid_color[1] - top_color[1]) * blend)
                blue = int(top_color[2] + (upper_mid_color[2] - top_color[2]) * blend)
            elif progress < 0.78:
                blend = (progress - 0.4) / 0.38
                red = int(upper_mid_color[0] + (lower_mid_color[0] - upper_mid_color[0]) * blend)
                green = int(upper_mid_color[1] + (lower_mid_color[1] - upper_mid_color[1]) * blend)
                blue = int(upper_mid_color[2] + (lower_mid_color[2] - upper_mid_color[2]) * blend)
            else:
                blend = (progress - 0.78) / 0.22
                red = int(lower_mid_color[0] + (bottom_color[0] - lower_mid_color[0]) * blend)
                green = int(lower_mid_color[1] + (bottom_color[1] - lower_mid_color[1]) * blend)
                blue = int(lower_mid_color[2] + (bottom_color[2] - lower_mid_color[2]) * blend)

            color = f"#{red:02x}{green:02x}{blue:02x}"
            self.background_canvas.create_line(0, y, width, y, fill=color)

        self.background_canvas.create_oval(-140, 40, 210, 330, fill="#1d766f", outline="", stipple="gray50")
        self.background_canvas.create_oval(520, -30, 860, 220, fill="#5aa5b2", outline="", stipple="gray50")
        self.background_canvas.create_oval(540, 250, 940, 580, fill="#bfe8e1", outline="", stipple="gray50")
        self.background_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.background_canvas.tk.call("lower", self.background_canvas._w)

    def handle_resize(self, event):
        if event.widget is self.root:
            self.draw_gradient_background(event.width, event.height)

    def get_source(self):
        source = self.camera_source.get().strip()
        return source if source else 0

    def handle_register(self):
        name = self.person_name.get().strip()
        if not name:
            messagebox.showerror("Missing Name", "Please enter a name before registration.")
            return

        try:
            result = register_face(
                name=name,
                camera_source=self.get_source(),
                roll_number=self.roll_number.get().strip(),
                class_name=self.class_name.get().strip(),
            )
            if result["success"]:
                messagebox.showinfo("Registration Complete", result["message"])
            else:
                messagebox.showwarning("Registration Incomplete", result["message"])
        except Exception as error:
            messagebox.showerror("Registration Error", str(error))

    def handle_attendance(self):
        try:
            start_attendance(camera_source=self.get_source())
        except Exception as error:
            messagebox.showerror("Attendance Error", str(error))

    def handle_dashboard(self):
        if not self.dashboard_started:
            threading.Thread(
                target=start_dashboard,
                kwargs={"host": "127.0.0.1", "port": 5000, "debug": False, "open_browser": False},
                daemon=True,
            ).start()
            self.dashboard_started = True

        webbrowser.open("http://127.0.0.1:5000")

    def handle_voice(self):
        threading.Thread(
            target=start_jarvis,
            kwargs={"camera_source": self.get_source(), "dashboard_url": "http://127.0.0.1:5000"},
            daemon=True,
        ).start()
        messagebox.showinfo("Jarvis", "Jarvis voice assistant started in the background.")


def run_gui():
    root = Tk()
    AttendanceGUI(root)
    root.mainloop()


if __name__ == "__main__":
    run_gui()
