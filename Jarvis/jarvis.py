import threading
import pyttsx3
import datetime
import speech_recognition as sr
import wikipedia
import webbrowser as wb
import os
import random
import pyautogui
import pyjokes
import customtkinter as ctk

# Configure UI
ctk.set_appearance_mode("Dark")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

class JarvisApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Jarvis AI Assistant")
        self.geometry("600x550")
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # Header
        self.header_label = ctk.CTkLabel(self, text="Jarvis - Voice Assistant", font=ctk.CTkFont(size=26, weight="bold"))
        self.header_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        # Log textbox
        self.log_box = ctk.CTkTextbox(self, width=500, height=350, font=ctk.CTkFont(size=14))
        self.log_box.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        self.log_box.configure(state="disabled")
        
        # Status Label
        self.status_label = ctk.CTkLabel(self, text="Status: Offline", font=ctk.CTkFont(size=14), text_color="gray")
        self.status_label.grid(row=2, column=0, padx=20, pady=5)
        
        # Buttons Frame
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.grid(row=3, column=0, padx=20, pady=(10, 20))
        
        self.start_btn = ctk.CTkButton(self.btn_frame, text="Start Listening", command=self.start_assistant, fg_color="#1F6AA5", font=ctk.CTkFont(size=14, weight="bold"))
        self.start_btn.grid(row=0, column=0, padx=10)
        
        self.stop_btn = ctk.CTkButton(self.btn_frame, text="Exit", command=self.stop_app, fg_color="#C62828", hover_color="#B71C1C", font=ctk.CTkFont(size=14, weight="bold"))
        self.stop_btn.grid(row=0, column=1, padx=10)
        
        # Engine setup
        self.engine = pyttsx3.init()
        voices = self.engine.getProperty('voices')
        self.engine.setProperty('voice', voices[1].id if len(voices) > 1 else voices[0].id)  
        self.engine.setProperty('rate', 150)
        self.engine.setProperty('volume', 1)
        
        self.is_running = False
        self.assistant_thread = None

    def log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        
    def speak(self, audio):
        self.log(f"🤖 Jarvis: {audio}")
        self.engine.say(audio)
        self.engine.runAndWait()

    def update_status(self, text, color="white"):
        self.status_label.configure(text=f"Status: {text}", text_color=color)

    def time(self):
        current_time = datetime.datetime.now().strftime("%I:%M:%S %p")
        self.speak(f"The current time is {current_time}")

    def date(self):
        now = datetime.datetime.now()
        self.speak(f"The current date is {now.day} {now.strftime('%B')} {now.year}")

    def wishme(self):
        hour = datetime.datetime.now().hour
        if 4 <= hour < 12:
            self.speak("Good morning!")
        elif 12 <= hour < 16:
            self.speak("Good afternoon!")
        elif 16 <= hour < 24:
            self.speak("Good evening!")
        else:
            self.speak("Good night, see you tomorrow.")
            
        self.speak("Jarvis at your service. Please tell me how may I assist you.")

    def screenshot(self):
        img = pyautogui.screenshot()
        img_path = os.path.expanduser("~\\Pictures\\screenshot.png")
        img.save(img_path)
        self.speak(f"Screenshot saved at your Pictures folder.")

    def takecommand(self):
        r = sr.Recognizer()
        with sr.Microphone() as source:
            self.update_status("Listening...", "#4CAF50")
            r.pause_threshold = 1
            try:
                audio = r.listen(source, timeout=5)
            except sr.WaitTimeoutError:
                self.update_status("Idle", "gray")
                return None

        try:
            self.update_status("Recognizing...", "#FFC107")
            query = r.recognize_google(audio, language="en-in")
            self.log(f"👤 You: {query}")
            return query.lower()
        except sr.UnknownValueError:
            self.update_status("Idle", "gray")
            return None
        except Exception as e:
            self.log(f"Error: {e}")
            self.update_status("Error", "red")
            return None

    def assistant_loop(self):
        self.is_running = True
        self.wishme()
        
        while self.is_running:
            self.update_status("Idle", "gray")
            query = self.takecommand()
            
            if not query:
                continue

            if "time" in query:
                self.time()
            elif "date" in query:
                self.date()
            elif "wikipedia" in query:
                query = query.replace("wikipedia", "").strip()
                try:
                    self.speak("Searching Wikipedia...")
                    result = wikipedia.summary(query, sentences=2)
                    self.speak(result)
                except:
                    self.speak("I couldn't find anything on Wikipedia.")
            elif "play music" in query:
                song_dir = os.path.expanduser("~\\Music")
                if os.path.exists(song_dir):
                    songs = [s for s in os.listdir(song_dir) if s.endswith((".mp3", ".wav"))]
                    if songs:
                        os.startfile(os.path.join(song_dir, random.choice(songs)))
                        self.speak("Playing music.")
                    else:
                        self.speak("No music files found in your Music folder.")
                else:
                    self.speak("Music folder not found.")
            elif "open youtube" in query:
                wb.open("youtube.com")
                self.speak("Opening YouTube")
            elif "open google" in query:
                wb.open("google.com")
                self.speak("Opening Google")
            elif "screenshot" in query:
                self.screenshot()
            elif "tell me a joke" in query:
                joke = pyjokes.get_joke()
                self.speak(joke)
            elif "shutdown" in query:
                self.speak("Shutting down the system, goodbye!")
                os.system("shutdown /s /f /t 1")
                self.is_running = False
                self.after(1000, self.destroy)
                break
            elif "restart" in query:
                self.speak("Restarting the system, please wait!")
                os.system("shutdown /r /f /t 1")
                self.is_running = False
                self.after(1000, self.destroy)
                break
            elif "offline" in query or "exit" in query:
                self.speak("Going offline. Have a good day!")
                self.is_running = False
                self.after(1000, self.destroy)
                break
                
    def start_assistant(self):
        if not self.is_running:
            self.start_btn.configure(state="disabled", text="Listening...")
            self.assistant_thread = threading.Thread(target=self.assistant_loop, daemon=True)
            self.assistant_thread.start()
            
    def stop_app(self):
        self.is_running = False
        self.destroy()

if __name__ == "__main__":
    app = JarvisApp()
    app.mainloop()
