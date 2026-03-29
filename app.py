# ============================================
# KSUnited - Backend
# This is the "brain" of the app
# It handles users, posts, replies, and AI
# Run it with: python app.py
# ============================================


# ---- IMPORTS (tools we need) ----
from flask import Flask, render_template, request, jsonify, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import json
import boto3


# ---- APP SETUP ----
app = Flask(__name__)
app.secret_key = 'ksu-united-secret-2024'  # keeps user sessions secure
DATABASE = 'ksunited.db'                    # our database file name


# ---- LOGIN MANAGER ----
# this tracks who is logged in across all pages
login_manager = LoginManager()
login_manager.init_app(app)


# ---- AWS BEDROCK (the AI) ----
# connects to Amazon's AI service so FlashAI can answer questions
# AWS keys will come from the .env file we set up later
bedrock = boto3.client(
    service_name='bedrock-runtime',
    region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
)


# ---- ALL VALID FLAIRS ----
# these are the tags students pick when posting
# based on real KSU services and what students actually need
FLAIRS = [
    'Academic',         # classes, exams, grades, professors
    'Advising',         # KSU Navigate, degree planning, advisor questions
    'Dining',           # Prentice Cafe, The Hub, Side by Side, meal plans
    'Housing',          # Tri-Towers, Centennial Court, Verder, off-campus
    'Health & Wellness',# DeWeese Health Center, CARES Center, counseling
    'Tech Help',        # Canvas, FlashLine, WiFi, KSU TechHelp 330-672-HELP
    'Events',           # campus events, activities, things to do
    'Clubs',            # student organizations, joining clubs
    'Jobs & Co-ops',    # internships, part-time jobs, Career Center
    'Tutoring',         # Academic Success Center, find tutors, study help
    'Freshman Corner',  # new students, orientation, first year questions
    'Seniors Only',     # graduation, senior week, job hunting
    'International',    # ISO office, visa questions, intl student life
    'Find Friends',     # meet people, study groups, hang out
    'Campus Life',      # share pics, campus moments, KSU vibes
    'Accessibility',    # SAS, disability services, accommodations
    'Rant',             # just need to vent? this is the place
]


# ============================================
# USER CLASS
# Flask-Login needs this to keep track of
# who is logged in right now
# ============================================
class User(UserMixin):
    def __init__(self, id, email, username):
        self.id = id
        self.email = email
        self.username = username


# runs on every page load to check if someone is logged in
@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    user = conn.execute(
        'SELECT * FROM users WHERE id = ?', (user_id,)
    ).fetchone()
    conn.close()
    if user:
        return User(user['id'], user['email'], user['username'])
    return None  # nobody logged in


# ============================================
# DATABASE SETUP
# SQLite = a simple file-based database
# think of it like an Excel spreadsheet
# that Python can read and write to
# ============================================

# opens the database so we can read/write
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # lets us use row['username'] instead of row[2]
    return conn


# creates all the tables we need
# only runs once when you first start the app
def init_db():
    conn = get_db()

    # USERS TABLE
    # stores everyone who signs up
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT UNIQUE NOT NULL,
            username      TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            year          TEXT DEFAULT 'Student',
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # POSTS TABLE
    # stores every question/post on the feed
    # sentiment = AI will tag it positive / neutral / negative
    conn.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            content    TEXT NOT NULL,
            category   TEXT NOT NULL,
            anonymous  BOOLEAN NOT NULL,
            username   TEXT,
            upvotes    INTEGER DEFAULT 0,
            sentiment  TEXT DEFAULT 'neutral',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # REPLIES TABLE
    # stores all replies to posts
    conn.execute('''
        CREATE TABLE IF NOT EXISTS replies (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id    INTEGER NOT NULL,
            user_id    INTEGER,
            content    TEXT NOT NULL,
            anonymous  BOOLEAN NOT NULL,
            username   TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()


# ============================================
# ROUTES
# each @app.route is a URL the app can visit
# the frontend calls these to get/send data
# ============================================

# HOME PAGE
# just loads the HTML file
@app.route('/')
def home():
    return render_template('index.html')


# GET ALL POSTS
# frontend calls this to load the feed
# returns a list of all posts newest first
@app.route('/posts')
def get_posts():
    conn = get_db()
    posts = conn.execute(
        'SELECT * FROM posts ORDER BY created_at DESC'
    ).fetchall()
    conn.close()
    return jsonify([dict(p) for p in posts])


# GET FLAIRS
# frontend calls this to build the category dropdown
@app.route('/flairs')
def get_flairs():
    return jsonify(FLAIRS)


# SIGN UP
# creates a new student account
@app.route('/signup', methods=['POST'])
def signup():
    data = request.json         # data sent from the frontend signup form
    email    = data.get('email', '').strip()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    year     = data.get('year', 'Student')  # Freshman / Sophomore / Junior / Senior

    # make sure no fields are empty
    if not email or not username or not password:
        return jsonify({'success': False, 'error': 'All fields required'}), 400

    # NEVER store plain passwords — always scramble them first
    password_hash = generate_password_hash(password)

    try:
        conn = get_db()
        conn.execute(
            'INSERT INTO users (email, username, password_hash, year) VALUES (?, ?, ?, ?)',
            (email, username, password_hash, year)
        )
        conn.commit()

        # get the user we just created so we can log them in right away
        user_row = conn.execute(
            'SELECT * FROM users WHERE email = ?', (email,)
        ).fetchone()
        conn.close()

        user = User(user_row['id'], user_row['email'], user_row['username'])
        login_user(user)  # log them in automatically after signup
        return jsonify({'success': True, 'username': username})

    except sqlite3.IntegrityError:
        # this happens if the email is already registered
        return jsonify({'success': False, 'error': 'Email already registered'}), 400


# LOG IN
# checks email + password then logs the user in
@app.route('/login', methods=['POST'])
def login():
    data     = request.json
    email    = data.get('email', '').strip()
    password = data.get('password', '')

    conn     = get_db()
    user_row = conn.execute(
        'SELECT * FROM users WHERE email = ?', (email,)
    ).fetchone()
    conn.close()

    # check_password_hash compares the plain password to the scrambled one
    if user_row and check_password_hash(user_row['password_hash'], password):
        user = User(user_row['id'], user_row['email'], user_row['username'])
        login_user(user)
        return jsonify({'success': True, 'username': user_row['username']})

    # wrong email or wrong password
    return jsonify({'success': False, 'error': 'Wrong email or password'}), 401


# LOG OUT
@app.route('/logout', methods=['POST'])
def logout():
    logout_user()
    return jsonify({'success': True})


# WHO AM I?
# frontend calls this when the page loads
# to check if the user is already logged in
@app.route('/me')
def me():
    if current_user.is_authenticated:
        return jsonify({
            'logged_in': True,
            'username': current_user.username
        })
    return jsonify({'logged_in': False})


# CREATE POST
# saves a new question to the database
@app.route('/post', methods=['POST'])
def create_post():
    data = request.json

    # if anonymous is checked, don't attach their name
    user_id  = current_user.id if current_user.is_authenticated else None
    username = 'Anonymous' if data.get('anonymous') else (
        current_user.username if current_user.is_authenticated else 'Anonymous'
    )

    # make sure the flair is valid
    category = data.get('category', 'Academic')
    if category not in FLAIRS:
        category = 'Academic'

    conn = get_db()
    conn.execute(
        '''INSERT INTO posts
           (user_id, content, category, anonymous, username)
           VALUES (?, ?, ?, ?, ?)''',
        (user_id, data['content'], category, data['anonymous'], username)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# GET REPLIES
# loads all replies for a specific post
@app.route('/replies/<int:post_id>')
def get_replies(post_id):
    conn    = get_db()
    replies = conn.execute(
        'SELECT * FROM replies WHERE post_id = ? ORDER BY created_at ASC',
        (post_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in replies])


# ADD REPLY
# saves a reply to a specific post
@app.route('/reply/<int:post_id>', methods=['POST'])
def reply(post_id):
    data     = request.json
    user_id  = current_user.id if current_user.is_authenticated else None
    username = 'Anonymous' if data.get('anonymous') else (
        current_user.username if current_user.is_authenticated else 'Anonymous'
    )

    conn = get_db()
    conn.execute(
        '''INSERT INTO replies
           (post_id, user_id, content, anonymous, username)
           VALUES (?, ?, ?, ?, ?)''',
        (post_id, user_id, data['content'], data['anonymous'], username)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# UPVOTE
# adds 1 upvote to a post when someone clicks the arrow
@app.route('/upvote/<int:post_id>', methods=['POST'])
def upvote(post_id):
    conn = get_db()
    conn.execute(
        'UPDATE posts SET upvotes = upvotes + 1 WHERE id = ?', (post_id,)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ============================================
# AI ROUTES
# these talk to AWS Bedrock (Claude Haiku)
# Claude Haiku = cheapest + fastest AI model
# ============================================

# FLASHAI CHAT
# student asks a question, AI answers using KSU knowledge
@app.route('/ai', methods=['POST'])
def ai_assistant():
    data     = request.json
    question = data.get('question', '').strip()

    if not question:
        return jsonify({'answer': 'Please ask a question!'})

    # system prompt = tells the AI who it is and what it knows
    # the more KSU info we put here, the better the answers
    system_prompt = """You are FlashAI, the friendly AI assistant for KSUnited
— the Q&A community platform for Kent State University students in Kent, Ohio.

You know about:
- Academics: classes, GPA, adding/dropping courses, advisors, KSU Navigate
- Housing: dorms (Centennial Court, Tri-Towers, Verder Hall), off-campus options
- Dining: Prentice Cafe, The Hub, Side by Side — hours and meal plans
- Health: DeWeese Health Center (Eastway Drive), CARES Center, counseling
- Tech Help: KSU TechHelp 330-672-HELP (24/7), Canvas, FlashLine
- Career: Career Exploration and Development office, co-ops, internships
- International students: ISO office, visa questions
- Accessibility: Student Accessibility Services (SAS)
- Tutoring: Academic Success Center

Keep answers short, friendly, and helpful.
If you don't know something specific, say so and point them to kent.edu."""

    try:
        # build the message to send to AWS Bedrock
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 512,
            "system": system_prompt,
            "messages": [{"role": "user", "content": question}]
        })

        # send it to Claude Haiku on AWS Bedrock
        response = bedrock.invoke_model(
            body=body,
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            accept="application/json",
            contentType="application/json"
        )

        # read the response and send it back to the frontend
        result = json.loads(response.get("body").read())
        return jsonify({'answer': result["content"][0]["text"]})

    except Exception as e:
        # if AWS isn't set up yet, show a friendly message instead of crashing
        print(f"Bedrock error: {e}")
        return jsonify({'answer': 'FlashAI is offline right now. Try again soon!'})


# SUMMARIZE POST (TL;DR button)
# student clicks "summarize" on a long post
# AI gives a 1-2 sentence summary
@app.route('/summarize/<int:post_id>', methods=['POST'])
def summarize(post_id):
    conn = get_db()
    post = conn.execute(
        'SELECT content FROM posts WHERE id = ?', (post_id,)
    ).fetchone()
    conn.close()

    if not post:
        return jsonify({'summary': 'Post not found'})

    try:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 100,
            "messages": [{
                "role": "user",
                "content": f"Summarize this KSU student post in 1-2 sentences max: {post['content']}"
            }]
        })
        response = bedrock.invoke_model(
            body=body,
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            accept="application/json",
            contentType="application/json"
        )
        result = json.loads(response.get("body").read())
        return jsonify({'summary': result["content"][0]["text"]})

    except Exception as e:
        return jsonify({'summary': 'Could not summarize right now.'})


# DUPLICATE CHECKER
# before a student posts, we check if a similar question already exists
# sends the new question + existing post titles to AI
# AI says yes or no if it's a duplicate
@app.route('/check-duplicate', methods=['POST'])
def check_duplicate():
    data         = request.json
    new_question = data.get('content', '').strip()

    if not new_question:
        return jsonify({'is_duplicate': False})

    # get the last 20 post titles to compare against
    conn  = get_db()
    posts = conn.execute(
        'SELECT content FROM posts ORDER BY created_at DESC LIMIT 20'
    ).fetchall()
    conn.close()

    if not posts:
        return jsonify({'is_duplicate': False, 'similar': None})

    # build a list of existing posts to send to AI
    existing = '\n'.join([f"- {p['content'][:100]}" for p in posts])

    try:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 150,
            "messages": [{
                "role": "user",
                "content": f"""New question: "{new_question}"

Existing questions:
{existing}

Is the new question very similar to any existing one? 
Reply with JSON only: {{"is_duplicate": true/false, "similar": "the similar question or null"}}"""
            }]
        })
        response = bedrock.invoke_model(
            body=body,
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            accept="application/json",
            contentType="application/json"
        )
        result  = json.loads(response.get("body").read())
        text    = result["content"][0]["text"].strip()

        # try to parse the AI's JSON response
        try:
            parsed = json.loads(text)
            return jsonify(parsed)
        except:
            return jsonify({'is_duplicate': False, 'similar': None})

    except Exception as e:
        # if AI is offline just let them post anyway
        return jsonify({'is_duplicate': False, 'similar': None})


# ============================================
# START THE APP
# runs when you type: python app.py
# ============================================
if __name__ == '__main__':
    init_db()            # set up the database tables
    app.run(debug=True)  # debug=True shows errors in browser
                         # IMPORTANT: turn debug off before going live!