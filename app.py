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

def is_google_connected():
    """Check if Google Calendar is connected via local file or Streamlit Secrets."""
    return os.path.exists(TOKEN_FILE) or ("google" in st.secrets and "token" in st.secrets["google"])

def get_google_credentials():
    """Get valid user credentials from storage, environment variables, or Streamlit Secrets."""
    creds = None
    
    # 1. Try to load token.json from local file or Streamlit Secrets
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    elif "google" in st.secrets and "token" in st.secrets["google"]:
        try:
            token_info = json.loads(st.secrets["google"]["token"])
            creds = Credentials.from_authorized_user_info(token_info, SCOPES)
        except Exception as e:
            st.error(f"Failed to load token from Streamlit Secrets: {e}")
            
    # 2. If credentials are not valid (expired, etc.), refresh or recreate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                st.error(f"Failed to refresh Google credentials: {e}")
                creds = None
                
        if not creds or not creds.valid:
            # Check Streamlit Secrets for credentials first
            if "google" in st.secrets and "credentials" in st.secrets["google"]:
                try:
                    creds_info = json.loads(st.secrets["google"]["credentials"])
                    flow = InstalledAppFlow.from_client_config(creds_info, SCOPES)
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    st.error(f"Failed to run OAuth flow with Secrets credentials: {e}")
                    return None
            # Otherwise fall back to local files
            elif os.path.exists(CREDENTIALS_FILE):
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
            else:
                st.error("Google credentials not found in local files or Streamlit Secrets.")
                st.info("Please set 'google.credentials' and 'google.token' in Streamlit Secrets, or place credentials.json in the local app directory.")
                return None
        
        # Save token.json locally if possible (will fail safely in read-only environments)
        try:
            with open(TOKEN_FILE, "w") as token:
                token.write(creds.to_json())
        except Exception:
            pass
            
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

# GATE DA Study Topics (Predefined & matched with the official IIT Guwahati syllabus)
GATE_DA_TOPICS = {
    "Probability & Statistics": [
        "Permutations & Combinations (Counting)",
        "Probability Axioms, Sample Space, Events",
        "Independent & Mutually Exclusive Events",
        "Marginal, Conditional & Joint Probability",
        "Bayes' Theorem",
        "Random Variables (Discrete & Continuous)",
        "Probability Mass & Density Functions (PMF & PDF)",
        "Cumulative Distribution Functions (CDF)",
        "Expectation, Variance & Conditional Expectation",
        "Mean, Median, Mode & Standard Deviation",
        "Correlation and Covariance"
    ],
    "Linear Algebra": [
        "Matrices & Determinants",
        "Systems of Linear Equations",
        "Eigenvalues & Eigenvectors",
        "LU Decomposition",
        "Singular Value Decomposition (SVD)"
    ],
    "Calculus & Optimization": [
        "Limits, Continuity & Differentiability",
        "Maxima & Minima (Single Variable)",
        "Taylor Series",
        "Functions of Multiple Variables (Partial Derivatives, Gradient)",
        "Unconstrained Optimization (Local/Global Minima)",
        "Constrained Optimization (Lagrange Multipliers)",
        "Gradient Descent Method"
    ],
    "Programming, Data Structures & Algorithms": [
        "Programming in Python (Syntax, Control Flow, Functions)",
        "Stacks, Queues, and Linked Lists",
        "Trees (Binary Trees, BSTs) and Hash Tables",
        "Search Algorithms (Linear & Binary Search)",
        "Sorting Algorithms (Selection, Bubble, Insertion, Merge, Quick Sort)",
        "Graph Theory (Basic Traversals: BFS, DFS)",
        "Graph Algorithms (Shortest Path: Dijkstra)"
    ],
    "Database Management & Warehousing": [
        "ER-Model (Entities, Relationships, Attributes)",
        "Relational Model (Relational Algebra, Tuple Calculus)",
        "SQL (Queries, Joins, Subqueries)",
        "Integrity Constraints & Normal Forms (1NF, 2NF, 3NF, BCNF)",
        "File Organization & Indexing (B/B+ Trees)",
        "Data Preprocessing (Normalization, Discretization, Sampling, Compression)",
        "Data Warehousing & Multidimensional Modeling (Schema, Concept Hierarchies)"
    ],
    "Machine Learning": [
        "Supervised Learning: Regression (Linear, Ridge)",
        "Supervised Learning: Classification (Logistic Regression, k-NN, Naive Bayes)",
        "Linear Discriminant Analysis (LDA)",
        "Support Vector Machines (SVM)",
        "Decision Trees & Random Forests",
        "Bias-Variance Trade-off",
        "Model Evaluation & Cross-validation (LOO, k-fold)",
        "Multi-Layer Perceptrons (MLPs) & Feed-Forward Neural Networks",
        "Unsupervised Learning: Clustering (k-means, k-medoids, Hierarchical)",
        "Dimensionality Reduction: Principal Component Analysis (PCA)"
    ],
    "Artificial Intelligence (AI)": [
        "Uninformed Search (BFS, DFS, Depth-limited, Iterative Deepening)",
        "Informed Search (A*, Greedy Best-First)",
        "Adversarial Search (Minimax, Alpha-beta pruning)",
        "Propositional & Predicate Logic (Syntax, Semantics, Inference)",
        "Reasoning under Uncertainty (Conditional Independence)",
        "Bayesian Networks (Exact inference via variable elimination)",
        "Approximate Inference via Sampling"
    ]
}

# GATE DA Previous Year Questions Database (2024-2026)
GATE_DA_PYQS = [
    {
        "id": 1,
        "year": 2024,
        "subject": "Probability & Statistics",
        "type": "MCQ",
        "question": r"Let $X$ be a Poisson random variable with parameter $\lambda$. If $P(X = 0) = 0.2$, what is the variance of $X$?",
        "options": [r"a) $\ln 5$", r"b) $\ln 2$", "c) 5", "d) 2"],
        "answer": r"a) $\ln 5$",
        "explanation": r"""For a Poisson random variable $X$, the probability mass function is:
$$P(X = k) = \frac{e^{-\lambda} \lambda^k}{k!}$$

Given $P(X = 0) = 0.2$:
$$P(X = 0) = \frac{e^{-\lambda} \lambda^0}{0!} = e^{-\lambda} = 0.2 = \frac{1}{5}$$

Taking the natural logarithm on both sides:
$$\ln(e^{-\lambda}) = \ln(1/5) \implies -\lambda = -\ln(5) \implies \lambda = \ln(5)$$

Since the variance of a Poisson random variable is equal to its parameter $\lambda$:
$$\text{Var}(X) = \lambda = \ln 5$$"""
    },
    {
        "id": 2,
        "year": 2024,
        "subject": "Linear Algebra",
        "type": "MCQ",
        "question": r"Let $M$ be a $3\times3$ real matrix with eigenvalues $2$, $1+i$, and $1-i$. What is the determinant of $M$?",
        "options": ["a) 2", "b) 4", "c) 0", r"d) $2+2i$"],
        "answer": "b) 4",
        "explanation": r"""The determinant of any square matrix $M$ is equal to the product of its eigenvalues.

Given eigenvalues:
$$\lambda_1 = 2, \quad \lambda_2 = 1+i, \quad \lambda_3 = 1-i$$

Calculate the product:
$$\det(M) = \lambda_1 \cdot \lambda_2 \cdot \lambda_3$$
$$\det(M) = 2 \cdot (1+i) \cdot (1-i)$$

Since $(1+i)(1-i) = 1^2 - i^2 = 1 - (-1) = 2$:
$$\det(M) = 2 \cdot 2 = 4$$"""
    },
    {
        "id": 3,
        "year": 2024,
        "subject": "Machine Learning",
        "type": "MCQ",
        "question": r"Consider the following statements regarding Linear Regression and Logistic Regression:

I. Linear Regression assumes a linear relationship between the input variables and the continuous output.
II. Logistic Regression outputs a probability value bounded between 0 and 1.

Which of the statements is/are correct?",
        "options": ["a) Only I", "b) Only II", "c) Both I and II", "d) Neither I nor II"],
        "answer": "c) Both I and II",
        "explanation": r"""- **Statement I is correct**: Linear Regression models the relationship between a continuous dependent variable $y$ and independent variables $X$ as a linear equation: $y = \beta_0 + \beta_1 x_1 + \dots + \beta_p x_p + \epsilon$.
- **Statement II is correct**: Logistic Regression uses the logistic (sigmoid) function to map the linear predictor output to a probability value between $0$ and $1$:
$$P(y=1|x) = \sigma(z) = \frac{1}{1 + e^{-z}}$$
where $z = \beta^T x$. Thus, both statements are correct."""
    },
    {
        "id": 4,
        "year": 2024,
        "subject": "Database Management & Warehousing",
        "type": "MCQ",
        "question": r"Suppose a relation schema $R(A, B, C, D)$ has the functional dependencies $A \rightarrow B$ and $B \rightarrow C$. What is the highest normal form that relation $R$ satisfies?",
        "options": ["a) 1NF", "b) 2NF", "c) 3NF", "d) BCNF"],
        "answer": "a) 1NF",
        "explanation": r"""To find the highest normal form, we first determine the candidate keys of $R(A, B, C, D)$:
1. Find the closure of attributes. Attribute $D$ does not appear on the right side of any functional dependency, so it must be part of any candidate key.
2. Let's find $(AD)^+$:
   - $(AD)^+ = \{A, D\}$ (reflexivity)
   - Since $A \rightarrow B$, $(AD)^+ = \{A, B, D\}$
   - Since $B \rightarrow C$, $(AD)^+ = \{A, B, C, D\}$
3. Since $(AD)^+$ contains all attributes, $AD$ is the candidate key.

Identify Prime and Non-Prime attributes:
- **Prime attributes** (part of any candidate key): $\{A, D\}$
- **Non-prime attributes** (not part of any candidate key): $\{B, C\}$

Check for 2NF (No partial dependency):
- A functional dependency $X \rightarrow Y$ is a partial dependency if $X$ is a proper subset of a candidate key and $Y$ is a non-prime attribute.
- For $A \rightarrow B$: $A$ is a proper subset of the candidate key $AD$, and $B$ is a non-prime attribute. This is a **partial dependency**.
- Since $R$ has a partial dependency, it is **not in 2NF**.

Since it does not satisfy 2NF but satisfies 1NF (all attributes are atomic), the highest normal form satisfied is **1NF**."""
    },
    {
        "id": 5,
        "year": 2025,
        "subject": "Programming, Data Structures & Algorithms",
        "type": "MCQ",
        "question": r"Which of the following sorting algorithms has a worst-case time complexity of $O(n \log n)$?",
        "options": ["a) Bubble Sort", "b) Quick Sort", "c) Merge Sort", "d) Insertion Sort"],
        "answer": "c) Merge Sort",
        "explanation": r"""Let's analyze the worst-case time complexities of each algorithm:
- **Bubble Sort**: $O(n^2)$ (when the array is sorted in reverse order).
- **Insertion Sort**: $O(n^2)$ (when the array is sorted in reverse order).
- **Quick Sort**: $O(n^2)$ (when the pivot consistently divides the array into unbalanced partitions, e.g., if the array is already sorted and we choose the first or last element as pivot).
- **Merge Sort**: $O(n \log n)$ in all cases (best, average, and worst) because it always divides the array into two equal halves and takes $O(n)$ time to merge them.

Therefore, **Merge Sort** is the correct answer."""
    },
    {
        "id": 6,
        "year": 2025,
        "subject": "Artificial Intelligence (AI)",
        "type": "MCQ",
        "question": r"In informed search, if a heuristic function $h(n)$ is admissible, what does it guarantee for the $A^*$ search algorithm?",
        "options": ["a) It will always find the optimal solution if one exists.", "b) It will use less memory than BFS.", "c) It will always expand fewer nodes than Greedy Best-First Search.", "d) It will run in linear time."],
        "answer": "a) It will always find the optimal solution if one exists.",
        "explanation": r"""- A heuristic function $h(n)$ is **admissible** if it never overestimates the actual cost to reach the goal node from node $h(n)$, i.e., $h(n) \le h^*(n)$ for all $n$, where $h^*(n)$ is the true optimal cost.
- If the heuristic function is admissible, $A^*$ search is guaranteed to return the **optimal path/solution** (the path with the lowest cost) to the goal node, assuming a solution exists.

Thus, statement (a) is correct."""
    },
    {
        "id": 7,
        "year": 2026,
        "subject": "Calculus & Optimization",
        "type": "MCQ",
        "question": r"Consider the function $f(x) = x^3 - 3x^2 + 2$. What is the local minimum of this function?",
        "options": [r"a) $x = 0$", r"b) $x = 2$", r"c) $x = -2$", r"d) $x = 1$"],
        "answer": r"b) $x = 2$",
        "explanation": r"""To find the local minimum, we follow these steps:
1. Find the first derivative $f'(x)$ and set it to $0$:
   $$f'(x) = 3x^2 - 6x = 0$$
   $$3x(x - 2) = 0 \implies x = 0 \text{ or } x = 2$$
   These are our critical points.

2. Find the second derivative $f''(x)$:
   $$f''(x) = 6x - 6$$

3. Evaluate the second derivative at the critical points:
   - At $x = 0$: $f''(0) = 6(0) - 6 = -6 < 0$. Since $f''(0) < 0$, $x = 0$ is a local maximum.
   - At $x = 2$: $f''(2) = 6(2) - 6 = 6 > 0$. Since $f''(2) > 0$, $x = 2$ is a local minimum.

Therefore, the local minimum occurs at $x = 2$."""
    },
    {
        "id": 8,
        "year": 2025,
        "subject": "Probability & Statistics",
        "type": "MCQ",
        "question": r"Consider a fair six-sided die. What is the expected number of rolls needed to get the number 6 for the first time?",
        "options": ["a) 6", "b) 36", "c) 5", "d) 1"],
        "answer": "a) 6",
        "explanation": r"""Let $X$ be the number of rolls needed to get the first $6$.
- This scenario is modeled by a **Geometric Distribution**, where we perform independent Bernoulli trials until the first success.
- The probability of success (rolling a $6$) in a single trial is $p = \frac{1}{6}$.
- The expected value (mean) of a geometrically distributed random variable $X$ representing the number of trials up to and including the first success is:
$$E[X] = \frac{1}{p}$$

Substituting $p = \frac{1}{6}$:
$$E[X] = \frac{1}{1/6} = 6$$

Thus, the expected number of rolls is $6$."""
    },
    {
        "id": 9,
        "year": 2026,
        "subject": "Linear Algebra",
        "type": "MCQ",
        "question": r"Let $A$ be an idempotent matrix, meaning $A^2 = A$. What are the only possible eigenvalues of $A$?",
        "options": ["a) 0 and 1", "b) 1 and -1", "c) Any real number", "d) 0 and -1"],
        "answer": "a) 0 and 1",
        "explanation": r"""Let $\lambda$ be an eigenvalue of $A$ and let $v$ be its corresponding non-zero eigenvector. By definition:
$$Av = \lambda v$$

Multiply both sides by $A$:
$$A(Av) = A(\lambda v)$$
$$A^2 v = \lambda (Av)$$

Since $A^2 = A$ and $Av = \lambda v$:
$$Av = \lambda (\lambda v)$$
$$\lambda v = \lambda^2 v$$
$$(\lambda^2 - \lambda) v = 0$$

Since $v$ is a non-zero eigenvector ($v \neq 0$), we must have:
$$\lambda^2 - \lambda = 0 \implies \lambda(\lambda - 1) = 0$$
$$\lambda = 0 \quad \text{or} \quad \lambda = 1$$

Thus, the only possible eigenvalues of an idempotent matrix are $0$ and $1$."""
    },
    {
        "id": 10,
        "year": 2026,
        "subject": "Machine Learning",
        "type": "MCQ",
        "question": r"In Support Vector Machines (SVM), what is the effect of increasing the regularization parameter $C$ (soft margin parameter) in the objective function?",
        "options": ["a) It allows more margin violations, leading to a wider margin.", "b) It penalizes margin violations more heavily, leading to a narrower margin.", "c) It makes the decision boundary completely linear.", "d) It has no effect on the margin width."],
        "answer": "b) It penalizes margin violations more heavily, leading to a narrower margin.",
        "explanation": r"""The SVM optimization objective (soft margin formulation) is:
$$\min_{w, b, \xi} \frac{1}{2} \|w\|^2 + C \sum_{i=1}^{n} \xi_i$$
subject to $y_i(w^T x_i + b) \ge 1 - \xi_i$ and $\xi_i \ge 0$.

Here:
- The parameter $C$ acts as a penalty weight for training classification violations ($\xi_i$).
- **If $C$ is large**: The objective function penalizes margin violations heavily. The optimization will focus on making the slack variables $\xi_i$ as close to $0$ as possible to avoid high penalty, resulting in a **narrower margin** that fits the training data more tightly (high variance, risk of overfitting).
- **If $C$ is small**: The optimization tolerates more misclassifications/violations in favor of finding a **wider margin** (high bias, risk of underfitting).

Therefore, increasing $C$ penalizes violations more heavily and leads to a narrower margin."""
    }
]

# Initialize database on startup
init_db()

# Sidebar
st.sidebar.title("📚 GATE DA Study Scheduler")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    ["📋 Task Manager", "📅 Calendar Sync", "📚 Study Topics", "📝 PYQ Practice", "📊 Progress Tracker", "⚙️ Settings"],
    index=0
)

# Google Calendar setup status
st.sidebar.markdown("---")
st.sidebar.subheader("📅 Google Calendar")
creds_status = "✅ Connected" if is_google_connected() else "❌ Not Connected"
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
                        if event_id and is_google_connected():
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
                                if task['synced_calendar'] and is_google_connected():
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
        if is_google_connected():
            st.success("✅ Connected to Google Calendar")
            if os.path.exists(TOKEN_FILE):
                st.info("Your credentials are saved in token.json")
            else:
                st.info("Your credentials are loaded from Streamlit Secrets")

            if st.button("🔌 Disconnect"):
                if os.path.exists(TOKEN_FILE):
                    os.remove(TOKEN_FILE)
                st.success("Disconnected from Google Calendar! If running on Streamlit Cloud, please also clear your secrets in the Streamlit Console.")
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
        if is_google_connected():
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

elif page == "📝 PYQ Practice":
    st.title("📝 PYQ Practice (2024-2026)")
    st.markdown("Practice official Previous Year Questions (PYQs) from GATE Data Science & AI (DA) exams.")

    # Initialize quiz state
    if "quiz_answers" not in st.session_state:
        st.session_state.quiz_answers = {}
    if "quiz_scores" not in st.session_state:
        st.session_state.quiz_scores = {}

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        filter_subject = st.selectbox("Filter by Subject", ["All"] + list(GATE_DA_TOPICS.keys()))
    with col2:
        filter_year = st.selectbox("Filter by Year", ["All", 2024, 2025, 2026])
    with col3:
        filter_type = st.selectbox("Filter by Question Type", ["All", "MCQ", "MSQ", "NAT"])

    # Filtered questions list
    filtered_pyqs = GATE_DA_PYQS
    if filter_subject != "All":
        filtered_pyqs = [q for q in filtered_pyqs if q["subject"] == filter_subject]
    if filter_year != "All":
        filtered_pyqs = [q for q in filtered_pyqs if q["year"] == filter_year]
    if filter_type != "All":
        filtered_pyqs = [q for q in filtered_pyqs if q["type"] == filter_type]

    # Score calculation
    correct_count = sum(1 for q_id, is_correct in st.session_state.quiz_scores.items() if is_correct)
    total_answered = len(st.session_state.quiz_scores)
    
    # Progress UI
    if total_answered > 0:
        st.markdown(f"**Score Card: {correct_count}/{total_answered} Correct**")
        st.progress(correct_count / total_answered)
    else:
        st.markdown("*Start practicing below to see your progress!*")

    st.markdown("---")

    if not filtered_pyqs:
        st.info("No questions match your filter criteria. Try expanding your search!")
    else:
        for idx, q in enumerate(filtered_pyqs):
            # Question card container
            with st.container():
                st.markdown(
                    f"""
                    <div style="margin-bottom: 8px;">
                        <span style="background-color: #1a73e8; color: white; padding: 3px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold;">GATE DA {q['year']}</span>
                        <span style="background-color: #e8f0fe; color: #1a73e8; padding: 3px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; margin-left: 5px;">{q['subject']}</span>
                        <span style="background-color: #fce8e6; color: #d93025; padding: 3px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; margin-left: 5px;">{q['type']}</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                st.markdown(f"**Q{idx+1}.** {q['question']}")

                # Question Input depending on type
                user_ans = None
                q_key = f"q_{q['id']}"
                
                if q["type"] == "MCQ":
                    selected_opt = st.radio(
                        "Select your option:",
                        q["options"],
                        index=None,
                        key=f"radio_{q_key}"
                    )
                    user_ans = selected_opt
                
                elif q["type"] == "MSQ":
                    st.write("Select one or more options:")
                    selected_opts = []
                    for opt in q["options"]:
                        if st.checkbox(opt, key=f"check_{q_key}_{opt}"):
                            selected_opts.append(opt)
                    user_ans = sorted(selected_opts)
                
                elif q["type"] == "NAT":
                    user_ans = st.text_input("Enter your numerical answer:", key=f"text_{q_key}").strip()

                # Action buttons
                col_submit, col_sol = st.columns([1, 4])
                with col_submit:
                    if st.button("Submit Answer", key=f"submit_{q_key}"):
                        if user_ans is not None and user_ans != [] and user_ans != "":
                            st.session_state.quiz_answers[q_key] = user_ans
                            
                            # Verify correctness
                            is_correct = False
                            if q["type"] == "MCQ":
                                is_correct = (user_ans == q["answer"])
                            elif q["type"] == "MSQ":
                                is_correct = (user_ans == sorted(q["answer"]))
                            elif q["type"] == "NAT":
                                # Handle numerical float comparison
                                try:
                                    is_correct = abs(float(user_ans) - float(q["answer"])) < 0.01
                                except ValueError:
                                    is_correct = (user_ans.lower() == str(q["answer"]).lower())
                                    
                            st.session_state.quiz_scores[q_key] = is_correct
                            st.rerun()
                        else:
                            st.warning("Please provide an answer first.")

                # Show validation results if answered
                if q_key in st.session_state.quiz_answers:
                    submitted_val = st.session_state.quiz_answers[q_key]
                    is_correct = st.session_state.quiz_scores.get(q_key, False)
                    
                    if is_correct:
                        st.success(f"🎉 Correct! Your answer: {submitted_val}")
                    else:
                        st.error(f"❌ Incorrect. Your answer: {submitted_val}")
                    
                    # Display solution
                    with st.expander("📖 View Detailed Solution", expanded=False):
                        st.markdown(f"**Correct Answer:** {q['answer']}")
                        st.markdown(q["explanation"])
                
                st.markdown("<br><hr style='border: 0.5px solid #ddd;'><br>", unsafe_allow_html=True)

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
