from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
import os
from groq import Groq
import aiofiles
from pydantic import BaseModel

app = Flask(__name__)
app.secret_key = 'supersecretkey'
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize the Groq client
client = Groq(api_key="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")

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


# Function to process text files
async def process_text_file(file):
    content = await file.read()
    return content.decode('utf-8')

# Function to process audio/video files (simulated processing)
async def process_audio_file(file):
    # Simulated transcription processing
    return "Simulated transcription for audio or video file"

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
        file_type = file.content_type
        if file_type.startswith('text'):
            content = file.read().decode('utf-8')
            combined_content += content + "\n"
        elif file_type.startswith('audio') or file_type.startswith('video'):
            content = "Simulated audio/video content processing"  # Placeholder for actual processing
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
