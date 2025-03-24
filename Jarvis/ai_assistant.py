import os
import threading
import speech_recognition as sr
import pyttsx3
from datetime import datetime
from deep_translator import GoogleTranslator
from PyQt6.QtWidgets import (QApplication, QWidget, QTextBrowser, QVBoxLayout, 
                          QLineEdit, QPushButton, QHBoxLayout, QLabel, 
                          QFrame, QGraphicsDropShadowEffect, QSizePolicy,
                          QScrollArea, QTextEdit)
from PyQt6.QtCore import (QThread, pyqtSignal, Qt, QPropertyAnimation, 
                       QEasingCurve, QSize, QTimer, QPointF, QRectF)
from PyQt6.QtGui import (QColor, QPalette, QFont, QIcon, QLinearGradient, 
                      QGradient, QPainter, QBrush, QPen, QPainterPath,
                      QTransform)
import time
from dotenv import load_dotenv
from functools import lru_cache
import queue
import re
import random
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
import math
import webbrowser
import requests

load_dotenv()

# Set Mistral API key
MISTRAL_API_KEY = os.getenv('MISTRAL_API_KEY')
client = MistralClient(api_key=MISTRAL_API_KEY)

# Response queue for threading
response_queue = queue.Queue()

# Initialize text-to-speech engine with caching
@lru_cache(maxsize=1)
def init_text_to_speech():
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    engine.setProperty('rate', 180)
    engine.setProperty('volume', 0.9)
    for voice in voices:
        if "male" in voice.name.lower():
            engine.setProperty('voice', voice.id)
            break
    return engine

# Global TTS engine
tts_engine = init_text_to_speech()

class ResponseThread(QThread):
    response_ready = pyqtSignal(str)

    def __init__(self, question):
        super().__init__()
        self.question = question

    def run(self):
        translated_question = translate_to_english(self.question)
        answer = get_answer(translated_question)
        self.response_ready.emit(answer)

class Particle:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.size = random.randint(2, 5)
        self.speed = random.uniform(0.5, 2)
        self.angle = random.uniform(0, 360)
        self.opacity = random.uniform(0.3, 0.7)

    def move(self):
        self.x += self.speed * math.cos(math.radians(self.angle))
        self.y += self.speed * math.sin(math.radians(self.angle))
        self.opacity = max(0.1, self.opacity - 0.001)

class RobotAnimation(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hover_offset = 0
        self.hover_direction = 1
        
        # Animation parameters
        self.arm_angle = 0
        self.leg_angle = 0
        self.arm_direction = 1
        self.leg_direction = 1

        # Timer for animations
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(50)
        self.setFixedSize(150, 150)  # Increased size for the full robot

    def animate(self):
        # Hover animation
        self.hover_offset += 0.2 * self.hover_direction
        if abs(self.hover_offset) >= 5:
            self.hover_direction *= -1
            
        # Limb animation
        self.arm_angle += 1 * self.arm_direction
        if abs(self.arm_angle) >= 15:
            self.arm_direction *= -1
            
        self.leg_angle += 0.5 * self.leg_direction
        if abs(self.leg_angle) >= 10:
            self.leg_direction *= -1
            
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Save the current state
        painter.save()
        
        # Translate to center and apply hover effect
        painter.translate(self.width() / 2, self.height() / 2 + self.hover_offset)

        # Draw robot body (torso)
        painter.setPen(QPen(QColor("#3498db"), 2))
        painter.setBrush(QBrush(QColor("#2c3e50")))
        painter.drawRoundedRect(-20, -15, 40, 50, 10, 10)  # Torso

        # Draw head with glowing elements
        painter.drawEllipse(-25, -45, 50, 40)  # Head
        
        # Draw glowing eyes
        painter.setBrush(QBrush(QColor("#3498db")))
        painter.drawEllipse(-15, -35, 10, 10)  # Left eye
        painter.drawEllipse(5, -35, 10, 10)    # Right eye
        
        # Draw antenna with glowing tip
        painter.drawLine(0, -45, 0, -55)
        gradient = QLinearGradient(0, -60, 0, -55)
        gradient.setColorAt(0, QColor("#3498db"))
        gradient.setColorAt(1, QColor("#2980b9"))
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(-5, -60, 10, 10)

        # Draw arms with joints
        painter.save()
        painter.rotate(self.arm_angle)  # Animate arms
        # Left arm
        painter.drawRoundedRect(-45, -10, 25, 10, 5, 5)  # Upper arm
        painter.drawEllipse(-48, -12, 14, 14)  # Shoulder joint
        # Right arm
        painter.drawRoundedRect(20, -10, 25, 10, 5, 5)   # Upper arm
        painter.drawEllipse(34, -12, 14, 14)   # Shoulder joint
        painter.restore()

        # Draw legs with joints
        painter.save()
        painter.rotate(self.leg_angle)  # Animate legs
        # Left leg
        painter.drawRoundedRect(-30, 35, 15, 30, 5, 5)   # Upper leg
        painter.drawEllipse(-28, 32, 12, 12)   # Hip joint
        # Right leg
        painter.drawRoundedRect(15, 35, 15, 30, 5, 5)    # Upper leg
        painter.drawEllipse(16, 32, 12, 12)    # Hip joint
        painter.restore()

        # Draw chest light
        gradient = QLinearGradient(0, -5, 0, 5)
        gradient.setColorAt(0, QColor("#3498db"))
        gradient.setColorAt(1, QColor("#2980b9"))
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(-10, 0, 20, 20)

        # Restore the state
        painter.restore()

class ParticleBackground(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.particles = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.updateParticles)
        self.timer.start(50)
        self.generate_particles()

    def generate_particles(self):
        for _ in range(50):
            x = random.randint(0, self.width())
            y = random.randint(0, self.height())
            self.particles.append(Particle(x, y))

    def updateParticles(self):
        for particle in self.particles:
            particle.move()
            if (particle.x < 0 or particle.x > self.width() or
                particle.y < 0 or particle.y > self.height() or
                particle.opacity < 0.1):
                self.particles.remove(particle)
                x = random.randint(0, self.width())
                y = random.randint(0, self.height())
                self.particles.append(Particle(x, y))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        for particle in self.particles:
            color = QColor("#3498db")
            color.setAlphaF(particle.opacity)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawEllipse(
                int(particle.x - particle.size/2),
                int(particle.y - particle.size/2),
                particle.size,
                particle.size
            )

class JarvisUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis AI Assistant")
        self.setGeometry(0, 0, 1366, 768)  # Set to a resolution suitable for Lenovo Yoga 460
        
        # Create particle background
        self.particle_bg = ParticleBackground(self)
        self.particle_bg.setGeometry(0, 0, 1366, 768)  # Adjust background size
        
        self.setup_ui()
        self.response_threads = []
        self.setup_styles()
        self.setup_animations()
        
    def setup_styles(self):
        # Dark blue theme with transparency
        self.setStyleSheet("""
            QWidget {
                background: transparent;
                color: #ffffff;
            }
            QTextBrowser {
                background-color: rgba(28, 31, 44, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                padding: 15px;
                font-size: 14px;
                selection-background-color: #3498db;
            }
            QTextEdit {
                background-color: rgba(28, 31, 44, 0.8);
                border: 2px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                padding: 12px 20px;
                font-size: 14px;
                color: white;
                selection-background-color: #3498db;
            }
            QPushButton {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                                stop:0 #3498db, stop:1 #2980b9);
                border: none;
                border-radius: 15px;
                padding: 12px 25px;
                color: white;
                font-weight: bold;
                font-size: 14px;
                box-shadow: 0px 4px 15px rgba(0, 0, 0, 0.3);
            }
            QPushButton:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                                stop:0 #3ea8e5, stop:1 #3498db);
            }
            QPushButton:pressed {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                                stop:0 #2980b9, stop:1 #2472a4);
            }
            QPushButton:disabled {
                background-color: rgba(52, 73, 94, 0.7);
                color: rgba(255, 255, 255, 0.7);
            }
            QLabel {
                color: #ffffff;
                font-family: 'Segoe UI', Arial;
            }
            #container {
                background-color: rgba(28, 31, 44, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 20px;
            }
        """)

    def setup_animations(self):
        # Pulse animation for status indicator
        self.pulse_animation = QPropertyAnimation(self.status_label, b"geometry")
        self.pulse_animation.setDuration(1500)
        self.pulse_animation.setLoopCount(-1)
        
    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(15, 20, 15, 20)
        
        # Glassmorphism container
        container = QFrame()
        container.setObjectName("container")
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(15)
        container_layout.setContentsMargins(15, 20, 15, 20)
        
        # Header with robot animation
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                padding: 5px;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(15, 5, 15, 5)
        
        # Add rotating robot
        self.robot_animation = RobotAnimation()
        
        title_label = QLabel("JARVIS")
        title_label.setFont(QFont("Segoe UI", 32, QFont.Weight.Bold))
        title_label.setStyleSheet("""
            color: #3498db;
            background: none;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.status_label = QLabel("🎤 Voice Recognition Active")
        self.status_label.setFont(QFont("Segoe UI", 11))
        self.status_label.setStyleSheet("""
            color: #3498db;
            background: rgba(52, 152, 219, 0.1);
            padding: 6px 12px;
            border-radius: 12px;
        """)
        
        header_layout.addWidget(self.robot_animation)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.status_label)
        
        container_layout.addWidget(header_frame)
        
        # Chat display with custom styling
        chat_frame = QFrame()
        chat_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.05);
                border-radius: 15px;
            }
        """)
        chat_layout = QVBoxLayout(chat_frame)
        chat_layout.setContentsMargins(10, 10, 10, 10)
        
        self.text_browser = QTextBrowser()
        self.text_browser.setFont(QFont("Segoe UI", 11))
        self.text_browser.setMinimumHeight(280)
        self.text_browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        
        chat_layout.addWidget(self.text_browser)
        container_layout.addWidget(chat_frame)
        
        # Modern input area with fixed width for send button
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 25px;
                padding: 5px;
            }
        """)
        self.input_layout = QHBoxLayout(input_frame)
        self.input_layout.setContentsMargins(10, 8, 10, 8)
        self.input_layout.setSpacing(10)
        
        self.text_input = QTextEdit()  # Changed from QLineEdit to QTextEdit for multi-line input
        self.text_input.setPlaceholderText("Type your question here...")
        self.text_input.setMinimumHeight(10)  # Reduced height for better appearance
        self.text_input.setMinimumWidth(400)  # Reduced width for better appearance
        self.text_input.setFont(QFont("Segoe UI", 11))
        
        self.send_button = QPushButton("Send")
        self.send_button.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.send_button.setMinimumHeight(45)
        self.send_button.setFixedWidth(120)  # Keep the send button width as is for usability
        
        self.input_layout.addWidget(self.text_input, stretch=1)
        self.input_layout.addWidget(self.send_button)
        
        container_layout.addWidget(input_frame)
        
        # Modern footer
        footer_frame = QFrame()
        footer_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                padding: 8px;
            }
        """)
        footer_layout = QHBoxLayout(footer_frame)
        
        footer_text = QLabel("Say 'Jarvis' to activate voice commands")
        footer_text.setFont(QFont("Segoe UI", 10))
        footer_text.setStyleSheet("""
            color: #888888;
            background: none;
        """)
        footer_layout.addWidget(footer_text, alignment=Qt.AlignmentFlag.AlignCenter)
        
        container_layout.addWidget(footer_frame)
        
        main_layout.addWidget(container)
        self.setLayout(main_layout)
        
        # Connect signals
        self.send_button.clicked.connect(self.handle_text_input)
        
        # Start listener thread
        self.listener_thread = ListenerThread()
        self.listener_thread.text_signal.connect(self.handle_thread_signal)
        self.listener_thread.start()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self.handle_text_input()
        elif event.key() == Qt.Key.Key_Shift and event.key() == Qt.Key.Key_Return:
            self.text_input.insertPlainText("\n")  # Allow new line

    def handle_thread_signal(self, text):
        # Animate the status indicator when receiving signals
        if "listening" in text.lower():
            self.status_label.setText("🎤 Actively Listening...")
            self.status_label.setStyleSheet("color: #ff6b6b;")
        else:
            self.status_label.setText("🎤 Voice Recognition Active")
            self.status_label.setStyleSheet("color: #3498db;")
        
        # Add text with styling
        if "You:" in text:
            self.add_message(text, is_user=True)
        elif "Jarvis:" in text:
            self.add_message(text, is_user=False)
        else:
            self.text_browser.append(f"<span style='color: #888888;'>{text}</span>")

    def add_message(self, text, is_user=True):
        timestamp = datetime.now().strftime("%H:%M")
        if is_user:
            message_html = f"""
                <div style='margin: 15px 0;'>
                    <div style='text-align: right;'>
                        <span style='background: linear-gradient(135deg, #3498db, #2980b9);
                               padding: 12px 20px;
                               border-radius: 20px 20px 5px 20px;
                               display: inline-block;
                               max-width: 85%;
                               box-shadow: 0 4px 15px rgba(52, 152, 219, 0.2);'>
                            {text}
                        </span>
                        <br>
                        <span style='color: #888888; font-size: 0.8em; margin-top: 5px; display: inline-block;'>{timestamp}</span>
                    </div>
                </div>
            """
        else:
            message_html = f"""
                <div style='margin: 15px 0;'>
                    <div style='text-align: left;'>
                        <span style='background: linear-gradient(135deg, #2c3e50, #2c3e50);
                               padding: 12px 20px;
                               border-radius: 20px 20px 20px 5px;
                               display: inline-block;
                               max-width: 85%;
                               box-shadow: 0 4px 15px rgba(44, 62, 80, 0.2);'>
                            {text}
                        </span>
                        <br>
                        <span style='color: #888888; font-size: 0.8em; margin-top: 5px; display: inline-block;'>{timestamp}</span>
                    </div>
                </div>
            """
        self.text_browser.append(message_html)
        self.text_browser.verticalScrollBar().setValue(
            self.text_browser.verticalScrollBar().maximum()
        )

    def handle_response(self, answer):
        self.add_message(f"🤖 Jarvis: {answer}", is_user=False)
        speak(answer)

    def handle_text_input(self):
        question = self.text_input.toPlainText().strip()
        if question:
            self.text_input.clear()
            self.add_message(f"👤 You: {question}", is_user=True)
            
            # Animate the send button
            self.send_button.setEnabled(False)
            self.send_button.setText("Thinking...")
            
            response_thread = ResponseThread(question)
            response_thread.response_ready.connect(self.handle_response)
            response_thread.finished.connect(lambda: self.reset_send_button())
            response_thread.start()
            self.response_threads.append(response_thread)

    def reset_send_button(self):
        self.send_button.setEnabled(True)
        self.send_button.setText("Send")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.particle_bg.setGeometry(0, 0, self.width(), self.height())

class ListenerThread(QThread):
    text_signal = pyqtSignal(str)

    def run(self):
        while True:  # Main loop to keep the thread running
            try:
                # Initialize recognizer for each attempt
                recognizer = sr.Recognizer()
                recognizer.energy_threshold = 2500  # Even lower threshold for better sensitivity
                recognizer.dynamic_energy_threshold = True
                recognizer.pause_threshold = 1.0  # Longer pause to allow for natural speech
                recognizer.phrase_threshold = 0.5  # More lenient phrase detection
                
                # Initialize microphone
                with sr.Microphone() as source:
                    print("\nListening for 'Jarvis'... (Microphone is active)")
                    self.text_signal.emit("\n🎤 Microphone is active and listening for 'Jarvis'...")
                    
                    # Initial adjustment
                    recognizer.adjust_for_ambient_noise(source, duration=1)
                    
                    while True:
                        try:
                            print("Waiting for command...")
                            audio = recognizer.listen(source, timeout=None, phrase_time_limit=8)
                            
                            try:
                                command = recognizer.recognize_google(audio).lower()
                                print(f"Heard: {command}")
                                
                                if "jarvis" in command:
                                    self.text_signal.emit("\n👤 You: Jarvis")
                                    self.text_signal.emit("🤖 Jarvis: Yes, boss? Take your time with your question.")
                                    speak("Yes, boss? Take your time with your question.")
                                    self.conversation_mode()
                                    
                            except sr.UnknownValueError:
                                continue
                            except sr.RequestError as e:
                                print(f"Could not request results; {e}")
                                self.text_signal.emit("⚠️ Network error. Retrying...")
                                time.sleep(1)
                                continue
                                
                        except Exception as e:
                            print(f"Error in listening loop: {e}")
                            time.sleep(0.1)
                            continue
                            
            except Exception as e:
                print(f"Microphone error: {e}")
                self.text_signal.emit("⚠️ Microphone error. Reinitializing...")
                time.sleep(2)
                continue

    def conversation_mode(self):
        try:
            recognizer = sr.Recognizer()
            recognizer.energy_threshold = 3000
            recognizer.dynamic_energy_threshold = True
            recognizer.pause_threshold = 0.8
            
            with sr.Microphone() as source:
                self.text_signal.emit("\n🤖 Jarvis: I'm listening...")
                speak("I'm listening...")
                
                # Initial adjustment
                recognizer.adjust_for_ambient_noise(source, duration=1)
                
                while True:
                    try:
                        print("Listening for question...")
                        audio = recognizer.listen(source, timeout=None, phrase_time_limit=5)
                        
                        try:
                            question = recognizer.recognize_google(audio).lower()
                            print(f"Heard: {question}")  # Debugging line
                            
                            if "goodbye" in question or "bye" in question:
                                self.text_signal.emit("\n👤 You: " + question)
                                self.text_signal.emit("🤖 Jarvis: Goodbye! Call me if you need anything.")
                                speak("Goodbye! Call me if you need anything.")
                                return
                            
                            # Check for commands
                            if "set timer" in question:
                                print("Detected command: set timer")  # Debugging line
                                self.set_timer(question)
                            elif "play music" in question:
                                print("Detected command: play music")  # Debugging line
                                self.play_music()
                            else:
                                print("Processing as a regular question")  # Debugging line
                                self.text_signal.emit(f"\n👤 You: {question}")
                                translated_question = translate_to_english(question)
                                answer = get_answer(translated_question)
                                self.text_signal.emit(f"🤖 Jarvis: {answer}")
                                speak(answer)
                            
                        except sr.UnknownValueError:
                            continue
                        except sr.RequestError as e:
                            print(f"Could not request results; {e}")
                            continue
                            
                    except Exception as e:
                        print(f"Error in conversation: {e}")
                        continue
                        
        except Exception as e:
            print(f"Microphone error in conversation: {e}")
            self.text_signal.emit("⚠️ Microphone error. Please try again.")
            return

    def set_timer(self, question):
        match = re.search(r'(\d+)\s*seconds?', question)
        if match:
            seconds = int(match.group(1))
            threading.Timer(seconds, self.timer_finished).start()
            self.text_signal.emit(f"⏰ Timer set for {seconds} seconds.")
            speak(f"Timer set for {seconds} seconds.")
        else:
            self.text_signal.emit("⚠️ I couldn't understand the timer duration.")
            speak("I couldn't understand the timer duration.")

    def timer_finished(self):
        self.text_signal.emit("⏰ Time's up!")
        speak("Time's up!")

    def play_music(self):
        music_directory = "/This PC/music"  # Change this to your actual music directory
        music_files = [f for f in os.listdir(music_directory) if f.endswith(('.mp3', '.wav'))]
        if music_files:
            os.startfile(os.path.join(music_directory, music_files[0]))
            self.text_signal.emit("🎶 Playing music.")
            speak("Playing music.")
        else:
            webbrowser.open("https://www.youtube.com/results?search_query=music")
            self.text_signal.emit("🎶 No music files found. Opening music in the browser.")
            speak("No music files found. Opening music in the browser.")

    def tell_weather(self):
        # Replace with your weather API key and endpoint
        api_key = "YOUR_WEATHER_API_KEY"
        city = "YOUR_CITY"  # You can modify this to get the city from the user
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"
        
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            temperature = data['main']['temp']
            weather_description = data['weather'][0]['description']
            self.text_signal.emit(f"The current temperature in {city} is {temperature}°C with {weather_description}.")
            speak(f"The current temperature in {city} is {temperature} degrees Celsius with {weather_description}.")
        else:
            self.text_signal.emit("⚠️ Unable to fetch weather data.")
            speak("Unable to fetch weather data.")

@lru_cache(maxsize=100)
def translate_to_english(text):
    try:
        translated_text = GoogleTranslator(source='auto', target='en').translate(text)
        return translated_text
    except Exception:
        return text

def get_answer(question):
    """Get answer using Mistral AI"""
    try:
        # Prepare the prompt based on question type
        question_lower = question.lower()
        
        if "capital" in question_lower:
            system_prompt = "You are a helpful AI assistant that gives very concise answers about capital cities. Answer in one short sentence without any additional context."
            user_prompt = f"What is the official capital city of the country mentioned in this question: {question}"
        elif "area" in question_lower or "size" in question_lower:
            system_prompt = "You are a helpful AI assistant that gives precise numerical answers about geographical areas. Answer with just the number and unit without any additional text."
            user_prompt = f"What is the total area in square kilometers of the country/region mentioned in: {question}"
        elif "population" in question_lower:
            system_prompt = "You are a helpful AI assistant that gives precise numerical answers about population. Answer with just the number without any additional text."
            user_prompt = f"What is the current population of the location mentioned in: {question}"
        elif "list" in question_lower or "what are" in question_lower:
            system_prompt = "You are a helpful AI assistant that creates concise numbered lists. Format the response as a simple numbered list without any introduction or conclusion."
            user_prompt = f"List only the top 5 most important items for: {question}"
        else:
            system_prompt = "You are a helpful AI assistant that gives very concise, direct answers. Answer in one sentence without any additional context or explanation."
            user_prompt = question

        # Make the request to Mistral
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt)
        ]
        
        chat_response = client.chat(
            model="mistral-tiny",  # Using the tiny model for faster responses
            messages=messages,
            temperature=0.1,
            max_tokens=100,
            top_p=0.9,
            random_seed=42  # For consistent responses
        )
        
        if chat_response and chat_response.choices:
            answer = chat_response.choices[0].message.content.strip()
            # Clean up the response
            answer = answer.replace("Answer:", "").replace("Response:", "").strip()
            # Add period if missing and not a list
            if not any(char.isdigit() for char in answer) and not answer.endswith(('.', '!', '?')):
                answer += '.'
            return answer

    except Exception as e:
        print(f"Error getting answer: {e}")
        return f"I apologize, but I encountered an error: {str(e)}"
    
    return "I'm sorry, I couldn't find accurate information for your question. Could you please rephrase it?"

def speak(text):
    global tts_engine
    try:
        # Remove URLs and technical symbols for better speech
        clean_text = re.sub(r'http\S+|www.\S+|\n|Source:', '', text)
        tts_engine.say(clean_text)
        tts_engine.runAndWait()
    except Exception as e:
        print(f"Speech synthesis error: {e}")
        tts_engine = init_text_to_speech()

if __name__ == "__main__":
    app = QApplication([])
    jarvis_ui = JarvisUI()
    jarvis_ui.show()
    app.exec()
