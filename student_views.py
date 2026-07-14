"""Student views."""
from datetime import date, time

import pandas as pd
import streamlit as st

from database import get_connection


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


def render_student():
    user = st.session_state.user
    with st.sidebar:
        st.markdown(f"### Welcome, {user['full_name']}")
        st.caption("Signed in as **student**")
        st.divider()
        page = st.radio(
            "Navigate",
            [
                "My Courses",
                "Enroll in a Course",
                "Book a Consultation",
                "My Consultations",
                "My Class Schedule",
            ],
            label_visibility="collapsed",
        )
        st.divider()
        if st.button("Sign out", use_container_width=True):
            st.session_state.sign_out_requested = True
            st.rerun()

    if page != "My Courses":
        st.session_state.current_course = None

    if page == "My Courses":
        student_my_courses()
    elif page == "Enroll in a Course":
        student_enroll()
    elif page == "Book a Consultation":
        student_book()
    elif page == "My Consultations":
        student_my_consultations()
    elif page == "My Class Schedule":
        student_schedule()


def student_my_courses():
    user = st.session_state.user

    approved = _fetchall(
        """
        SELECT c.*, i.full_name AS instructor_name
        FROM courses c
        JOIN enrollments e ON e.course_id = c.id
        JOIN users i ON i.id = c.instructor_id
        WHERE e.user_id = %s AND e.status = 'approved'
        ORDER BY c.code
        """,
        (user["id"],),
    )

    if st.session_state.get("current_course") is None:
        st.title("My Courses")
        if not approved:
            st.info(
                "You are not enrolled in any course yet. "
                "Go to **Enroll in a Course** to request enrollment."
            )
            return
        st.caption("Pick a course to open its announcement board.")
        for c in approved:
            st.markdown(
                f"""
                <div class="card">
                    <h4 style="margin:0;">{c['code']} — {c['name']}</h4>
                    <p style="margin:0.35rem 0 0; color:#555;">
                        👤 <strong>{c['instructor_name']}</strong>
                    </p>
                    <p style="margin:0.35rem 0 0; color:#555;">
                        📍 {c['room'] or 'TBA'} &nbsp;·&nbsp; 🗓 {c['schedule_day'] or 'TBA'} &nbsp;·&nbsp; ⏰ {c['schedule_time'] or 'TBA'}
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Open course", key=f"open_{c['id']}"):
                st.session_state.current_course = c["id"]
                st.rerun()
    else:
        show_course_inside(st.session_state.current_course)


def show_course_inside(course_id: int):
    user = st.session_state.user

    course = _fetchone(
        """
        SELECT c.*, i.full_name AS instructor_name
        FROM courses c
        JOIN users i ON i.id = c.instructor_id
        WHERE c.id = %s
        """,
        (course_id,),
    )
    enrolled = _fetchone(
        "SELECT 1 AS x FROM enrollments WHERE user_id = %s AND course_id = %s AND status = 'approved'",
        (user["id"], course_id),
    )

    if not course or not enrolled:
        st.error("This course is no longer available to you.")
        st.session_state.current_course = None
        if st.button("Back"):
            st.rerun()
        return

    if st.button("← Back to my courses"):
        st.session_state.current_course = None
        st.rerun()

    st.title(f"{course['code']} — {course['name']}")
    st.caption(
        f"👤 {course['instructor_name']}  ·  📍 {course['room'] or 'TBA'}  ·  🗓 {course['schedule_day'] or 'TBA'}  ·  ⏰ {course['schedule_time'] or 'TBA'}"
    )

    tab_ann, tab_att = st.tabs(["📢 Announcements", "✅ My Attendance"])

    with tab_ann:
        anns = _fetchall(
            "SELECT * FROM announcements WHERE course_id = %s ORDER BY posted_at DESC",
            (course_id,),
        )
        if not anns:
            st.info("No announcements yet for this course.")
        else:
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

    with tab_att:
        conn = get_connection()
        df = pd.read_sql_query(
            """
            SELECT date AS "Date", status AS "Status"
            FROM attendance
            WHERE course_id = %(cid)s AND student_id = %(uid)s
            ORDER BY date DESC
            """,
            conn,
            params={"cid": course_id, "uid": user["id"]},
        )
        conn.close()
        if df.empty:
            st.info("No attendance recorded yet.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)


def student_enroll():
    st.title("Enroll in a Course")
    st.caption("Browse courses offered by every instructor. Pick one to request enrollment.")
    user = st.session_state.user

    all_courses = _fetchall(
        """
        SELECT c.*, i.full_name AS instructor_name, i.email AS instructor_email
        FROM courses c
        JOIN users i ON i.id = c.instructor_id
        ORDER BY i.full_name, c.code
        """
    )
    existing_rows = _fetchall(
        "SELECT course_id, status FROM enrollments WHERE user_id = %s", (user["id"],)
    )
    existing = {r["course_id"]: r["status"] for r in existing_rows}

    if not all_courses:
        st.info("No courses have been created yet.")
        return

    instructors = sorted({c["instructor_name"] for c in all_courses})
    picked = st.selectbox("Filter by instructor", ["All instructors"] + instructors)

    shown_any = False
    for c in all_courses:
        if picked != "All instructors" and c["instructor_name"] != picked:
            continue
        shown_any = True
        current = existing.get(c["id"])
        if current == "approved":
            chip = '<span class="chip chip-approved">ENROLLED</span>'
        elif current == "pending":
            chip = '<span class="chip chip-pending">PENDING</span>'
        elif current == "rejected":
            chip = '<span class="chip chip-rejected">REJECTED</span>'
        else:
            chip = ""

        st.markdown(
            f"""
            <div class="card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <h4 style="margin:0;">{c['code']} — {c['name']}</h4>
                        <p style="margin:0.35rem 0 0; color:#555;">
                            👤 <strong>{c['instructor_name']}</strong>
                        </p>
                        <p style="margin:0.35rem 0 0; color:#555;">
                            📍 {c['room'] or 'TBA'} · 🗓 {c['schedule_day'] or 'TBA'} · ⏰ {c['schedule_time'] or 'TBA'}
                        </p>
                    </div>
                    {chip}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if current is None:
            if st.button("Request enrollment", key=f"enr_{c['id']}"):
                _execute(
                    "INSERT INTO enrollments (user_id, course_id, status) VALUES (%s, %s, 'pending')",
                    (user["id"], c["id"]),
                )
                st.rerun()
        elif current == "rejected":
            if st.button("Request again", key=f"reenr_{c['id']}"):
                _execute(
                    "UPDATE enrollments SET status='pending' WHERE user_id = %s AND course_id = %s",
                    (user["id"], c["id"]),
                )
                st.rerun()

    if not shown_any:
        st.info("No courses match that filter.")


def student_book():
    st.title("Book a Consultation")
    st.caption("Request a 1-on-1 consultation with an instructor.")
    user = st.session_state.user

    instructors = _fetchall(
        "SELECT id, full_name, email FROM users "
        "WHERE role IN ('admin', 'instructor') ORDER BY full_name"
    )

    if not instructors:
        st.info("No instructors are available on this platform yet.")
        return

    instructor_labels = [f"{i['full_name']} ({i['email']})" for i in instructors]
    instructor_ids = [i["id"] for i in instructors]

    with st.form("book_form", clear_on_submit=True):
        pick = st.selectbox(
            "Instructor",
            range(len(instructors)),
            format_func=lambda i: instructor_labels[i],
        )
        c1, c2 = st.columns(2)
        req_date = c1.date_input("Preferred date", min_value=date.today())
        req_time = c2.time_input("Preferred time", value=time(10, 0))
        topic = st.text_area(
            "What would you like to discuss?",
            placeholder="e.g. Thesis chapter feedback, exam questions, project consultation…",
        )
        submitted = st.form_submit_button("Request consultation")
        if submitted:
            if not topic.strip():
                st.error("Please describe the topic.")
            else:
                _execute(
                    """
                    INSERT INTO consultations
                        (student_id, instructor_id, requested_date, requested_time, topic, status)
                    VALUES (%s, %s, %s, %s, %s, 'pending')
                    """,
                    (
                        user["id"],
                        instructor_ids[pick],
                        req_date.isoformat(),
                        req_time.strftime("%H:%M"),
                        topic.strip(),
                    ),
                )
                st.success(f"Consultation request sent to {instructors[pick]['full_name']}.")


def student_my_consultations():
    st.title("My Consultations")
    user = st.session_state.user
    rows = _fetchall(
        """
        SELECT co.*, i.full_name AS instructor_name
        FROM consultations co
        JOIN users i ON i.id = co.instructor_id
        WHERE co.student_id = %s
        ORDER BY co.requested_date DESC, co.requested_time DESC
        """,
        (user["id"],),
    )

    if not rows:
        st.info("No consultation requests yet.")
        return

    for r in rows:
        st.markdown(
            f"""
            <div class="card">
                <div style="display:flex; justify-content:space-between;">
                    <div>
                        👤 with <strong>{r['instructor_name']}</strong><br>
                        🗓 <strong>{r['requested_date']}</strong> at <strong>{r['requested_time']}</strong><br>
                        <em>Topic: {r['topic']}</em>
                    </div>
                    <span class="chip chip-{r['status']}">{r['status'].upper()}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def student_schedule():
    st.title("My Class Schedule")
    st.caption("The classes you are approved to attend.")
    user = st.session_state.user
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT c.code AS "Code", c.name AS "Course", i.full_name AS "Instructor",
               c.room AS "Room", c.schedule_day AS "Day", c.schedule_time AS "Time"
        FROM courses c
        JOIN enrollments e ON e.course_id = c.id
        JOIN users i ON i.id = c.instructor_id
        WHERE e.user_id = %(uid)s AND e.status = 'approved'
        ORDER BY c.schedule_day, c.schedule_time
        """,
        conn,
        params={"uid": user["id"]},
    )
    conn.close()
    if df.empty:
        st.info("You have no approved courses yet.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)