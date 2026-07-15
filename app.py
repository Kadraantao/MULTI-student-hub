"""Student Hub — main entry point (multi-instructor)."""
import base64
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st
import extra_streamlit_components as stx

from admin_views import render_admin
from auth import (
    sign_in, sign_up, create_session, get_user_from_session, delete_session,
    create_password_reset_request,
)
from database import init_db, seed_admin
from student_views import render_student

# -------------------- Page config --------------------
BASE_DIR = Path(__file__).parent
ICON_PATH = BASE_DIR / "icons" / "ccs.jpg"

st.set_page_config(
    page_title="Student Hub",
    page_icon=str(ICON_PATH) if ICON_PATH.exists() else "🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Load icon if present, else fall back to no icon
if ICON_PATH.exists():
    with open(ICON_PATH, "rb") as _f:
        ICON_B64 = base64.b64encode(_f.read()).decode()
else:
    ICON_B64 = None


# -------------------- Init DB + seed admin --------------------
init_db()

# Load admin credentials from Streamlit Secrets (safe) with local fallback
try:
    ADMIN_EMAIL = st.secrets["admin"]["email"]
    ADMIN_PASSWORD = st.secrets["admin"]["password"]
    ADMIN_NAME = st.secrets["admin"]["full_name"]
except (KeyError, FileNotFoundError):
    ADMIN_EMAIL = "[email protected]"
    ADMIN_PASSWORD = "admin123"
    ADMIN_NAME = "Kadra"

seed_admin(email=ADMIN_EMAIL, password=ADMIN_PASSWORD, full_name=ADMIN_NAME)

# Load instructor signup code from Streamlit Secrets (with local dev fallback)
try:
    INSTRUCTOR_SIGNUP_CODE = st.secrets["instructor_signup"]["code"]
except (KeyError, FileNotFoundError):
    INSTRUCTOR_SIGNUP_CODE = "FACULTY2026"


# -------------------- Styling --------------------
st.markdown(
    """
    <style>
        .stApp {
            background-color: #FFFFFF;
            font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, sans-serif;
            color: #1A1A1A;
        }
        .stApp p, .stApp label, .stApp span, .stApp div { font-size: 1.05rem; }
        h1 { color: #60063a; font-weight: 700; font-size: 5.5rem; letter-spacing: -0.02em; margin-bottom: 0.25rem; }
        h2 { color: #60063a; font-weight: 600; font-size: 1.9rem; letter-spacing: -0.01em; }
        h3 { color: #60063a; font-weight: 600; font-size: 1.45rem; }
        h4 { color: #1A1A1A; font-weight: 600; font-size: 1.2rem; }
        section[data-testid="stSidebar"] { background-color: #FAFAFA; border-right: 1px solid #EEEEEE; }
        section[data-testid="stSidebar"] .stMarkdown { font-size: 1.05rem; }
        section[data-testid="stSidebar"] [role="radiogroup"] label { font-size: 1.05rem; padding: 0.35rem 0; }
        .stButton > button, [data-testid="stFormSubmitButton"] button {
            background-color: #60063a; color: #FFFFFF; border: none; border-radius: 12px;
            padding: 0.7rem 1.6rem; font-weight: 500; font-size: 1rem; transition: all 0.15s ease;
            box-shadow: 0 1px 2px rgba(96, 6, 58, 0.15);
        }
        .stButton > button:hover, [data-testid="stFormSubmitButton"] button:hover {
            background-color: #60063a; transform: translateY(-1px);
            box-shadow: 0 6px 18px rgba(96, 6, 58, 0.30); color: #FFFFFF;
        }
        .stButton > button:focus { outline: none; box-shadow: 0 0 0 3px rgba(96, 6, 58, 0.25); color: #FFFFFF; }
        .card {
            background: #FFFFFF; border: 1px solid #F0F0F0; border-left: 4px solid #60063a;
            border-radius: 14px; padding: 1.5rem 1.75rem; margin-bottom: 1rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04); transition: box-shadow 0.15s ease; font-size: 1.05rem;
        }
        .card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        .card h4 { color: #1A1A1A; margin: 0; font-size: 1.25rem; }
        .card p { font-size: 1rem; line-height: 1.5; }
        .chip {
            display: inline-block; padding: 0.3rem 0.9rem; border-radius: 999px;
            font-size: 0.78rem; font-weight: 700; letter-spacing: 0.05em;
            text-transform: uppercase; white-space: nowrap;
        }
        .chip-pending   { background: #FFF3E0; color: #E65100; }
        .chip-approved  { background: #E8F5E9; color: #2E7D32; }
        .chip-confirmed { background: #E8F5E9; color: #2E7D32; }
        .chip-rejected  { background: #FFEBEE; color: #C62828; }
        input[type="text"], input[type="password"], textarea {
            font-size: 1.05rem !important; border-radius: 10px !important; padding: 0.6rem 0.85rem !important;
        }
        .stSelectbox div[data-baseweb="select"] > div,
        .stDateInput input, .stTimeInput input {
            font-size: 1.05rem !important; border-radius: 10px !important;
        }
        .stTabs [data-baseweb="tab-list"] { gap: 0.5rem; }
        .stTabs [data-baseweb="tab"] { font-size: 1.05rem; padding: 0.6rem 1rem; }
        .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { color: #60063a; }
        .stTabs [data-baseweb="tab-highlight"] { background-color: #60063a; }
        [data-testid="stMetricValue"] { color: #60063a; font-size: 2.2rem; font-weight: 700; }
        [data-testid="stMetricLabel"] { font-size: 1rem; }
        hr { border-color: #EEEEEE; margin: 1.5rem 0; }
        .stDataFrame { font-size: 1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# -------------------- Session state --------------------
if "user" not in st.session_state:
    st.session_state.user = None
if "current_course" not in st.session_state:
    st.session_state.current_course = None
if "hub_session_token" not in st.session_state:
    st.session_state.hub_session_token = None

# -------------------- Cookie manager --------------------
cookies = stx.CookieManager(key="hub_cookie_manager")
all_cookies = cookies.get_all()

if st.session_state.get("sign_out_requested"):
    st.session_state.sign_out_requested = False
    old_token = st.session_state.get("hub_session_token")
    if old_token:
        delete_session(old_token)
    try:
        cookies.delete("hub_session", key="delete_hub_session")
    except Exception:
        pass
    st.session_state.user = None
    st.session_state.current_course = None
    st.session_state.hub_session_token = None
    st.rerun()

if st.session_state.user is None:
    saved_token = (all_cookies or {}).get("hub_session")
    if saved_token:
        restored = get_user_from_session(saved_token)
        if restored:
            st.session_state.user = restored
            st.session_state.hub_session_token = saved_token
        else:
            try:
                cookies.delete("hub_session", key="delete_stale_hub_session")
            except Exception:
                pass


# -------------------- Login / Signup screen --------------------
def login_screen():
    col_left, col_mid, col_right = st.columns([1, 4, 1])
    with col_mid:
        if ICON_B64:
            st.markdown(
                f"""
                <div style="display: flex; align-items: center; gap: 20px; margin: 1rem 0 1.5rem 0;">
                    <img src="data:image/jpeg;base64,{ICON_B64}" style="width: 130px; height: auto; display: block;"/>
                    <span style="
                        color: #60063a; font-size: 6rem; font-weight: 800;
                        letter-spacing: -0.03em; line-height: 1; white-space: nowrap;
                        font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif;
                    ">Student Hub</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <h1 style="font-size: 6rem; margin: 1rem 0 0.5rem;">Student Hub</h1>
                """,
                unsafe_allow_html=True,
            )
        st.markdown("**Consultation booking · Class schedule · Course announcements**")

        tab_signin, tab_signup = st.tabs(["Sign in", "Sign up"])

        # ---------------- Sign In tab ----------------
        with tab_signin:
            with st.form("signin_form"):
                email = st.text_input("Email", key="signin_email")
                password = st.text_input("Password", type="password", key="signin_pw")
                if st.form_submit_button("Sign in", use_container_width=True):
                    user = sign_in(email, password)
                    if user:
                        token = create_session(user["id"])
                        cookies.set(
                            "hub_session",
                            token,
                            expires_at=datetime.now() + timedelta(days=30),
                            key="set_hub_session",
                        )
                        st.session_state.user = user
                        st.session_state.hub_session_token = token
                        import time
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("Invalid email or password.")

            # Forgot password expander (outside the sign-in form)
            with st.expander("Forgot your password?"):
                with st.form("reset_request_form", clear_on_submit=True):
                    reset_email = st.text_input(
                        "Enter your email",
                        key="reset_email",
                        placeholder="you@example.com",
                    )
                    st.caption("Your admin will review the request and share a temporary password with you privately.")
                    if st.form_submit_button("Request password reset"):
                        ok, msg = create_password_reset_request(reset_email)
                        (st.success if ok else st.error)(msg)

        # ---------------- Sign Up tab ----------------
        with tab_signup:
            with st.form("signup_form", clear_on_submit=False):
                full_name = st.text_input("Full name", key="signup_name")
                email = st.text_input("Email", key="signup_email")
                password = st.text_input(
                    "Password (min 6 characters)", type="password", key="signup_pw"
                )
                signup_role = st.radio(
                    "I am registering as a...",
                    ["Student", "Instructor"],
                    horizontal=True,
                    key="signup_role",
                )
                if signup_role == "Instructor":
                    instructor_code = st.text_input(
                        "Instructor signup code",
                        type="password",
                        key="signup_code",
                        help="Ask the platform admin for the code.",
                    )
                else:
                    instructor_code = ""

                if st.form_submit_button("Create account", use_container_width=True):
                    role_value = "instructor" if signup_role == "Instructor" else "student"
                    if role_value == "instructor" and instructor_code != INSTRUCTOR_SIGNUP_CODE:
                        st.error("Invalid instructor signup code.")
                    else:
                        ok, msg = sign_up(email, password, full_name, role_value)
                        (st.success if ok else st.error)(msg)

            st.caption(
                "Students can sign up freely. Instructors need a signup code from the platform admin."
            )


# -------------------- Route --------------------
cookies_ready = all_cookies is not None and len(all_cookies) > 0

if st.session_state.user is None and not cookies_ready:
    st.markdown(
        """
        <div style="display:flex; justify-content:center; align-items:center;
                    height:60vh; color:#60063a;">
            <div style="text-align:center;">
                <div style="width:40px; height:40px; margin:0 auto 1rem;
                            border:4px solid #FCE4EC; border-top-color:#60063a;
                            border-radius:50%; animation:spin 0.8s linear infinite;"></div>
                <div style="font-size:1.1rem;">Loading…</div>
            </div>
        </div>
        <style>@keyframes spin { to { transform: rotate(360deg); } }</style>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

if st.session_state.user is None:
    login_screen()
else:
    if st.session_state.user["role"] in ("admin", "instructor"):
        render_admin()
    else:
        render_student()
