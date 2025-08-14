from flask import Flask, request, render_template_string, redirect, url_for, session
import os
import json
from datetime import datetime
from collections import defaultdict
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "supersecretkey")

# Simple user store for demonstration
USERS = {
    "tezpul_user": {
        "password": "tezpulpass",
        "access": "tezpul",
    },
    "anydoc_user": {
        "password": "anydocpass",
        "access": "anydoc",
    },
}

def get_db_connection():
    """Create a database connection using environment variables"""
    conn = psycopg2.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        port=os.environ.get('DB_PORT', '5432'),
        database=os.environ.get('DB_NAME', 'postgres'),
        user=os.environ.get('DB_USER', 'postgres'),
        password=os.environ.get('DB_PASSWORD', 'postgres')
    )
    return conn

@app.route('/chat-logs', methods=['GET', 'POST'])
def login():
    # If already logged in, redirect based on access
    if 'username' in session:
        access = USERS.get(session['username'], {}).get('access')
        if access == 'tezpul':
            return redirect(url_for('view_tezpul_logs'))
        elif access == 'anydoc':
            return redirect(url_for('view_anydoc_logs'))
    error = None
    if request.method == 'POST':
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = USERS.get(username)
        if user and user["password"] == password:
            session['username'] = username
            if user["access"] == "tezpul":
                return redirect(url_for("view_tezpul_logs"))
            elif user["access"] == "anydoc":
                return redirect(url_for("view_anydoc_logs"))
        else:
            error = "Invalid username or password"
    return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Login - Tezpul/Anydoc Logs</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; background: #f8f9fa; }
                .login-box {
                    width: 350px;
                    margin: 60px auto;
                    background: white;
                    padding: 30px 25px;
                    border-radius: 8px;
                    box-shadow: 0 2px 16px rgba(0,0,0,0.09);
                }
                .login-box h2 { margin-bottom: 20px; text-align: center; }
                .login-box input[type=text], .login-box input[type=password] {
                    width: 100%; padding: 10px; margin: 10px 0 20px;
                    border: 1px solid #ccc; border-radius: 4px;
                }
                .login-box input[type=submit] {
                    width: 100%; background: #1890ff; color: white;
                    border: none; padding: 10px; border-radius: 4px;
                    font-size: 1em; cursor: pointer;
                }
                .login-box .error { color: red; margin-bottom: 15px; text-align: center; }
            </style>
        </head>
        <body>
            <div class="login-box">
                <h2>Login</h2>
                {% if error %}
                    <div class="error">{{ error }}</div>
                {% endif %}
                <form method="POST">
                    <label for="username">Username:</label>
                    <input type="text" id="username" name="username" required>
                    <label for="password">Password:</label>
                    <input type="password" id="password" name="password" required>
                    <input type="submit" value="Login">
                </form>
                <p><strong>Demo Users:</strong></p>
                <ul>
                    <li><b>tezpul_user</b> : tezpulpass (Tezpul logs)</li>
                    <li><b>anydoc_user</b> : anydocpass (Anydoc logs)</li>
                </ul>
            </div>
        </body>
        </html>
    """, error=error)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

def require_login(access_type):
    def decorator(f):
        def wrapper(*args, **kwargs):
            username = session.get('username')
            if not username or USERS.get(username, {}).get('access') != access_type:
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

@app.route('/tezpul-logs')
@require_login('tezpul')
def view_tezpul_logs():
    return _render_logs_view(
        table_name="tezpul_chat_histories",
        page_title="Tezpul Chat Logs"
    )

@app.route('/anydoc-logs')
@require_login('anydoc')
def view_anydoc_logs():
    return _render_logs_view(
        table_name="anydoc_chat_histories",
        page_title="Anydoc Chat Logs"
    )

def _render_logs_view(table_name, page_title):
    # Get the current page date from the query parameter (default to today if not present)
    page_date_str = request.args.get('date', (datetime.now()).strftime('%Y-%m-%d'))
    page_date = datetime.strptime(page_date_str, '%Y-%m-%d').date()

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Query to get available dates (for pagination)
        cursor.execute(
            f"SELECT DISTINCT DATE(created_at) as log_date FROM {table_name} ORDER BY log_date DESC LIMIT 5"
        )
        available_dates = [row['log_date'] for row in cursor.fetchall()]

        # If no dates found or requested date not in available dates, use the most recent date
        if not available_dates or page_date not in available_dates:
            page_date = available_dates[0] if available_dates else datetime.now().date()

        # Query to get logs for the selected date, grouped by session_id
        cursor.execute(
            f"""
            SELECT session_id, message, created_at 
            FROM {table_name} 
            WHERE DATE(created_at) = %s
            ORDER BY session_id, created_at
            """,
            (page_date,)
        )

        logs = cursor.fetchall()
        cursor.close()
        conn.close()

        # Group logs by session_id
        sessions = defaultdict(list)
        for log in logs:
            sessions[log['session_id']].append(log)

        # Process logs for HTML display
        html_logs = []
        for session_id, session_logs in sessions.items():
            html_logs.append(f'<div class="session-header">Session ID: {session_id}</div>')

            for log in session_logs:
                try:
                    timestamp = log['created_at'].strftime('%Y-%m-%d %H:%M:%S')
                    message_data = log['message']

                    # Check if message is already a dict or needs to be parsed from JSON string
                    if isinstance(message_data, str):
                        message_data = json.loads(message_data)

                    message_type = message_data.get('type', 'unknown')
                    content = message_data.get('content', '')

                    # Format based on message type
                    if message_type == 'human':
                        html_logs.append(f'<div class="human"><span class="timestamp">{timestamp}</span><br><strong>Human:</strong><br>{content}</div>')
                    elif message_type == 'ai':
                        html_logs.append(f'<div class="ai"><span class="timestamp">{timestamp}</span><br><strong>AI:</strong><br>{content}</div>')
                    else:
                        html_logs.append(f'<div class="unknown"><span class="timestamp">{timestamp}</span><br><strong>Unknown ({message_type}):</strong><br>{content}</div>')

                except Exception as e:
                    html_logs.append(f'<div class="error">Error parsing log: {str(e)}</div>')

            html_logs.append('<hr>')

        # Join the HTML logs
        log_content = '\n'.join(html_logs)

        # Get dates for pagination
        pagination_dates = available_dates

    except Exception as e:
        # Handle database connection errors
        log_content = f"<div class='error'>Error connecting to database: {str(e)}</div>"
        pagination_dates = [page_date]

    # Render the log content in a HTML template with pagination links
    return render_template_string("""
        <!DOCTYPE html>
        <html>
            <head>
                <title>{{ page_title }} for {{ page_date }}</title>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <!-- Refresh page every 60 seconds -->
                <meta http-equiv="refresh" content="60">
                <style>
                    body { 
                        font-family: Arial, sans-serif; 
                        margin: 20px; 
                        line-height: 1.6;
                    }
                    .pagination { 
                        margin: 20px 0; 
                        padding: 10px;
                        background-color: #f8f9fa;
                        border-radius: 5px;
                    }
                    .pagination a, .pagination strong { 
                        margin-right: 10px; 
                        text-decoration: none;
                        padding: 5px 10px;
                    }
                    .pagination a {
                        background-color: #e9ecef;
                        border-radius: 3px;
                    }
                    .human { 
                        background-color: #e6f7ff; 
                        padding: 15px; 
                        margin: 10px 0; 
                        border-radius: 5px; 
                        border-left: 4px solid #1890ff;
                    }
                    .ai { 
                        background-color: #f0f0f0; 
                        padding: 15px; 
                        margin: 10px 0; 
                        border-radius: 5px;
                        border-left: 4px solid #52c41a;
                    }
                    .unknown, .error { 
                        background-color: #fff2e8; 
                        padding: 15px; 
                        margin: 10px 0; 
                        border-radius: 5px;
                        border-left: 4px solid #fa541c;
                    }
                    .timestamp {
                        color: #666;
                        font-size: 0.8em;
                    }
                    .session-header {
                        font-weight: bold;
                        font-size: 1.2em;
                        margin-top: 20px;
                        padding: 10px;
                        background-color: #fafafa;
                        border-bottom: 1px solid #ddd;
                    }
                    hr {
                        margin: 30px 0;
                        border: 0;
                        border-top: 1px dashed #ddd;
                    }
                    .logout-link {
                        margin-top: 20px;
                        text-align: right;
                    }
                    .logout-link a {
                        color: #1890ff;
                        text-decoration: none;
                        font-weight: bold;
                    }
                </style>
            </head>
            <body>
                <h1>{{ page_title }} for {{ page_date }}</h1>
                
                <div class="logout-link">
                    <a href="{{ url_for('logout') }}">Logout</a>
                </div>
                <!-- Pagination links at the top -->
                <div class="pagination">
                    {% for date in pagination_dates %}
                        {% if date == page_date %}
                            <strong>{{ date }}</strong>
                        {% else %}
                            <a href="?date={{ date }}">{{ date }}</a>
                        {% endif %}
                    {% endfor %}
                </div>

                <!-- Log content -->
                <div class="logs">{{ log_content|safe }}</div>
                
            </body>
        </html>
    """, log_content=log_content, page_date=page_date, pagination_dates=pagination_dates, page_title=page_title)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
