import os
import psycopg2
import streamlit as st

st.set_page_config(
    page_title="College Mail To-Do List", page_icon="🎓", layout="wide"
)

DATABASE_URL = os.environ.get(
    "DATABASE_URL", st.secrets.get("DATABASE_URL", "")
)


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def load_todos():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, title, category, importance, deadline, details, completed FROM todos ORDER BY id DESC"
        )
        rows = cur.fetchall()
    conn.close()
    return rows


def toggle_todo(todo_id, status):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE todos SET completed = %s WHERE id = %s", (status, todo_id)
        )
    conn.commit()
    conn.close()


st.title("🎓 College Mail To-Do Tracker (24/7)")
st.caption("Continuously monitored in the cloud.")

if not DATABASE_URL:
    st.error("Please set DATABASE_URL in secrets/environment variables.")
    st.stop()

todos = load_todos()
pending = [t for t in todos if not t[6]]
completed = [t for t in todos if t[6]]

col1, col2, col3 = st.columns(3)
col1.metric("Pending Tasks", len(pending))
col2.metric("High Priority", len([t for t in pending if t[3] == "High"]))
col3.metric("Completed", len(completed))

st.markdown("---")
st.header("📋 Actionable Tasks")

if not pending:
    st.info("No pending tasks! Cloud monitoring is active.")
else:
    for t in pending:
        t_id, title, category, importance, deadline, details, comp = t
        badge = (
            "🔴 High"
            if importance == "High"
            else ("🟡 Medium" if importance == "Medium" else "🟢 Low")
        )

        c1, c2 = st.columns([0.05, 0.95])
        with c1:
            if st.checkbox("", key=f"t_{t_id}", value=False):
                toggle_todo(t_id, True)
                st.rerun()
        with c2:
            st.markdown(f"**{title}** &nbsp; `{badge}` &nbsp; `📁 {category}`")
            st.caption(f"🗓️ **Deadline:** {deadline} | ℹ️ **Details:** {details}")
