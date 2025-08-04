from flask import Flask, request, render_template_string
import os
import json
from datetime import datetime
from collections import defaultdict
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

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

@app.route('/')
def view_logs():
    # Get the current page date from the query parameter (default to today if not present)
    page_date_str = request.args.get('date', (datetime.now()).strftime('%Y-%m-%d'))
    page_date = datetime.strptime(page_date_str, '%Y-%m-%d').date()
    
    # Connect to the database
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Query to get available dates (for pagination)
        cursor.execute(
            "SELECT DISTINCT DATE(created_at) as log_date FROM tezpul_chat_histories ORDER BY log_date DESC LIMIT 5"
        )
        available_dates = [row['log_date'] for row in cursor.fetchall()]
        
        # If no dates found or requested date not in available dates, use the most recent date
        if not available_dates or page_date not in available_dates:
            page_date = available_dates[0] if available_dates else datetime.now().date()
        
        # Query to get logs for the selected date, grouped by session_id
        cursor.execute(
            """
            SELECT session_id, message, created_at 
            FROM tezpul_chat_histories 
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
                <title>Tezpul Chat Logs</title>
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
                </style>
            </head>
            <body>
                <h1>Tezpul Chat Logs for {{ page_date }}</h1>
                
                <!-- Pagination links at the top -->
                <div class="pagination">
                    {% for date in pagination_dates %}
                        {% if date == page_date %}
                            <strong>{{ date }}</strong>
                        {% else %}
                            <a href="/?date={{ date }}">{{ date }}</a>
                        {% endif %}
                    {% endfor %}
                </div>

                <!-- Log content -->
                <div class="logs">{{ log_content|safe }}</div>
                
            </body>
        </html>
    """, log_content=log_content, page_date=page_date, pagination_dates=pagination_dates)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8082)
