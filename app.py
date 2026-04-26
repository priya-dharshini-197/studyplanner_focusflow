from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from collections import Counter
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "supersecretkey"


# -------------------- DB --------------------
def get_db():
    conn = sqlite3.connect("/tmp/database.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        task TEXT,
        completed INTEGER DEFAULT 0,
        deadline TEXT
    )
    """)

    # ✅ Add completed_at if missing
    cur.execute("PRAGMA table_info(tasks)")
    cols = [col[1] for col in cur.fetchall()]
    if "completed_at" not in cols:
        cur.execute("ALTER TABLE tasks ADD COLUMN completed_at TEXT")

    conn.commit()
    conn.close()


init_db()


# -------------------- AUTH --------------------
def login_required():
    return 'user' in session


# -------------------- HOME --------------------
@app.route('/')
def home():
    if not login_required():
        return redirect(url_for('login'))

    conn = get_db()
    cur = conn.cursor()

    # tasks
    cur.execute("SELECT id, task, completed, deadline FROM tasks WHERE user=?", (session['user'],))
    tasks = cur.fetchall()

    # stats
    total = cur.execute("SELECT COUNT(*) FROM tasks WHERE user=?", (session['user'],)).fetchone()[0]
    completed = cur.execute("SELECT COUNT(*) FROM tasks WHERE user=? AND completed=1", (session['user'],)).fetchone()[0]

    # 📊 trend data
    cur.execute("""
        SELECT deadline FROM tasks 
        WHERE user=? AND completed=1 AND deadline IS NOT NULL
    """, (session['user'],))

    dates = [row['deadline'] for row in cur.fetchall()]
    count = Counter(dates)

    sorted_dates = sorted(count.items())
    labels = [d[0] for d in sorted_dates]
    values = [d[1] for d in sorted_dates]

    # 🔥 STREAK LOGIC (THIS IS STEP 3)
    cur.execute("""
        SELECT completed_at FROM tasks 
        WHERE user=? AND completed=1 AND completed_at IS NOT NULL
    """, (session['user'],))

    completed_dates = [row['completed_at'] for row in cur.fetchall()]
    conn.close()

    completed_dates = sorted(set(completed_dates), reverse=True)

    streak = 0
    today = datetime.now().date()

    for i, date_str in enumerate(completed_dates):
        date = datetime.strptime(date_str, "%Y-%m-%d").date()

        if i == 0:
            if date not in [today, today - timedelta(days=1)]:
                break
        else:
            prev = datetime.strptime(completed_dates[i-1], "%Y-%m-%d").date()
            if (prev - date).days != 1:
                break

        streak += 1

    return render_template(
        'index.html',
        tasks=tasks,
        total=total,
        completed=completed,
        labels=labels,
        values=values,
        streak=streak
    )


# -------------------- REGISTER --------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    success = None

    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()

        if not username or not password:
            error = "All fields are required"
        elif len(password) < 5:
            error = "Password must be at least 5 characters"
        else:
            conn = get_db()
            cur = conn.cursor()

            cur.execute("SELECT * FROM users WHERE username=?", (username,))
            if cur.fetchone():
                error = "Username already exists"
            else:
                hashed = generate_password_hash(password)
                cur.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed))
                conn.commit()
                success = "Account created! Please login."

            conn.close()

    return render_template('register.html', error=error, success=success)


# -------------------- LOGIN --------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None

    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()

        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT * FROM users WHERE username=?", (username,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user'] = username
            return redirect(url_for('home'))
        else:
            error = "Invalid username or password"

    return render_template('login.html', error=error)


# -------------------- LOGOUT --------------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# -------------------- ADD --------------------
@app.route('/add', methods=['POST'])
def add():
    if not login_required():
        return redirect(url_for('login'))

    task = request.form.get('task').strip()
    deadline = request.form.get('deadline')

    if not task:
        return redirect(url_for('home'))

    conn = get_db()
    cur = conn.cursor()

    cur.execute("INSERT INTO tasks (user, task, deadline) VALUES (?, ?, ?)",
                (session['user'], task, deadline))

    conn.commit()
    conn.close()

    return redirect(url_for('home'))


# -------------------- COMPLETE --------------------
@app.route('/complete/<int:id>')
def complete(id):
    if not login_required():
        return redirect(url_for('login'))

    conn = get_db()
    cur = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")

    cur.execute("""
        UPDATE tasks 
        SET completed=1, completed_at=? 
        WHERE id=? AND user=?
    """, (today, id, session['user']))

    conn.commit()
    conn.close()

    return redirect(url_for('home'))


# -------------------- DELETE --------------------
@app.route('/delete/<int:id>')
def delete(id):
    if not login_required():
        return redirect(url_for('login'))

    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM tasks WHERE id=? AND user=?", (id, session['user']))

    conn.commit()
    conn.close()

    return redirect(url_for('home'))


# -------------------- RUN --------------------
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=10000)
