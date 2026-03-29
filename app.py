# ============================================
# KsUnited - Backend
# AWS Bedrock Bearer Token authentication
# Model: anthropic.claude-3-haiku-20240307-v1:0
# ============================================

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import json
import requests
import secrets
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ---- Load .env file ----
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, val = line.partition('=')
                    os.environ.setdefault(key.strip(), val.strip())

load_env()

app = Flask(__name__)
app.secret_key = 'ksu-united-secret-2024'
DATABASE = 'ksunited.db'

# ---- LOGIN MANAGER ----
login_manager = LoginManager()
login_manager.init_app(app)

# ---- AWS BEDROCK SETTINGS ----
BEDROCK_TOKEN  = os.environ.get('AWS_BEARER_TOKEN_BEDROCK', '')
BEDROCK_REGION = 'us-east-1'
BEDROCK_URL    = f'https://bedrock-runtime.{BEDROCK_REGION}.amazonaws.com'
MODEL_ID       = 'anthropic.claude-3-haiku-20240307-v1:0'

# ---- ADMIN CREDENTIALS ----
ADMIN_EMAIL    = 'admin@ksunited.edu'
ADMIN_PASSWORD = 'KSUAdmin2024!'

# ---- MAIL SETTINGS ----
MAIL_EMAIL    = os.environ.get('MAIL_EMAIL', '')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')

def send_reset_email(to_email, token):
    if not MAIL_EMAIL or not MAIL_PASSWORD:
        print(f'[MAIL] No credentials — token for {to_email}: {token}')
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'KsUnited ⚡ Password Reset'
        msg['From']    = MAIL_EMAIL
        msg['To']      = to_email
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:2rem;background:#07101e;color:#eef2f8;border-radius:10px">
          <h2 style="color:#EAB020;margin-bottom:.5rem">KsUnited ⚡</h2>
          <p style="color:#aab;margin-bottom:1.5rem">Password reset request received.</p>
          <div style="background:#0d1e36;border:1px solid rgba(234,176,32,.3);border-radius:8px;padding:1.2rem;text-align:center;margin-bottom:1.5rem">
            <div style="font-size:.75rem;color:#888;letter-spacing:.1em;text-transform:uppercase;margin-bottom:.5rem">Your Reset Token</div>
            <div style="font-size:2rem;font-weight:700;color:#EAB020;letter-spacing:.2em">{token}</div>
          </div>
          <p style="color:#888;font-size:.85rem">Enter this token on the reset page. It expires after use.</p>
          <p style="color:#555;font-size:.75rem;margin-top:1rem">If you didn't request this, ignore this email.</p>
        </div>
        """
        msg.attach(MIMEText(html, 'html'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(MAIL_EMAIL, MAIL_PASSWORD)
            server.sendmail(MAIL_EMAIL, to_email, msg.as_string())
        print(f'[MAIL] Reset email sent to {to_email}')
        return True
    except Exception as e:
        print(f'[MAIL] Failed to send email: {e}')
        return False

print(f"Bedrock token loaded: {'YES ✓' if BEDROCK_TOKEN else 'NO ✗ — check your .env file'}")


def call_bedrock(messages, system_prompt='', max_tokens=512):
    """Call AWS Bedrock using Bearer token. Returns text or None."""
    if not BEDROCK_TOKEN:
        return None
    url = f'{BEDROCK_URL}/model/{MODEL_ID}/invoke'
    headers = {
        'Content-Type':  'application/json',
        'Authorization': f'Bearer {BEDROCK_TOKEN}',
    }
    body = {
        'anthropic_version': 'bedrock-2023-05-31',
        'max_tokens': max_tokens,
        'messages': messages,
    }
    if system_prompt:
        body['system'] = system_prompt
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=30)
        print(f'Bedrock status: {resp.status_code}')
        if resp.status_code != 200:
            print(f'Bedrock error: {resp.text[:300]}')
        resp.raise_for_status()
        return resp.json()['content'][0]['text']
    except Exception as e:
        print(f'Bedrock error: {e}')
        return None


# ---- FLAIRS ----
FLAIRS = [
    'Academic', 'Advising', 'Dining', 'Housing',
    'Health & Wellness', 'Tech Help', 'Events', 'Clubs',
    'Jobs & Co-ops', 'Tutoring', 'Freshman Corner', 'Seniors Only',
    'International', 'Find Friends', 'Campus Life', 'Accessibility', 'Rant',
]

# ---- FLASHAI SYSTEM PROMPT ----
KSU_SYSTEM_PROMPT = """You are FlashAI, the friendly AI assistant for KsUnited —
the student Q&A community for Kent State University.

You talk like a helpful KSU senior who knows everything about campus.
Start responses with "Hey Flash!" occasionally. Be warm, helpful, and concise.
Always include a relevant kent.edu link when you know one.

FACTS YOU KNOW:
TUITION
- Ohio resident: ~$13,850/year
- Non-resident: ~$24,300/year
- More info: kent.edu/fbe-center/tuition-and-other-costs

HOUSING (kent.edu/housing)
- 6,200 students live on campus
- Freshmen and sophomores required to live on campus
- Dorms: Centennial Court, Tri-Towers, Eastway, Verder, Prentice, Lake, Olson
- Eastway Center: most popular for freshmen, dining on-site, all-you-can-eat
- Centennial Court: great option, own bathroom cleaned weekly
- Double room: ~$4,345/semester

DINING (kent.edu/dining)
- Eastway Market: all-you-can-eat swipe dining, open for breakfast/lunch/dinner
- Prentice Cafe, The Hub, Side by Side also available
- Meal plans required for on-campus students

HEALTH
- DeWeese Health Center: kent.edu/health
- Counseling services available on campus
- CARES Center for food/housing insecurity needs
- Student Accessibility Services: kent.edu/sas

TECH HELP
- TechHelp: 330-672-HELP available 24/7
- Canvas help: available inside Canvas > Help menu
- FlashLine portal: flashline.kent.edu

ADVISING
- KSU Navigate: navigate.kent.edu
- Add/drop classes through FlashLine

CAREER
- Career Exploration and Development: kent.edu/career
- Co-ops and internships available

CAMPUS LIFE
- 86% of students feel safe on campus
- Active Greek life, clubs, intramural sports
- Kent State Athletics: kent.edu/athletics

If you do not know something specific, be honest and direct them to kent.edu.
Keep answers to 2-4 sentences unless more detail is needed."""


# ============================================
# USER
# ============================================
class User(UserMixin):
    def __init__(self, id, email, username, is_admin=False):
        self.id = id
        self.email = email
        self.username = username
        self.is_admin = is_admin


@login_manager.user_loader
def load_user(user_id):
    if str(user_id) == 'admin':
        return User('admin', ADMIN_EMAIL, 'Admin', is_admin=True)
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if user:
        return User(user['id'], user['email'], user['username'])
    return None


# ============================================
# DATABASE
# ============================================
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        email         TEXT UNIQUE NOT NULL,
        username      TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        year          TEXT DEFAULT 'Student',
        reset_token   TEXT,
        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS posts (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER,
        content    TEXT NOT NULL,
        category   TEXT NOT NULL,
        anonymous  BOOLEAN NOT NULL,
        username   TEXT,
        upvotes    INTEGER DEFAULT 0,
        sentiment  TEXT DEFAULT 'neutral',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS replies (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id    INTEGER NOT NULL,
        user_id    INTEGER,
        content    TEXT NOT NULL,
        anonymous  BOOLEAN NOT NULL,
        username   TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()


# ============================================
# ROUTES
# ============================================

@app.route('/')
def home():
    if not current_user.is_authenticated:
        return redirect(url_for('login_page'))
    return render_template('index.html')


@app.route('/login')
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    return render_template('login.html')


@app.route('/admin')
def admin_page():
    return render_template('admin.html')


@app.route('/posts')
def get_posts():
    conn  = get_db()
    posts = conn.execute('SELECT * FROM posts ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(p) for p in posts])


@app.route('/flairs')
def get_flairs():
    return jsonify(FLAIRS)


@app.route('/signup', methods=['POST'])
def signup():
    data     = request.json
    email    = data.get('email', '').strip()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    year     = data.get('year', 'Student')

    if not email or not username or not password:
        return jsonify({'success': False, 'error': 'All fields required'}), 400

    try:
        conn = get_db()
        conn.execute(
            'INSERT INTO users (email, username, password_hash, year) VALUES (?, ?, ?, ?)',
            (email, username, generate_password_hash(password), year)
        )
        conn.commit()
        row = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        user = User(row['id'], row['email'], row['username'])
        login_user(user)
        return jsonify({'success': True, 'username': username, 'user_id': row['id'], 'is_admin': False})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'error': 'Email already registered'}), 400


@app.route('/login', methods=['POST'])
def login():
    data     = request.json
    email    = data.get('email', '').strip()
    password = data.get('password', '')

    # Admin login
    if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
        admin = User('admin', ADMIN_EMAIL, 'Admin', is_admin=True)
        login_user(admin)
        return jsonify({'success': True, 'username': 'Admin', 'user_id': 'admin', 'is_admin': True})

    conn = get_db()
    row  = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()
    if row and check_password_hash(row['password_hash'], password):
        login_user(User(row['id'], row['email'], row['username']))
        return jsonify({'success': True, 'username': row['username'], 'user_id': row['id'], 'is_admin': False})
    return jsonify({'success': False, 'error': 'Wrong email or password'}), 401


@app.route('/logout', methods=['POST'])
def logout():
    logout_user()
    return jsonify({'success': True})


@app.route('/me')
def me():
    if current_user.is_authenticated:
        return jsonify({
            'logged_in': True,
            'username': current_user.username,
            'user_id': current_user.id,
            'is_admin': getattr(current_user, 'is_admin', False)
        })
    return jsonify({'logged_in': False})


# ---- FORGOT PASSWORD ----
@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    email = request.json.get('email', '').strip()
    if not email.endswith('@kent.edu'):
        return jsonify({'success': False, 'error': 'Must be a @kent.edu email'}), 400
    conn = get_db()
    row  = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'success': True, 'message': 'If that email is registered, a reset code was sent.'})
    token = ''.join(secrets.choice(string.digits) for _ in range(6))
    conn.execute('UPDATE users SET reset_token = ? WHERE email = ?', (token, email))
    conn.commit()
    conn.close()
    sent = send_reset_email(email, token)
    if sent:
        return jsonify({'success': True, 'message': f'Reset code sent to {email}! Check your inbox.'})
    else:
        return jsonify({'success': True, 'message': 'Reset code sent! Check your inbox.', 'token': token})


@app.route('/reset-password', methods=['POST'])
def reset_password():
    data     = request.json
    email    = data.get('email', '').strip()
    token    = data.get('token', '').strip()
    password = data.get('password', '')
    if not email or not token or not password:
        return jsonify({'success': False, 'error': 'All fields required'}), 400
    conn = get_db()
    row  = conn.execute('SELECT * FROM users WHERE email = ? AND reset_token = ?', (email, token)).fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'error': 'Invalid token or email'}), 400
    conn.execute('UPDATE users SET password_hash = ?, reset_token = NULL WHERE email = ?',
                 (generate_password_hash(password), email))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Password reset! You can now log in.'})


@app.route('/post', methods=['POST'])
def create_post():
    data     = request.json
    user_id  = current_user.id if current_user.is_authenticated else None
    username = 'Anonymous' if data.get('anonymous') else (
        current_user.username if current_user.is_authenticated else 'Anonymous'
    )
    category = data.get('category', 'Academic')
    if category not in FLAIRS:
        category = 'Academic'

    sentiment = 'neutral'
    answer = call_bedrock(
        messages=[{'role': 'user', 'content':
            f'Reply with ONE word only — positive, negative, or neutral — '
            f'for this student post: "{data["content"][:200]}"'
        }],
        max_tokens=5
    )
    if answer:
        w = answer.strip().lower()
        if 'positive' in w:
            sentiment = 'positive'
        elif 'negative' in w:
            sentiment = 'negative'

    conn = get_db()
    conn.execute(
        'INSERT INTO posts (user_id,content,category,anonymous,username,sentiment) VALUES (?,?,?,?,?,?)',
        (user_id, data['content'], category, data['anonymous'], username, sentiment)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ---- DELETE POST ----
@app.route('/post/<int:post_id>', methods=['DELETE'])
def delete_post(post_id):
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    conn = get_db()
    post = conn.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    if not post:
        conn.close()
        return jsonify({'success': False, 'error': 'Post not found'}), 404
    is_admin = getattr(current_user, 'is_admin', False)
    if str(post['user_id']) != str(current_user.id) and not is_admin:
        conn.close()
        return jsonify({'success': False, 'error': 'Not your post'}), 403
    conn.execute('DELETE FROM posts WHERE id = ?', (post_id,))
    conn.execute('DELETE FROM replies WHERE post_id = ?', (post_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/replies/<int:post_id>')
def get_replies(post_id):
    conn    = get_db()
    replies = conn.execute(
        'SELECT * FROM replies WHERE post_id = ? ORDER BY created_at ASC', (post_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in replies])


@app.route('/reply/<int:post_id>', methods=['POST'])
def reply(post_id):
    data     = request.json
    user_id  = current_user.id if current_user.is_authenticated else None
    username = 'Anonymous' if data.get('anonymous') else (
        current_user.username if current_user.is_authenticated else 'Anonymous'
    )
    conn = get_db()
    conn.execute(
        'INSERT INTO replies (post_id,user_id,content,anonymous,username) VALUES (?,?,?,?,?)',
        (post_id, user_id, data['content'], data['anonymous'], username)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/upvote/<int:post_id>', methods=['POST'])
def upvote(post_id):
    conn = get_db()
    conn.execute('UPDATE posts SET upvotes = upvotes + 1 WHERE id = ?', (post_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ============================================
# ADMIN ROUTES
# ============================================

@app.route('/admin/stats')
def admin_stats():
    if not current_user.is_authenticated or not getattr(current_user, 'is_admin', False):
        return jsonify({'error': 'Unauthorized'}), 403
    conn    = get_db()
    users   = conn.execute('SELECT COUNT(*) as c FROM users').fetchone()['c']
    posts   = conn.execute('SELECT COUNT(*) as c FROM posts').fetchone()['c']
    replies = conn.execute('SELECT COUNT(*) as c FROM replies').fetchone()['c']
    pos     = conn.execute("SELECT COUNT(*) as c FROM posts WHERE sentiment='positive'").fetchone()['c']
    neg     = conn.execute("SELECT COUNT(*) as c FROM posts WHERE sentiment='negative'").fetchone()['c']
    conn.close()
    return jsonify({'users': users, 'posts': posts, 'replies': replies,
                    'positive': pos, 'negative': neg, 'neutral': posts - pos - neg})


@app.route('/admin/users')
def admin_users():
    if not current_user.is_authenticated or not getattr(current_user, 'is_admin', False):
        return jsonify({'error': 'Unauthorized'}), 403
    conn  = get_db()
    users = conn.execute('SELECT id, email, username, year, created_at FROM users ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(u) for u in users])


@app.route('/admin/posts')
def admin_posts():
    if not current_user.is_authenticated or not getattr(current_user, 'is_admin', False):
        return jsonify({'error': 'Unauthorized'}), 403
    conn  = get_db()
    posts = conn.execute('SELECT * FROM posts ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(p) for p in posts])


@app.route('/admin/delete-user/<int:user_id>', methods=['DELETE'])
def admin_delete_user(user_id):
    if not current_user.is_authenticated or not getattr(current_user, 'is_admin', False):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ============================================
# AI ROUTES
# ============================================

@app.route('/ai', methods=['POST'])
def ai_assistant():
    question = request.json.get('question', '').strip()
    if not question:
        return jsonify({'answer': 'Please ask a question!'})
    print(f'FlashAI question: {question}')
    answer = call_bedrock(
        messages=[{'role': 'user', 'content': question}],
        system_prompt=KSU_SYSTEM_PROMPT,
        max_tokens=512
    )
    print(f'FlashAI answer: {answer}')
    if answer:
        return jsonify({'answer': answer})
    return jsonify({'answer': 'FlashAI is offline right now. Try again soon!'})


@app.route('/summarize/<int:post_id>', methods=['POST'])
def summarize(post_id):
    conn = get_db()
    post = conn.execute('SELECT content FROM posts WHERE id = ?', (post_id,)).fetchone()
    conn.close()
    if not post:
        return jsonify({'summary': 'Post not found'})
    answer = call_bedrock(
        messages=[{'role': 'user', 'content':
            f'Summarize this KSU student post in 1-2 sentences: "{post["content"]}"'
        }],
        max_tokens=100
    )
    if answer:
        return jsonify({'summary': answer})
    return jsonify({'summary': 'Could not summarize right now.'})


@app.route('/check-duplicate', methods=['POST'])
def check_duplicate():
    new_q = request.json.get('content', '').strip()
    if not new_q:
        return jsonify({'is_duplicate': False})
    conn  = get_db()
    posts = conn.execute('SELECT content FROM posts ORDER BY created_at DESC LIMIT 20').fetchall()
    conn.close()
    if not posts:
        return jsonify({'is_duplicate': False, 'similar': None})
    existing = '\n'.join([f'- {p["content"][:100]}' for p in posts])
    answer = call_bedrock(
        messages=[{'role': 'user', 'content':
            f'New question: "{new_q}"\n\nExisting:\n{existing}\n\n'
            f'Is it very similar to any existing one? '
            f'Reply with JSON only: {{"is_duplicate": true/false, "similar": "matching question or null"}}'
        }],
        max_tokens=150
    )
    if answer:
        try:
            clean = answer.strip().replace('```json', '').replace('```', '').strip()
            return jsonify(json.loads(clean))
        except Exception:
            pass
    return jsonify({'is_duplicate': False, 'similar': None})



# ============================================
# FLASH SCORE LEADERBOARD
# Formula: (upvotes_received x 3) + (post_count x 2) + (reply_count x 1) + sentiment_bonus
# Sentiment bonus: +10 if >60% positive posts, -5 if >60% negative
# Normalized 0-100 via min-max normalization
# ============================================

@app.route('/leaderboard')
def leaderboard():
    conn = get_db()
    users = conn.execute('''
        SELECT DISTINCT username, user_id FROM posts
        WHERE anonymous=0 AND user_id IS NOT NULL AND username != 'Anonymous'
    ''').fetchall()

    scores = []
    for u in users:
        uid, username = u['user_id'], u['username']
        pd = conn.execute('''
            SELECT COUNT(*) as pc, COALESCE(SUM(upvotes),0) as uv,
                   SUM(CASE WHEN sentiment='positive' THEN 1 ELSE 0 END) as pos,
                   SUM(CASE WHEN sentiment='negative' THEN 1 ELSE 0 END) as neg
            FROM posts WHERE user_id=? AND anonymous=0
        ''', (uid,)).fetchone()
        rc = conn.execute('SELECT COUNT(*) as c FROM replies WHERE user_id=? AND anonymous=0', (uid,)).fetchone()['c']
        pc, uv, pos, neg = pd['pc'], pd['uv'], pd['pos'] or 0, pd['neg'] or 0
        sb = 0
        if pc > 0:
            if pos/pc > 0.6: sb = 10
            elif neg/pc > 0.6: sb = -5
        raw = (uv*3) + (pc*2) + (rc*1) + sb
        scores.append({'username':username,'raw_score':raw,'post_count':pc,'total_upvotes':uv,'reply_count':rc,'sentiment_bonus':sb})
    conn.close()
    if not scores: return jsonify([])
    vals = [s['raw_score'] for s in scores]
    mn, mx = min(vals), max(vals)
    for s in scores:
        s['flash_score'] = round((s['raw_score']-mn)/(mx-mn)*100,1) if mx!=mn else (100 if mx>0 else 0)
    scores.sort(key=lambda x: x['flash_score'], reverse=True)
    return jsonify(scores[:10])

# ============================================
# START
# ============================================
if __name__ == '__main__':
    init_db()
    app.run(debug=False)