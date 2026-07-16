"""
Streamlit Task Scheduler for GATE DA Preparation
- Task scheduling with priority management
- Google Calendar integration
- Study planning for GATE Data Analytics preparation
"""
import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime, timedelta, date
from dateutil import parser as dateparser
import json

# Google Calendar API imports
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

st.set_page_config(
    page_title="GATE DA Study Scheduler",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize database
def get_db_connection():
    conn = sqlite3.connect("tasks.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT,
            priority TEXT,
            completed INTEGER DEFAULT 0,
            synced_calendar INTEGER DEFAULT 0,
            calendar_event_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# Google Calendar API
SCOPES = ["https://www.googleapis.com/auth/calendar"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

def get_google_credentials():
    """Get valid user credentials from storage or run OAuth flow."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                st.error(f"Google credentials file not found: {CREDENTIALS_FILE}")
                st.info("Please download credentials.json from Google Cloud Console and place it in the app directory.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    return creds

def get_calendar_service():
    """Build and return Google Calendar service."""
    creds = get_google_credentials()
    if creds:
        return build("calendar", "v3", credentials=creds)
    return None

def create_calendar_event(service, task):
    """Create a Google Calendar event for a task."""
    event = {
        "summary": f"📚 GATE DA: {task['title']}",
        "description": f"{task['description'] or ''}\n\nPriority: {task['priority']}",
        "start": {
            "date": task["due_date"],
            "timeZone": "Asia/Kolkata",
        },
        "end": {
            "date": task["due_date"],
            "timeZone": "Asia/Kolkata",
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 30},
                {"method": "email", "minutes": 60},
            ],
        },
    }
    event = service.events().insert(calendarId="primary", body=event).execute()
    return event.get("id")

def update_calendar_event(service, event_id, task):
    """Update an existing Google Calendar event."""
    event = {
        "summary": f"📚 GATE DA: {task['title']}",
        "description": f"{task['description'] or ''}\n\nPriority: {task['priority']}",
        "start": {
            "date": task["due_date"],
            "timeZone": "Asia/Kolkata",
        },
        "end": {
            "date": task["due_date"],
            "timeZone": "Asia/Kolkata",
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 30},
                {"method": "email", "minutes": 60},
            ],
        },
    }
    service.events().update(calendarId="primary", eventId=event_id, body=event).execute()

def delete_calendar_event(service, event_id):
    """Delete a Google Calendar event."""
    service.events().delete(calendarId="primary", eventId=event_id).execute()

# Task operations
def add_task(title, description, due_date, priority):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tasks (title, description, due_date, priority) VALUES (?, ?, ?, ?)",
        (title, description, due_date, priority)
    )
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()
    return task_id

def get_all_tasks():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks ORDER BY CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 WHEN 'Low' THEN 3 END, due_date")
    tasks = cursor.fetchall()
    conn.close()
    return [dict(task) for task in tasks]

def get_task(task_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    task = cursor.fetchone()
    conn.close()
    return dict(task) if task else None

def update_task(task_id, title, description, due_date, priority, completed=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if completed is not None:
        cursor.execute(
            "UPDATE tasks SET title=?, description=?, due_date=?, priority=?, completed=? WHERE id=?",
            (title, description, due_date, priority, completed, task_id)
        )
    else:
        cursor.execute(
            "UPDATE tasks SET title=?, description=?, due_date=?, priority=? WHERE id=?",
            (title, description, due_date, priority, task_id)
        )
    conn.commit()
    conn.close()

def delete_task(task_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT calendar_event_id FROM tasks WHERE id = ?", (task_id,))
    task = cursor.fetchone()
    event_id = task["calendar_event_id"] if task else None
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return event_id

def mark_completed(task_id, completed=True):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET completed = ? WHERE id = ?", (1 if completed else 0, task_id))
    conn.commit()
    conn.close()

def get_tasks_for_calendar_sync():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE synced_calendar = 0 AND completed = 0")
    tasks = cursor.fetchall()
    conn.close()
    return [dict(task) for task in tasks]

def mark_synced(task_id, event_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET synced_calendar = 1, calendar_event_id = ? WHERE id = ?", (event_id, task_id))
    conn.commit()
    conn.close()

def update_synced_task(task_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT calendar_event_id FROM tasks WHERE id = ?", (task_id,))
    task = cursor.fetchone()
    conn.close()
    return task["calendar_event_id"] if task else None

# Priority helpers
PRIORITY_ORDER = {"High": 1, "Medium": 2, "Low": 3}
PRIORITY_COLORS = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}
PRIORITY_STYLE = {
    "High": "background-color: #ffebee; border-left: 4px solid #f44336;",
    "Medium": "background-color: #fff8e1; border-left: 4px solid #ffc107;",
    "Low": "background-color: #e8f5e9; border-left: 4px solid #4caf50;"
}

# GATE DA Study Topics (predefined)
GATE_DA_TOPICS = {
    "Probability & Statistics": ["Probability Distributions", "Hypothesis Testing", "Regression Analysis", "Statistical Inference"],
    "Linear Algebra": ["Matrices", "Eigenvalues & Eigenvectors", "Vector Spaces", "Linear Transformations"],
    "Calculus": ["Multivariable Calculus", "Optimization", "Differential Equations"],
    "Programming (Python/R)": ["Data Structures", "Pandas/NumPy", "Data Visualization", "ML Libraries"],
    "Machine Learning": ["Supervised Learning", "Unsupervised Learning", "Model Evaluation", "Feature Engineering"],
    "Databases & SQL": ["SQL Queries", "Database Design", "NoSQL Basics"],
    "Data Visualization": ["Matplotlib/Seaborn", "Tableau/PowerBI", "Dashboard Design"],
    "Big Data": ["Hadoop/Spark Basics", "MapReduce", "Data Warehousing"]
}

# Initialize database on startup
init_db()

# Sidebar
st.sidebar.title("📚 GATE DA Study Scheduler")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    ["📋 Task Manager", "📅 Calendar Sync", "📚 Study Topics", "📊 Progress Tracker", "⚙️ Settings"],
    index=0
)

# Google Calendar setup status
st.sidebar.markdown("---")
st.sidebar.subheader("📅 Google Calendar")
creds_status = "✅ Connected" if os.path.exists(TOKEN_FILE) else "❌ Not Connected"
st.sidebar.write(creds_status)

if st.sidebar.button("🔗 Connect Google Calendar"):
    service = get_calendar_service()
    if service:
        st.sidebar.success("Connected to Google Calendar!")
        st.rerun()

if st.sidebar.button("🔄 Sync Tasks to Calendar"):
    service = get_calendar_service()
    if service:
        unsynced_tasks = get_tasks_for_calendar_sync()
        if not unsynced_tasks:
            st.sidebar.info("No unsynced tasks found.")
        else:
            synced = 0
            for task in unsynced_tasks:
                try:
                    event_id = create_calendar_event(service, task)
                    mark_synced(task["id"], event_id)
                    synced += 1
                except Exception as e:
                    st.sidebar.error(f"Failed to sync '{task['title']}': {e}")
            if synced > 0:
                st.sidebar.success(f"Synced {synced} task(s) to Google Calendar!")
                st.rerun()

# Main content
if page == "📋 Task Manager":
    st.title("📋 Task Manager")
    st.markdown("Manage your GATE DA study tasks with priority scheduling.")

    # Add new task form
    with st.expander("➕ Add New Task", expanded=False):
        with st.form("add_task_form"):
            col1, col2 = st.columns(2)
            with col1:
                title = st.text_input("Task Title *", placeholder="e.g., Complete Probability Distributions")
                priority = st.selectbox("Priority *", ["High", "Medium", "Low"], index=1)
            with col2:
                due_date = st.date_input("Due Date *", value=date.today() + timedelta(days=7))
                category = st.selectbox("GATE DA Topic", list(GATE_DA_TOPICS.keys()) + ["Other"])
            description = st.text_area("Description", placeholder="Add details, sub-topics, resources...")
            submitted = st.form_submit_button("Add Task")
            if submitted:
                if title and due_date:
                    task_id = add_task(title, description, due_date.isoformat(), priority)
                    st.success(f"Task added! (ID: {task_id})")
                    st.rerun()
                else:
                    st.error("Title and Due Date are required!")

    # Filter and display tasks
    tasks = get_all_tasks()

    if not tasks:
        st.info("No tasks yet. Add your first GATE DA study task above! 📚")
    else:
        # Filters
        col1, col2, col3 = st.columns(3)
        with col1:
            filter_priority = st.multiselect("Filter by Priority", ["High", "Medium", "Low"], default=["High", "Medium", "Low"])
        with col2:
            filter_completed = st.selectbox("Show", ["All", "Pending", "Completed"])
        with col3:
            sort_by = st.selectbox("Sort by", ["Priority & Date", "Due Date", "Created Date"])

        # Apply filters
        filtered_tasks = tasks
        if filter_priority:
            filtered_tasks = [t for t in filtered_tasks if t["priority"] in filter_priority]
        if filter_completed == "Pending":
            filtered_tasks = [t for t in filtered_tasks if t["completed"] == 0]
        elif filter_completed == "Completed":
            filtered_tasks = [t for t in filtered_tasks if t["completed"] == 1]

        # Sort
        if sort_by == "Due Date":
            filtered_tasks.sort(key=lambda x: x["due_date"] or "9999-12-31")
        elif sort_by == "Created Date":
            filtered_tasks.sort(key=lambda x: x["created_at"] or "", reverse=True)

        st.markdown(f"**Showing {len(filtered_tasks)} of {len(tasks)} tasks**")

        # Display tasks
        for task in filtered_tasks:
            priority_color = PRIORITY_STYLE.get(task["priority"], "")
            priority_emoji = PRIORITY_COLORS.get(task["priority"], "")
            completed = task["completed"] == 1
            synced = task["synced_calendar"] == 1

            with st.container():
                title_style = "text-decoration: line-through; color: #888;" if completed else ""
                st.markdown(
                    f"""
                    <div style="{priority_color} padding: 15px; border-radius: 8px; margin-bottom: 10px;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div style="flex: 1;">
                                <h4 style="margin: 0; {title_style}">
                                    {priority_emoji} {task['title']}
                                    {' ✅' if completed else ''}
                                    {' 📅' if synced else ''}
                                </h4>
                                <p style="margin: 5px 0; color: #666;">{task['description'] or 'No description'}</p>
                                <small>Due: {task['due_date']} | Priority: {task['priority']} | Created: {task['created_at'][:10]}</small>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # Action buttons
                col1, col2, col3, col4 = st.columns([1, 1, 1, 3])
                with col1:
                    if st.button("✏️ Edit", key=f"edit_{task['id']}"):
                        st.session_state[f'editing_{task["id"]}'] = True
                        st.rerun()
                with col2:
                    if not completed:
                        if st.button("✅ Complete", key=f"complete_{task['id']}"):
                            mark_completed(task['id'], True)
                            st.rerun()
                    else:
                        if st.button("↩️ Undo", key=f"undo_{task['id']}"):
                            mark_completed(task['id'], False)
                            st.rerun()
                with col3:
                    if st.button("🗑️ Delete", key=f"delete_{task['id']}"):
                        event_id = delete_task(task['id'])
                        if event_id and os.path.exists(TOKEN_FILE):
                            service = get_calendar_service()
                            if service:
                                try:
                                    delete_calendar_event(service, event_id)
                                except:
                                    pass
                        st.rerun()
                with col4:
                    if task['synced_calendar']:
                        st.caption("📅 Synced to Google Calendar")
                    else:
                        st.caption("☁️ Not synced to Calendar")

                # Edit form
                if st.session_state.get(f'editing_{task["id"]}', False):
                    with st.form(f"edit_form_{task['id']}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            new_title = st.text_input("Title", value=task['title'], key=f"title_{task['id']}")
                            new_priority = st.selectbox("Priority", ["High", "Medium", "Low"],
                                                        index=["High", "Medium", "Low"].index(task['priority']), key=f"priority_{task['id']}")
                        with col2:
                            try:
                                default_date = dateparser.parse(task['due_date']).date() if task['due_date'] else date.today()
                            except:
                                default_date = date.today()
                            new_due_date = st.date_input("Due Date", value=default_date, key=f"date_{task['id']}")
                        new_description = st.text_area("Description", value=task['description'] or "", key=f"desc_{task['id']}")
                        col_save, col_cancel = st.columns(2)
                        with col_save:
                            if st.form_submit_button("💾 Save"):
                                update_task(task['id'], new_title, new_description, new_due_date.isoformat(), new_priority)
                                # Update calendar if synced
                                if task['synced_calendar'] and os.path.exists(TOKEN_FILE):
                                    service = get_calendar_service()
                                    if service and task['calendar_event_id']:
                                        try:
                                            update_calendar_event(service, task['calendar_event_id'], {
                                                'title': new_title, 'description': new_description,
                                                'due_date': new_due_date.isoformat(), 'priority': new_priority
                                            })
                                        except:
                                            pass
                                st.session_state[f'editing_{task["id"]}'] = False
                                st.rerun()
                        with col_cancel:
                            if st.form_submit_button("❌ Cancel"):
                                st.session_state[f'editing_{task["id"]}'] = False
                                st.rerun()

elif page == "📅 Calendar Sync":
    st.title("📅 Google Calendar Integration")
    st.markdown("Sync your study tasks with Google Calendar for reminders and scheduling.")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Connection Status")
        if os.path.exists(TOKEN_FILE):
            st.success("✅ Connected to Google Calendar")
            st.info("Your credentials are saved in token.json")

            if st.button("🔌 Disconnect"):
                os.remove(TOKEN_FILE)
                st.success("Disconnected from Google Calendar")
                st.rerun()
        else:
            st.warning("❌ Not connected to Google Calendar")
            st.markdown("""
            **Setup Instructions:**
            1. Go to [Google Cloud Console](https://console.cloud.google.com/)
            2. Create a new project or select existing one
            3. Enable **Google Calendar API**
            4. Create **OAuth 2.0 Client ID** (Desktop Application)
            5. Download `credentials.json` and place it in this folder
            6. Click "Connect" below
            """)
            if st.button("🔗 Connect Google Calendar"):
                service = get_calendar_service()
                if service:
                    st.success("Connected successfully!")
                    st.rerun()

    with col2:
        st.subheader("Sync Actions")
        if os.path.exists(TOKEN_FILE):
            tasks = get_all_tasks()
            unsynced = [t for t in tasks if t['synced_calendar'] == 0 and t['completed'] == 0]
            synced = [t for t in tasks if t['synced_calendar'] == 1]

            st.metric("Unsynced Tasks", len(unsynced))
            st.metric("Synced Tasks", len(synced))

            if unsynced:
                if st.button("☁️ Sync All Pending Tasks to Calendar"):
                    service = get_calendar_service()
                    if service:
                        progress = st.progress(0)
                        synced_count = 0
                        for i, task in enumerate(unsynced):
                            try:
                                event_id = create_calendar_event(service, task)
                                mark_synced(task['id'], event_id)
                                synced_count += 1
                            except Exception as e:
                                st.error(f"Failed to sync '{task['title']}': {e}")
                            progress.progress((i + 1) / len(unsynced))
                        st.success(f"Synced {synced_count} tasks to Google Calendar!")
                        st.rerun()

            if synced:
                if st.button("🔄 Update Synced Tasks in Calendar"):
                    service = get_calendar_service()
                    if service:
                        for task in synced:
                            if task['calendar_event_id']:
                                try:
                                    update_calendar_event(service, task['calendar_event_id'], task)
                                except Exception as e:
                                    st.error(f"Failed to update '{task['title']}': {e}")
                        st.success("Updated all synced tasks!")
                        st.rerun()

elif page == "📚 Study Topics":
    st.title("📚 GATE DA Study Topics")
    st.markdown("Track your progress through the GATE Data Analytics syllabus.")

    # Load progress from session state or localStorage
    if 'topic_progress' not in st.session_state:
        st.session_state.topic_progress = {}

    for topic, subtopics in GATE_DA_TOPICS.items():
        with st.expander(f"📖 {topic}", expanded=False):
            for subtopic in subtopics:
                key = f"{topic}_{subtopic}"
                completed = st.session_state.topic_progress.get(key, False)
                col1, col2 = st.columns([0.9, 0.1])
                with col1:
                    st.checkbox(subtopic, value=completed, key=f"check_{key}")
                with col2:
                    if st.button("📝", key=f"task_{key}", help="Create task for this topic"):
                        # Auto-create a task
                        due = date.today() + timedelta(days=7)
                        task_id = add_task(
                            f"Study: {subtopic}",
                            f"Cover {subtopic} under {topic} for GATE DA",
                            due.isoformat(),
                            "Medium"
                        )
                        st.success(f"Created task for {subtopic}!")
                        st.rerun()

elif page == "📊 Progress Tracker":
    st.title("📊 Progress Tracker")
    st.markdown("Monitor your GATE DA preparation progress.")

    tasks = get_all_tasks()

    if not tasks:
        st.info("No tasks to track yet. Add some tasks to see progress!")
    else:
        # Summary metrics
        total = len(tasks)
        completed = sum(1 for t in tasks if t['completed'] == 1)
        pending = total - completed
        high_priority = sum(1 for t in tasks if t['priority'] == 'High' and t['completed'] == 0)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Tasks", total)
        col2.metric("Completed", completed, f"{completed/total*100:.0f}%" if total > 0 else "0%")
        col3.metric("Pending", pending)
        col4.metric("High Priority Pending", high_priority, "🔴" if high_priority > 0 else "✅")

        # Progress bar
        if total > 0:
            st.progress(completed / total)

        # Priority distribution
        st.subheader("Priority Distribution")
        priority_counts = {"High": 0, "Medium": 0, "Low": 0}
        for t in tasks:
            if t['completed'] == 0:
                priority_counts[t['priority']] += 1

        df_priority = pd.DataFrame(list(priority_counts.items()), columns=["Priority", "Count"])
        st.bar_chart(df_priority.set_index("Priority"))

        # Upcoming deadlines
        st.subheader("📅 Upcoming Deadlines (Next 14 Days)")
        upcoming = []
        today = date.today()
        for t in tasks:
            if t['completed'] == 0 and t['due_date']:
                try:
                    due = dateparser.parse(t['due_date']).date()
                    if today <= due <= today + timedelta(days=14):
                        upcoming.append((due, t))
                except:
                    pass

        if upcoming:
            upcoming.sort(key=lambda x: x[0])
            for due, task in upcoming:
                days_left = (due - today).days
                urgency = "🔴" if days_left <= 2 else "🟡" if days_left <= 5 else "🟢"
                st.write(f"{urgency} **{task['title']}** - Due: {due} ({days_left} days) - {PRIORITY_COLORS[task['priority']]} {task['priority']}")
        else:
            st.info("No upcoming deadlines in the next 14 days.")

        # Weekly study plan
        st.subheader("📅 Weekly Study Plan")
        week_start = today - timedelta(days=today.weekday())
        week_days = [week_start + timedelta(days=i) for i in range(7)]

        for day in week_days:
            day_tasks = [t for t in tasks if t['due_date'] and dateparser.parse(t['due_date']).date() == day and t['completed'] == 0]
            with st.expander(f"{day.strftime('%A, %b %d')} ({len(day_tasks)} tasks)"):
                if day_tasks:
                    for t in day_tasks:
                        st.write(f"- {PRIORITY_COLORS[t['priority']]} **{t['title']}** ({t['priority']})")
                else:
                    st.write("No tasks scheduled. Add some study tasks!")

elif page == "⚙️ Settings":
    st.title("⚙️ Settings")

    st.subheader("📁 Data Management")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📥 Export Tasks (CSV)"):
            tasks = get_all_tasks()
            df = pd.DataFrame(tasks)
            csv = df.to_csv(index=False)
            st.download_button("Download CSV", csv, "gate_da_tasks.csv", "text/csv")
    with col2:
        if st.button("🗑️ Clear All Tasks"):
            if st.checkbox("I understand this will delete all tasks"):
                conn = get_db_connection()
                conn.execute("DELETE FROM tasks")
                conn.commit()
                conn.close()
                st.success("All tasks cleared!")
                st.rerun()

    st.subheader("📅 Google Calendar")
    st.write("Credentials file:", CREDENTIALS_FILE)
    st.write("Token file:", TOKEN_FILE)

    st.subheader("ℹ️ About")
    st.markdown("""
    **GATE DA Study Scheduler** - A Streamlit application for GATE Data Analytics preparation.

    Features:
    - Task scheduling with priority management
    - Google Calendar integration for reminders
    - Progress tracking and study planning
    - Predefined GATE DA syllabus topics

    Built with Streamlit, SQLite, and Google Calendar API.
    """)

# Footer
st.sidebar.markdown("---")
st.sidebar.caption("GATE DA Study Scheduler v1.0")
st.sidebar.caption("Built with Streamlit 🚀")
