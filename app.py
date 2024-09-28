from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
import os
import fitz  # PyMuPDF
from docx import Document
import pytesseract
from PIL import Image
import aiofiles
from groq import Groq
import speech_recognition as sr
from pydub import AudioSegment
import moviepy.editor as mp
from pydantic import BaseModel

app = Flask(__name__)
app.secret_key = 'supersecretkey'
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize the Groq client
client = Groq(api_key="")

# Data storage (in-memory for simplicity)
user_data = {}  # {user_id: {persona: ..., context: ...}}

# In-memory user credentials for login
users = {"testuser": "password123"}

# Route for login
@app.route('/')
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users and users[username] == password:
            session['user_id'] = username
            return redirect(url_for('home'))
        else:
            flash("Incorrect Username or Password. Please try again.", "danger")
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

# Route for home
@app.route('/home')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('home.html')

# Function to extract text from PDF files
def extract_text_from_pdf(file_path):
    text = ""
    pdf_document = fitz.open(file_path)
    for page in pdf_document:
        text += page.get_text()
    return text

# Function to extract text from DOCX files
def extract_text_from_docx(file_path):
    text = ""
    doc = Document(file_path)
    for para in doc.paragraphs:
        text += para.text + "\n"
    return text

# Function to extract text from PNG images using OCR
def extract_text_from_image(file_path):
    text = pytesseract.image_to_string(Image.open(file_path))
    return text

# Function to extract text from audio files
def extract_text_from_audio(file_path):
    recognizer = sr.Recognizer()
    audio = sr.AudioFile(file_path)
    with audio as source:
        audio_data = recognizer.record(source)
    try:
        text = recognizer.recognize_google(audio_data)
    except sr.UnknownValueError:
        text = "Could not understand audio"
    except sr.RequestError:
        text = "Could not request results; check your network connection"
    return text

# Function to extract text from video files
def extract_text_from_video(file_path):
    # Extract audio from video
    video = mp.VideoFileClip(file_path)
    audio_path = file_path.rsplit('.', 1)[0] + ".wav"
    video.audio.write_audiofile(audio_path)
    
    # Transcribe the extracted audio
    text = extract_text_from_audio(audio_path)
    return text

# Function to process text files
async def process_text_file(file):
    content = await file.read()
    return content.decode('utf-8')

# Function to process audio/video files (actual processing)
async def process_audio_file(file):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
    file.save(file_path)
    
    if file.content_type.startswith('audio'):
        return extract_text_from_audio(file_path)
    elif file.content_type.startswith('video'):
        return extract_text_from_video(file_path)
    else:
        return "Unsupported file type"

# Upload files route
@app.route('/upload-files', methods=['POST'])
def upload_files():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    persona = request.form.get('persona')

    if 'files' not in request.files:
        return jsonify({"error": "No files part in the request"}), 400

    files = request.files.getlist('files')
    combined_content = ""
    
    for file in files:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        file_type = file.content_type
        
        if file_type.startswith('text'):
            content = file.read().decode('utf-8')
            combined_content += content + "\n"
        elif file_type.startswith('application/pdf'):
            content = extract_text_from_pdf(file_path)
            combined_content += content + "\n"
        elif file_type.startswith('application/vnd.openxmlformats-officedocument.wordprocessingml.document'):
            content = extract_text_from_docx(file_path)
            combined_content += content + "\n"
        elif file_type.startswith('image/'):
            content = extract_text_from_image(file_path)
            combined_content += content + "\n"
        elif file_type.startswith('audio') or file_type.startswith('video'):
            content = process_audio_file(file)
            combined_content += content + "\n"
        else:
            return jsonify({"error": f"Unsupported file type: {file_type}"}), 400
    
    # Store user data
    user_data[user_id] = {
        'persona': persona,
        'context': combined_content
    }
    
    return jsonify({"status": "Files processed and persona context created."}), 200

# Function to interact with the persona using Groq API
def ask_question(persona, context, question):
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": f"You are acting as the user's {persona}. Use the following context to inform your responses."
            },
            {
                "role": "user",
                "content": f"Context: {context}\nQuestion: {question}"
            }
        ],
        model="mixtral-8x7b-32768"
    )
    
    try:
        return chat_completion.choices[0].message.content
    except KeyError:
        return "Error: Could not retrieve a valid response from the model."

# Chat with persona route
@app.route('/ask', methods=['POST'])
def ask_question_endpoint():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    data = request.get_json()
    question = data.get('question')

    if user_id not in user_data:
        return jsonify({"error": "User data not found. Please upload files first."}), 404

    persona = user_data[user_id]['persona']
    context = user_data[user_id]['context']

    response = ask_question(persona, context, question)
    return jsonify({"response": response}), 200

# Route for registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if username in users:
            flash("Username already exists. Please choose a different username.", "danger")
            return redirect(url_for('register'))
        
        if password != confirm_password:
            flash("Passwords do not match. Please try again.", "danger")
            return redirect(url_for('register'))
        
        # Add new user to the users dictionary
        users[username] = password
        flash("Registration successful! You can now log in.", "success")
        return redirect(url_for('login'))
    
    return render_template('register.html')

if __name__ == "__main__":
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
