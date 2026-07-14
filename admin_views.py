"""Instructor (admin) views. All queries filter by the current instructor's ID."""
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from database import get_connection


DAY_OPTIONS = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
    "Mon - Tue", "Mon - Wed", "Mon - Thu", "Mon - Fri", "Mon - Sat",
    "Tue - Wed", "Tue - Thu", "Tue - Fri", "Tue - Sat",
    "Wed - Thu", "Wed - Fri", "Wed - Sat",
    "Thu - Fri", "Thu - Sat",
    "Fri - Sat",
]

DURATION_OPTIONS = {
    "1 hour": 60,
    "1 hour 30 minutes": 90,
    "2 hours": 120,
    "2 hours 30 minutes": 150,
    "3 hours": 180,
    "3 hours 30 minutes": 210,
    "4 hours": 240,
    "5 hours": 300,
}


def _generate_start_times():
    t = datetime.strptime("07:00", "%H:%M")
    end = datetime.strptime("20:00", "%H:%M")
    out = []
    while t <= end:
        out.append(t.strftime("%H:%M"))
        t += timedelta(minutes=30)
    return out


START_TIME_OPTIONS = _generate_start_times()


def format_time_slot(start_str: str, duration_min: int) -> str:
    start = datetime.strptime(start_str, "%H:%M")
    end = start + timedelta(minutes=duration_min)
    return f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"


def _fetchall(sql: str, params=None):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        rows = cur.fetchall()
    conn.close()
    return rows


def _fetchone(sql: str, params=None):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        row = cur.fetchone()
    conn.close()
    return row


def _execute(sql: str, params=None):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
    conn.commit()
    conn.close()


def render_admin():
    user = st.session_state.user
    role_label = "Admin" if user["role"] == "admin" else "Instructor"

    with st.sidebar:
        st.markdown(f"### Welcome, {user['full_name']}")
        st.caption(f"Signed in as **{role_label.lower()}**")
        st.divider()
        page = st.radio(
            "Navigate",
            [
                "Dashboard",
                "Courses",
                "Enrollment Requests",
                "Consultations",
                "Course Manager",
            ],
            label_visibility="collapsed",
        )
        st.divider()
        if st.button("Sign out", use_container_width=True):
            st.session_state.sign_out_requested = True
            st.rerun()

    if page == "Dashboard":
        admin_dashboard()
    elif page == "Courses":
        admin_courses()
    elif page == "Enrollment Requests":
        admin_enrollments()
    elif page == "Consultations":
        admin_consultations()
    elif page == "Course Manager":
        admin_course_manager()


def admin_dashboard():
    st.title("Dashboard")
    st.caption("Your own workspace — showing only your courses and students.")
    uid = st.session_state.user["id"]

    n_students = _fetchone(
        """
        SELECT COUNT(DISTINCT u.id) AS n
        FROM users u
        JOIN enrollments e ON e.user_id = u.id
        JOIN courses c ON c.id = e.course_id
        WHERE c.instructor_id = %s AND e.status = 'approved' AND u.role = 'student'
        """,
        (uid,),
    )["n"]
    n_courses = _fetchone(
        "SELECT COUNT(*) AS n FROM courses WHERE instructor_id = %s", (uid,)
    )["n"]
    n_pending = _fetchone(
        """
        SELECT COUNT(*) AS n FROM enrollments e
        JOIN courses c ON c.id = e.course_id
        WHERE c.instructor_id = %s AND e.status = 'pending'
        """,
        (uid,),
    )["n"]
    n_consults = _fetchone(
        "SELECT COUNT(*) AS n FROM consultations WHERE instructor_id = %s AND status = 'pending'",
        (uid,),
    )["n"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("My Students", n_students)
    c2.metric("My Courses", n_courses)
    c3.metric("Pending Enrollments", n_pending)
    c4.metric("Pending Consultations", n_consults)

    st.divider()
    st.subheader("My class schedule")
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT code AS "Code", name AS "Course", room AS "Room",
               schedule_day AS "Day", schedule_time AS "Time"
        FROM courses
        WHERE instructor_id = %(uid)s
        ORDER BY schedule_day, schedule_time
        """,
        conn,
        params={"uid": uid},
    )
    conn.close()
    if df.empty:
        st.info("No courses yet. Add one in **Courses**.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


def admin_courses():
    st.title("My Courses")
    st.caption("Only you can see and manage these courses.")
    uid = st.session_state.user["id"]

    with st.expander("➕ Add a new course", expanded=False):
        with st.form("new_course", clear_on_submit=True):
            c1, c2 = st.columns(2)
            code = c1.text_input("Course code", placeholder="e.g. CS401")
            name = c2.text_input("Course name", placeholder="e.g. Advanced Image Processing")

            c3, c4 = st.columns(2)
            room = c3.text_input("Room", placeholder="e.g. Lab 3-201")
            day = c4.selectbox("Day / Days", DAY_OPTIONS)

            c5, c6 = st.columns(2)
            duration_label = c5.selectbox("Class duration", list(DURATION_OPTIONS.keys()))
            start_time = c6.selectbox("Start time", START_TIME_OPTIONS)

            if st.form_submit_button("Create course"):
                if not code or not name:
                    st.error("Code and name are required.")
                else:
                    duration_min = DURATION_OPTIONS[duration_label]
                    time_str = format_time_slot(start_time, duration_min)
                    try:
                        _execute(
                            "INSERT INTO courses (code, name, room, schedule_day, schedule_time, instructor_id) "
                            "VALUES (%s, %s, %s, %s, %s, %s)",
                            (code.upper().strip(), name.strip(), room.strip(), day, time_str, uid),
                        )
                        st.success(f"Course {code.upper()} created — {day}, {time_str}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not create course: {e}")

    courses = _fetchall(
        "SELECT * FROM courses WHERE instructor_id = %s ORDER BY code", (uid,)
    )

    if not courses:
        st.info("You haven't created any courses yet.")
        return

    for c in courses:
        st.markdown(
            f"""
            <div class="card">
                <h4 style="margin:0;">{c['code']} — {c['name']}</h4>
                <p style="margin:0.35rem 0 0; color:#555;">
                    📍 {c['room'] or 'TBA'} &nbsp;·&nbsp; 🗓 {c['schedule_day'] or 'TBA'} &nbsp;·&nbsp; ⏰ {c['schedule_time'] or 'TBA'}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        col1, _ = st.columns([1, 6])
        if col1.button("Delete", key=f"del_{c['id']}"):
            _execute("DELETE FROM courses WHERE id = %s AND instructor_id = %s", (c["id"], uid))
            st.rerun()


def admin_enrollments():
    st.title("Enrollment Requests")
    st.caption("Approve or reject students who requested to enroll in your courses.")
    uid = st.session_state.user["id"]

    rows = _fetchall(
        """
        SELECT e.id, e.status, e.requested_at,
               u.id AS student_id, u.full_name, u.email,
               c.id AS course_id, c.code, c.name
        FROM enrollments e
        JOIN users u ON u.id = e.user_id
        JOIN courses c ON c.id = e.course_id
        WHERE c.instructor_id = %s
        ORDER BY (e.status = 'pending') DESC, e.requested_at DESC
        """,
        (uid,),
    )

    if not rows:
        st.info("No enrollment requests yet.")
        return

    status_filter = st.selectbox("Filter", ["All", "Pending", "Approved", "Rejected"])

    for r in rows:
        if status_filter != "All" and r["status"] != status_filter.lower():
            continue
        chip_class = f"chip-{r['status']}"
        st.markdown(
            f"""
            <div class="card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <strong>{r['full_name']}</strong>
                        <span style="color:#666;">({r['email']})</span><br>
                        <span style="color:#333;">Requested: <strong>{r['code']}</strong> — {r['name']}</span>
                    </div>
                    <span class="chip {chip_class}">{r['status'].upper()}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if r["status"] == "pending":
            c1, c2, _ = st.columns([1, 1, 6])
            if c1.button("✅ Approve", key=f"apv_{r['id']}"):
                _execute("UPDATE enrollments SET status='approved' WHERE id = %s", (r["id"],))
                st.rerun()
            if c2.button("❌ Reject", key=f"rej_{r['id']}"):
                _execute("UPDATE enrollments SET status='rejected' WHERE id = %s", (r["id"],))
                st.rerun()


def admin_consultations():
    st.title("Consultation Requests")
    st.caption("Students who requested a 1-on-1 consultation with you.")
    uid = st.session_state.user["id"]

    rows = _fetchall(
        """
        SELECT co.*, u.full_name, u.email
        FROM consultations co
        JOIN users u ON u.id = co.student_id
        WHERE co.instructor_id = %s
        ORDER BY (co.status = 'pending') DESC, co.requested_date, co.requested_time
        """,
        (uid,),
    )

    if not rows:
        st.info("No consultation requests yet.")
        return

    for r in rows:
        st.markdown(
            f"""
            <div class="card">
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                    <div>
                        <strong>{r['full_name']}</strong>
                        <span style="color:#666;">({r['email']})</span><br>
                        🗓 <strong>{r['requested_date']}</strong> at <strong>{r['requested_time']}</strong><br>
                        <em style="color:#333;">Topic: {r['topic']}</em>
                    </div>
                    <span class="chip chip-{r['status']}">{r['status'].upper()}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if r["status"] == "pending":
            c1, c2, _ = st.columns([1, 1, 6])
            if c1.button("✅ Confirm", key=f"con_{r['id']}"):
                _execute("UPDATE consultations SET status='confirmed' WHERE id = %s", (r["id"],))
                st.rerun()
            if c2.button("❌ Decline", key=f"dec_{r['id']}"):
                _execute("UPDATE consultations SET status='rejected' WHERE id = %s", (r["id"],))
                st.rerun()


def admin_course_manager():
    st.title("Course Manager")
    st.caption("Manage announcements, attendance, and roster for one of your courses.")
    uid = st.session_state.user["id"]

    courses = _fetchall(
        "SELECT * FROM courses WHERE instructor_id = %s ORDER BY code", (uid,)
    )

    if not courses:
        st.info("You haven't created any courses yet. Add one in **Courses** first.")
        return

    labels = [f"{c['code']} — {c['name']}" for c in courses]
    idx = st.selectbox("Course", range(len(courses)), format_func=lambda i: labels[i])
    course = courses[idx]

    tab_ann, tab_att, tab_students = st.tabs(
        ["📢 Announcements", "✅ Attendance", "👥 Enrolled Students"]
    )
    with tab_ann:
        manage_announcements(course["id"])
    with tab_att:
        manage_attendance(course["id"])
    with tab_students:
        show_enrolled_students(course["id"])


def _verify_course_ownership(course_id: int) -> bool:
    uid = st.session_state.user["id"]
    row = _fetchone(
        "SELECT 1 AS x FROM courses WHERE id = %s AND instructor_id = %s", (course_id, uid)
    )
    return row is not None


def manage_announcements(course_id: int):
    if not _verify_course_ownership(course_id):
        st.error("You don't own this course.")
        return
    st.subheader("Post an announcement")
    st.caption("Only students enrolled (approved) in this course will see it.")
    with st.form(f"new_ann_{course_id}", clear_on_submit=True):
        c1, c2 = st.columns([3, 1])
        title = c1.text_input("Title")
        ann_type = c2.selectbox("Type", ["activity", "status"])
        content = st.text_area(
            "Message",
            placeholder="e.g. 'I cannot attend tomorrow's class' or 'Quiz on Chapter 4 this Friday'",
        )
        if st.form_submit_button("Post"):
            if not title or not content:
                st.error("Title and message are required.")
            else:
                _execute(
                    "INSERT INTO announcements (course_id, title, content, type) "
                    "VALUES (%s, %s, %s, %s)",
                    (course_id, title.strip(), content.strip(), ann_type),
                )
                st.success("Announcement posted.")
                st.rerun()

    st.divider()
    st.subheader("Previous announcements")
    anns = _fetchall(
        "SELECT * FROM announcements WHERE course_id = %s ORDER BY posted_at DESC",
        (course_id,),
    )

    if not anns:
        st.info("No announcements posted yet for this course.")
        return

    for a in anns:
        icon = "📌" if a["type"] == "activity" else "📣"
        st.markdown(
            f"""
            <div class="card">
                <div style="display:flex; justify-content:space-between;">
                    <strong>{icon} {a['title']}</strong>
                    <span style="color:#888; font-size:0.8rem;">{a['posted_at']}</span>
                </div>
                <p style="margin:0.5rem 0 0; white-space:pre-wrap;">{a['content']}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Delete", key=f"delann_{a['id']}"):
            _execute("DELETE FROM announcements WHERE id = %s", (a["id"],))
            st.rerun()


def manage_attendance(course_id: int):
    if not _verify_course_ownership(course_id):
        st.error("You don't own this course.")
        return
    st.subheader("Record attendance")
    students = _fetchall(
        """
        SELECT u.id, u.full_name, u.email
        FROM users u
        JOIN enrollments e ON e.user_id = u.id
        WHERE e.course_id = %s AND e.status = 'approved'
        ORDER BY u.full_name
        """,
        (course_id,),
    )

    if not students:
        st.info("No approved students enrolled in this course yet.")
        return

    att_date = st.date_input("Date", value=date.today(), key=f"att_date_{course_id}")

    st.write("Mark attendance:")
    statuses = {}
    for s in students:
        c1, c2 = st.columns([3, 2])
        c1.write(f"**{s['full_name']}** — {s['email']}")
        statuses[s["id"]] = c2.selectbox(
            f"Status_{s['id']}",
            ["present", "absent", "late"],
            label_visibility="collapsed",
            key=f"att_{s['id']}_{att_date.isoformat()}_{course_id}",
        )

    if st.button("Save attendance", type="primary", key=f"save_att_{course_id}"):
        conn = get_connection()
        with conn.cursor() as cur:
            for sid, status in statuses.items():
                cur.execute(
                    """
                    INSERT INTO attendance (course_id, student_id, date, status)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (course_id, student_id, date)
                    DO UPDATE SET status = EXCLUDED.status
                    """,
                    (course_id, sid, att_date.isoformat(), status),
                )
        conn.commit()
        conn.close()
        st.success(f"Attendance saved for {att_date.isoformat()}.")

    st.divider()
    st.subheader("Attendance history")
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT a.date AS "Date", u.full_name AS "Student", a.status AS "Status"
        FROM attendance a
        JOIN users u ON u.id = a.student_id
        WHERE a.course_id = %(cid)s
        ORDER BY a.date DESC, u.full_name
        """,
        conn,
        params={"cid": course_id},
    )
    conn.close()
    if df.empty:
        st.info("No attendance records yet.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


def show_enrolled_students(course_id: int):
    if not _verify_course_ownership(course_id):
        st.error("You don't own this course.")
        return
    st.subheader("Enrolled students (approved)")
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT u.full_name AS "Full name", u.email AS "Email",
               e.requested_at AS "Enrolled since"
        FROM users u
        JOIN enrollments e ON e.user_id = u.id
        WHERE e.course_id = %(cid)s AND e.status = 'approved'
        ORDER BY u.full_name
        """,
        conn,
        params={"cid": course_id},
    )
    conn.close()
    if df.empty:
        st.info("No approved students yet.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)