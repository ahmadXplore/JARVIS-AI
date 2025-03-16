import os
import subprocess
import threading
import speech_recognition as sr
import pyttsx3
from datetime import datetime
from deep_translator import GoogleTranslator
from PyQt6.QtWidgets import (QApplication, QWidget, QTextBrowser, QVBoxLayout, 
                          QLineEdit, QPushButton, QHBoxLayout, QLabel, 
                          QFrame, QGraphicsDropShadowEffect, QSizePolicy,
                          QScrollArea)
from PyQt6.QtCore import (QThread, pyqtSignal, Qt, QPropertyAnimation, 
                       QEasingCurve, QSize, QTimer)
from PyQt6.QtGui import (QColor, QPalette, QFont, QIcon, QLinearGradient, 
                      QGradient, QPainter, QBrush, QPen, QPainterPath)
import time
from dotenv import load_dotenv
from functools import lru_cache
import queue
import json
import re
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage

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

class JarvisUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis AI Assistant")
        self.setGeometry(100, 100, 900, 500)  # Wider but shorter window
        self.setup_ui()
        self.response_threads = []
        self.setup_styles()
        self.setup_animations()
        
    def setup_styles(self):
        # Dark theme with purple accents
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                          stop:0 #1a1a1a, stop:0.5 #2d2d2d, stop:1 #1a1a1a);
                color: #ffffff;
            }
            QTextBrowser {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                padding: 15px;
                font-size: 14px;
                selection-background-color: #9b59b6;
            }
            QLineEdit {
                background-color: rgba(255, 255, 255, 0.07);
                border: 2px solid rgba(255, 255, 255, 0.1);
                border-radius: 25px;
                padding: 12px 20px;
                font-size: 14px;
                color: white;
                selection-background-color: #9b59b6;
            }
            QLineEdit:focus {
                border: 2px solid #9b59b6;
                background-color: rgba(255, 255, 255, 0.1);
            }
            QPushButton {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                                stop:0 #9b59b6, stop:1 #8e44ad);
                border: none;
                border-radius: 25px;
                padding: 12px 25px;
                color: white;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                                stop:0 #a66bbe, stop:1 #9b59b6);
            }
            QPushButton:pressed {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                                stop:0 #8e44ad, stop:1 #763c94);
            }
            QLabel {
                color: #ffffff;
                font-family: 'Segoe UI', Arial;
            }
        """)

    def setup_animations(self):
        # Pulse animation for status indicator
        self.pulse_animation = QPropertyAnimation(self.status_label, b"geometry")
        self.pulse_animation.setDuration(1500)
        self.pulse_animation.setLoopCount(-1)
        
    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)  # Reduced spacing
        main_layout.setContentsMargins(30, 20, 30, 20)  # Reduced vertical margins
        
        # Glassmorphism container
        container = QFrame()
        container.setObjectName("container")
        container.setStyleSheet("""
            #container {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 20px;
            }
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(15)  # Reduced spacing
        container_layout.setContentsMargins(25, 20, 25, 20)  # Reduced margins
        
        # Header with modern design
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                padding: 5px;  # Reduced padding
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(15, 5, 15, 5)  # Reduced margins
        
        logo_label = QLabel("🤖")
        logo_label.setFont(QFont("Segoe UI", 32))  # Slightly smaller font
        logo_label.setStyleSheet("background: none;")
        
        title_label = QLabel("JARVIS AI")
        title_label.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))  # Slightly smaller font
        title_label.setStyleSheet("""
            color: #9b59b6;
            background: none;
        """)
        
        self.status_label = QLabel("🎤 Voice Recognition Active")
        self.status_label.setFont(QFont("Segoe UI", 11))  # Slightly smaller font
        self.status_label.setStyleSheet("""
            color: #9b59b6;
            background: rgba(155, 89, 182, 0.1);
            padding: 6px 12px;  # Reduced padding
            border-radius: 12px;
        """)
        
        header_layout.addWidget(logo_label)
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
        chat_layout.setContentsMargins(10, 10, 10, 10)  # Reduced margins
        
        self.text_browser = QTextBrowser()
        self.text_browser.setFont(QFont("Segoe UI", 11))  # Slightly smaller font
        self.text_browser.setMinimumHeight(280)  # Reduced height
        self.text_browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        chat_layout.addWidget(self.text_browser)
        container_layout.addWidget(chat_frame)
        
        # Modern input area
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 25px;
                padding: 5px;
            }
        """)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(15, 8, 15, 8)  # Reduced margins
        
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Type your question here...")
        self.text_input.setMinimumHeight(40)  # Reduced height
        self.text_input.setFont(QFont("Segoe UI", 11))  # Slightly smaller font
        
        self.send_button = QPushButton("Send")
        self.send_button.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))  # Slightly smaller font
        self.send_button.setMinimumHeight(40)  # Reduced height
        self.send_button.setMinimumWidth(100)  # Slightly smaller width
        
        input_layout.addWidget(self.text_input)
        input_layout.addWidget(self.send_button)
        
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
        footer_text.setFont(QFont("Segoe UI", 10))  # Slightly smaller font
        footer_text.setStyleSheet("""
            color: #888888;
            background: none;
        """)
        footer_layout.addWidget(footer_text, alignment=Qt.AlignmentFlag.AlignCenter)
        
        container_layout.addWidget(footer_frame)
        
        main_layout.addWidget(container)
        self.setLayout(main_layout)
        
        # Connect signals
        self.text_input.returnPressed.connect(self.handle_text_input)
        self.send_button.clicked.connect(self.handle_text_input)
        
        # Start listener thread
        self.listener_thread = ListenerThread()
        self.listener_thread.text_signal.connect(self.handle_thread_signal)
        self.listener_thread.start()

    def handle_thread_signal(self, text):
        # Animate the status indicator when receiving signals
        if "listening" in text.lower():
            self.status_label.setText("🎤 Actively Listening...")
            self.status_label.setStyleSheet("color: #ff6b6b;")
        else:
            self.status_label.setText("🎤 Voice Recognition Active")
            self.status_label.setStyleSheet("color: #9b59b6;")
        
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
                        <span style='background: linear-gradient(135deg, #9b59b6, #8e44ad);
                               padding: 12px 20px;
                               border-radius: 20px 20px 5px 20px;
                               display: inline-block;
                               max-width: 70%;
                               box-shadow: 0 4px 15px rgba(155, 89, 182, 0.2);'>
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
                               max-width: 70%;
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
        question = self.text_input.text().strip()
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
                            audio = recognizer.listen(source, timeout=None, phrase_time_limit=8)  # Increased to 8 seconds
                            
                            try:
                                command = recognizer.recognize_google(audio).lower()
                                print(f"Heard: {command}")  # Debug print
                                
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
                            print(f"Heard: {question}")
                            
                            if "goodbye" in question or "bye" in question:
                                self.text_signal.emit("\n👤 You: " + question)
                                self.text_signal.emit("🤖 Jarvis: Goodbye! Call me if you need anything.")
                                speak("Goodbye! Call me if you need anything.")
                                return
                            
                            if question.strip():
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
