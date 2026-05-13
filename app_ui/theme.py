from __future__ import annotations

import html


SYSTEM_NAME = "Part-Time Lecturer Claims and Attendance Register Management System"


def _st():
    import streamlit as st

    return st


def apply_app_theme() -> None:
    st = _st()
    st.markdown(
        """
        <style>
        :root {
            --pt-navy: #0b1f3a;
            --pt-charcoal: #111827;
            --pt-secondary: #374151;
            --pt-gold: #b58a2a;
            --pt-bg: #f3f6fa;
            --pt-panel: #ffffff;
            --pt-border: #d9e1ec;
            --pt-muted: #6b7280;
            --pt-blue: #1d5fa7;
            --pt-green: #1f7a4d;
            --pt-amber: #a16207;
            --pt-red: #b42318;
        }
        .stApp {
            background: var(--pt-bg);
            color: var(--pt-charcoal);
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #10233f 0%, #1c314f 100%);
        }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] .stRadio label,
        [data-testid="stSidebar"] .stCheckbox label {
            color: #f8fafc;
        }
        [data-testid="stSidebar"] .stRadio label {
            padding: 0.2rem 0;
        }
        [data-testid="stSidebar"] .stButton > button {
            border: 1px solid rgba(255,255,255,0.35);
            background: rgba(255,255,255,0.08);
            color: #ffffff;
            width: 100%;
        }
        h1, h2, h3 {
            color: var(--pt-navy);
            letter-spacing: 0;
        }
        p, label, span, div[data-testid="stMarkdownContainer"], div[data-testid="stText"] {
            color: var(--pt-charcoal);
        }
        div[data-testid="stWidgetLabel"] label,
        div[data-testid="stCheckbox"] label,
        div[data-testid="stRadio"] label,
        div[data-testid="stSelectbox"] label,
        div[data-testid="stTextInput"] label,
        div[data-testid="stNumberInput"] label,
        div[data-testid="stDateInput"] label,
        div[data-testid="stFileUploader"] label {
            color: var(--pt-secondary);
            font-weight: 600;
        }
        div[data-testid="stMetric"] {
            background: var(--pt-panel);
            border: 1px solid var(--pt-border);
            border-radius: 10px;
            padding: 1rem 1.1rem;
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06);
        }
        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] [data-testid="stMetricLabel"],
        div[data-testid="stMetric"] [data-testid="stMetricValue"],
        div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
            color: var(--pt-navy);
        }
        div[data-testid="stMetric"] [data-testid="stMetricLabel"] {
            color: var(--pt-secondary);
            font-weight: 650;
        }
        button[data-baseweb="tab"] p,
        button[data-baseweb="tab"] span {
            color: var(--pt-secondary);
            font-weight: 650;
        }
        button[data-baseweb="tab"][aria-selected="true"] p,
        button[data-baseweb="tab"][aria-selected="true"] span {
            color: var(--pt-navy);
        }
        .stButton > button,
        .stDownloadButton > button,
        div[data-testid="stDownloadButton"] > button,
        div[data-testid="stLinkButton"] a,
        .stFormSubmitButton > button,
        button[data-testid="baseButton-primary"],
        button[kind="primary"] {
            border-radius: 8px;
            border: 1px solid #1d5fa7;
            background: #1d5fa7 !important;
            background-color: #1d5fa7 !important;
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
            font-weight: 600;
        }
        .stButton > button *,
        .stDownloadButton > button,
        .stDownloadButton > button *,
        div[data-testid="stDownloadButton"] > button,
        div[data-testid="stDownloadButton"] > button *,
        div[data-testid="stLinkButton"] a,
        div[data-testid="stLinkButton"] a *,
        .stFormSubmitButton > button,
        .stFormSubmitButton > button *,
        button[kind="primary"],
        button[kind="primary"] *,
        button[data-testid="baseButton-primary"],
        button[data-testid="baseButton-primary"] * {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
            fill: #ffffff !important;
            stroke: #ffffff;
        }
        .stButton > button:hover {
            border-color: #164a82;
            background: #164a82 !important;
            background-color: #164a82 !important;
            color: #ffffff !important;
        }
        .stDownloadButton > button:hover,
        div[data-testid="stDownloadButton"] > button:hover,
        div[data-testid="stLinkButton"] a:hover {
            border-color: #164a82 !important;
            background: #164a82 !important;
            background-color: #164a82 !important;
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
        }
        .stButton > button:disabled,
        .stDownloadButton > button:disabled,
        div[data-testid="stDownloadButton"] > button:disabled,
        .stFormSubmitButton > button:disabled {
            background: #d9e1ec !important;
            background-color: #d9e1ec !important;
            border-color: #c4cfdd;
            color: #4b5563 !important;
            -webkit-text-fill-color: #4b5563 !important;
        }
        div[data-testid="stTextInput"],
        div[data-testid="stTextArea"],
        div[data-testid="stDateInput"],
        div[data-testid="stTimeInput"],
        div[data-testid="stSelectbox"] {
            color: var(--pt-charcoal);
        }
        div[data-baseweb="input"],
        div[data-baseweb="textarea"],
        div[data-baseweb="select"],
        div[data-testid="stTextInput"] div[data-baseweb="input"],
        div[data-testid="stTextArea"] div[data-baseweb="textarea"],
        div[data-testid="stDateInput"] div[data-baseweb="input"],
        div[data-testid="stTimeInput"] div[data-baseweb="input"],
        div[data-testid="stSelectbox"] div[data-baseweb="select"] {
            background: #ffffff !important;
            background-color: #ffffff !important;
            color: var(--pt-charcoal) !important;
            border-color: var(--pt-border) !important;
            opacity: 1 !important;
        }
        div[data-baseweb="input"] *,
        div[data-baseweb="textarea"] *,
        div[data-baseweb="select"] * {
            background-color: transparent;
        }
        div[data-baseweb="input"] input,
        div[data-baseweb="textarea"] textarea,
        div[data-baseweb="select"] input,
        div[data-baseweb="select"] span,
        div[data-baseweb="select"] div,
        input,
        textarea {
            color: var(--pt-charcoal) !important;
            -webkit-text-fill-color: var(--pt-charcoal) !important;
            opacity: 1 !important;
        }
        div[data-baseweb="input"] input,
        div[data-baseweb="textarea"] textarea,
        div[data-baseweb="select"] input,
        input,
        textarea {
            caret-color: var(--pt-charcoal) !important;
        }
        div[data-baseweb="input"] svg,
        div[data-baseweb="select"] svg,
        div[data-baseweb="textarea"] svg,
        div[data-testid="stTextInput"] svg,
        div[data-testid="stDateInput"] svg,
        div[data-testid="stTimeInput"] svg,
        div[data-testid="stSelectbox"] svg {
            color: var(--pt-secondary) !important;
            fill: var(--pt-secondary) !important;
            stroke: var(--pt-secondary) !important;
            opacity: 1 !important;
        }
        input::placeholder,
        textarea::placeholder {
            color: var(--pt-muted) !important;
            -webkit-text-fill-color: var(--pt-muted) !important;
            opacity: 1 !important;
        }
        input:focus,
        textarea:focus,
        div[data-baseweb="input"]:focus-within,
        div[data-baseweb="textarea"]:focus-within,
        div[data-baseweb="select"]:focus-within {
            background-color: #ffffff !important;
            color: var(--pt-charcoal) !important;
            border-color: var(--pt-blue) !important;
            box-shadow: 0 0 0 1px rgba(29, 95, 167, 0.25);
        }
        input:disabled,
        textarea:disabled,
        div[data-baseweb="input"][aria-disabled="true"],
        div[data-baseweb="select"][aria-disabled="true"] {
            background-color: #f3f6fa !important;
            color: #4b5563 !important;
            -webkit-text-fill-color: #4b5563 !important;
            opacity: 1 !important;
        }
        div[data-baseweb="popover"],
        div[data-baseweb="popover"] *,
        div[data-baseweb="menu"],
        div[data-baseweb="menu"] *,
        div[role="listbox"],
        div[role="listbox"] *,
        div[role="option"],
        div[role="option"] * {
            background-color: #ffffff !important;
            color: var(--pt-charcoal) !important;
            -webkit-text-fill-color: var(--pt-charcoal) !important;
            opacity: 1 !important;
        }
        div[role="option"]:hover,
        div[role="option"][aria-selected="true"] {
            background-color: #e8f1fb !important;
            color: var(--pt-navy) !important;
            -webkit-text-fill-color: var(--pt-navy) !important;
        }
        div[data-testid="stCodeBlock"],
        div[data-testid="stCodeBlock"] pre,
        div[data-testid="stCodeBlock"] code,
        pre,
        code {
            background-color: #f8fafc !important;
            color: var(--pt-charcoal) !important;
            -webkit-text-fill-color: var(--pt-charcoal) !important;
            border-color: var(--pt-border) !important;
        }
        .pt-file-path {
            background: #f8fafc;
            border: 1px solid var(--pt-border);
            border-radius: 8px;
            padding: 0.65rem 0.75rem;
            margin: 0.35rem 0 0.75rem 0;
        }
        .pt-file-path-label {
            display: block;
            color: var(--pt-secondary);
            font-weight: 700;
            margin-bottom: 0.2rem;
        }
        .pt-file-path code {
            color: var(--pt-charcoal) !important;
            -webkit-text-fill-color: var(--pt-charcoal) !important;
            background: transparent !important;
            overflow-wrap: anywhere;
        }
        .pt-file-path-meta {
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
            margin-top: 0.35rem;
            color: var(--pt-muted);
            font-size: 0.88rem;
        }
        .pt-file-path-meta span {
            color: var(--pt-muted);
        }
        .stDataFrame, div[data-testid="stDataFrame"] {
            border: 1px solid var(--pt-border);
            border-radius: 10px;
            overflow: hidden;
        }
        .pt-hero, .pt-card, .pt-login-card {
            background: var(--pt-panel);
            border: 1px solid var(--pt-border);
            border-radius: 12px;
            box-shadow: 0 12px 26px rgba(15, 23, 42, 0.08);
        }
        .pt-hero {
            padding: 1.3rem 1.4rem;
            border-left: 5px solid var(--pt-gold);
            margin-bottom: 1.1rem;
        }
        .pt-login-card {
            max-width: 780px;
            margin: 1.5rem auto 1rem auto;
            padding: 1.5rem 1.6rem;
        }
        .pt-card {
            padding: 1rem 1.1rem;
            margin: 0.75rem 0 1rem 0;
        }
        .pt-title {
            font-size: 1.6rem;
            font-weight: 750;
            color: var(--pt-navy);
            margin: 0 0 0.25rem 0;
        }
        .pt-subtitle, .pt-muted {
            color: var(--pt-muted);
            font-size: 0.98rem;
            margin: 0;
        }
        .pt-user-card {
            border: 1px solid rgba(255,255,255,0.25);
            background: rgba(255,255,255,0.09);
            border-radius: 10px;
            padding: 0.85rem 0.9rem;
            margin: 0.5rem 0 0.8rem 0;
        }
        .pt-user-card strong {
            display: block;
            font-size: 0.95rem;
            margin-bottom: 0.15rem;
        }
        .pt-user-card span {
            display: block;
            color: #dbeafe;
            font-size: 0.83rem;
        }
        .pt-badge {
            display: inline-block;
            border-radius: 999px;
            padding: 0.18rem 0.55rem;
            font-size: 0.78rem;
            font-weight: 700;
            border: 1px solid transparent;
        }
        .pt-badge.info { background: #e8f1fb; color: var(--pt-blue); border-color: #bfd7f2; }
        .pt-badge.success { background: #e9f7ef; color: var(--pt-green); border-color: #bfe8cf; }
        .pt-badge.warning { background: #fff7e6; color: var(--pt-amber); border-color: #f2d28f; }
        .pt-badge.error { background: #fff0ef; color: var(--pt-red); border-color: #f3b8b3; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_app_header(title: str, subtitle: str | None = None, badge: str | None = None) -> None:
    st = _st()
    subtitle_html = f"<p class='pt-subtitle'>{html.escape(subtitle)}</p>" if subtitle else ""
    badge_html = f" <span class='pt-badge info'>{html.escape(badge)}</span>" if badge else ""
    st.markdown(
        f"""
        <div class="pt-hero">
            <div class="pt-title">{html.escape(title)}{badge_html}</div>
            {subtitle_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_login_header() -> None:
    st = _st()
    st.markdown(
        f"""
        <div class="pt-login-card">
            <div class="pt-title">{html.escape(SYSTEM_NAME)}</div>
            <p class="pt-subtitle">Secure access for administrators and lecturers</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_training_banner() -> None:
    st = _st()
    st.markdown(
        """
        <div style="
            border: 1px solid #b45309;
            background: #fffbeb;
            color: #78350f;
            border-radius: 10px;
            padding: 0.75rem 1rem;
            margin: 0.5rem 0 1rem 0;
            font-weight: 700;
        ">
            TRAINING ENVIRONMENT, dummy data only.
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_user(username: str, role: str, display_name: str | None = None) -> None:
    st = _st()
    label = display_name or username
    st.sidebar.markdown(
        f"""
        <div class="pt-user-card">
            <strong>{html.escape(label)}</strong>
            <span>Username: {html.escape(username)}</span>
            <span>Role: {html.escape(role.title())}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_status_badge(label: str, status: str = "info") -> None:
    st = _st()
    safe_status = status if status in {"info", "success", "warning", "error"} else "info"
    st.markdown(f"<span class='pt-badge {safe_status}'>{html.escape(label)}</span>", unsafe_allow_html=True)
