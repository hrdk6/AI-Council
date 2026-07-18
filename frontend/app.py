import html
import re
from typing import Any
import requests
import streamlit as st

st.set_page_config(
    page_title="AI Council",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def escape_text(value: Any) -> str:
    """Safely prepare model and API output for a small HTML surface."""
    return html.escape(str(value)).replace("\n", "<br>")


def safe_member_value(member: dict[str, Any], key: str, fallback: str = "Not provided") -> str:
    return escape_text(member.get(key, fallback))


def render_member_card(member: dict[str, Any], revised: dict[str, Any] | None, index: int) -> None:
    role_name = safe_member_value(member, "role_name", "Council member")
    provider = safe_member_value(member, "provider", "Provider")
    model = safe_member_value(member, "model", "Model")

    if member.get("success"):
        first_take = f'<div class="analysis-copy">{safe_member_value(member, "content", "No analysis returned.")}</div>'
    else:
        first_take = f'<div class="analysis-error">{safe_member_value(member, "error", "This member could not complete its analysis.")}</div>'

    revised_take = ""
    if revised:
        if revised.get("success"):
            revised_content = f'<div class="analysis-copy">{safe_member_value(revised, "content", "No final position returned.")}</div>'
        else:
            revised_content = f'<div class="analysis-error">{safe_member_value(revised, "error", "This member could not revise its position.")}</div>'
        revised_take = f"""
            <div class="phase-divider"></div>
            <div class="phase-badge phase-two">Phase II &nbsp;·&nbsp; Final Position</div>
            {revised_content}
        """

    st.markdown(
        f"""
        <article class="member-card" style="animation-delay: {min(index * 0.07, 0.42):.2f}s;">
            <div class="member-head">
                <div class="member-avatar">{index + 1:02d}</div>
                <div class="member-meta">
                    <h3 class="member-name">{role_name}</h3>
                    <p class="member-model">{provider} &nbsp;/&nbsp; {model}</p>
                </div>
                <div class="member-status">
                    <span class="status-dot"></span>
                    Active
                </div>
            </div>
            <div class="phase-badge">Phase I &nbsp;·&nbsp; Independent Analysis</div>
            {first_take}
            {revised_take}
        </article>
        """,
        unsafe_allow_html=True,
    )


def reset_council() -> None:
    for key in ("council_result", "council_error", "council_prompt"):
        st.session_state.pop(key, None)


DIRECTIVE_HEADINGS = (
    "Recommendation",
    "Why this wins",
    "Execution plan",
    "Guardrails and reversal triggers",
    "Confidence and key uncertainty",
)

_DIRECTIVE_HEADING_RE = re.compile(
    r"^(Recommendation|Why this wins|Execution plan|Guardrails and reversal triggers|Confidence and key uncertainty)\\s*:?\\s*$",
    re.IGNORECASE,
)


def parse_directive(value: Any) -> list[tuple[str, str]]:
    """Turn the chairman's fixed-format decision memo into readable report sections."""
    sections: list[tuple[str, list[str]]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in str(value or "").splitlines():
        match = _DIRECTIVE_HEADING_RE.match(line.strip())
        if match:
            if current_heading is not None:
                sections.append((current_heading, current_lines))
            current_heading = next(
                heading for heading in DIRECTIVE_HEADINGS if heading.lower() == match.group(1).lower()
            )
            current_lines = []
        elif current_heading is not None:
            current_lines.append(line)
        else:
            current_lines.append(line)

    if current_heading is not None:
        sections.append((current_heading, current_lines))

    if not sections:
        return [("Recommendation", str(value or "No final answer was returned."))]
    return [(heading, "\n".join(lines).strip() or "No details returned.") for heading, lines in sections]


def decision_brief_text(result: dict[str, Any]) -> str:
    """Create a portable plain-text record without exposing raw HTML."""
    return (
        f"AI COUNCIL | DECISION BRIEF\n{'=' * 32}"
        f"\n\nQUESTION\n{result.get('question', st.session_state.get('council_prompt', 'Not recorded'))}"
        f"\n\nDECISION CHARTER\n{result.get('decision_charter', 'Not returned by the backend.')}"
        f"\n\nFINAL DIRECTIVE\n{result.get('final_answer', 'No final answer was returned.')}\n"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Global CSS — Premium SaaS aesthetic (Linear / Vercel / Notion-inspired)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500;600&display=swap');

    /* ── Tokens ── */
    :root {
        /* Surfaces */
        --bg:          #0a0a0b;
        --bg-raised:   #111113;
        --bg-subtle:   #18181b;
        --bg-overlay:  rgba(255,255,255,0.04);

        /* Borders */
        --border:      rgba(255,255,255,0.08);
        --border-hi:   rgba(255,255,255,0.14);
        --border-focus:rgba(124,58,237,0.6);

        /* Accent — violet */
        --accent:      #7c3aed;
        --accent-hi:   #8b5cf6;
        --accent-soft: rgba(124,58,237,0.12);
        --accent-glow: rgba(124,58,237,0.20);

        /* Status */
        --success:     #22c55e;
        --error:       #ef4444;
        --warning:     #f59e0b;

        /* Typography */
        --text-hi:     #fafafa;
        --text:        #a1a1aa;
        --text-dim:    #52525b;
        --text-accent: #c4b5fd;

        /* Type scale */
        --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        --font-mono: 'Geist Mono', 'JetBrains Mono', monospace;

        /* Shadows */
        --shadow-sm:   0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px var(--border);
        --shadow-md:   0 4px 16px rgba(0,0,0,0.5), 0 0 0 1px var(--border);
        --shadow-lg:   0 12px 40px rgba(0,0,0,0.6), 0 0 0 1px var(--border);

        /* Radius */
        --r-sm:  6px;
        --r-md:  10px;
        --r-lg:  14px;
    }

    /* ── Reset & Base ── */
    *, *::before, *::after { box-sizing: border-box; }

    html, body,
    [data-testid="stAppViewContainer"],
    [data-testid="stApp"] {
        background: var(--bg) !important;
        color: var(--text) !important;
        font-family: var(--font-sans) !important;
        -webkit-font-smoothing: antialiased !important;
        -moz-osx-font-smoothing: grayscale !important;
    }

    /* Subtle vignette */
    [data-testid="stAppViewContainer"] {
        background-image:
            radial-gradient(ellipse 80% 50% at 50% -10%, rgba(124,58,237,0.08) 0%, transparent 60%) !important;
        background-attachment: fixed !important;
    }

    /* Hide Streamlit chrome */
    #MainMenu, header, footer,
    [data-testid="stToolbar"],
    [data-testid="stStatusWidget"],
    [data-testid="stDecoration"] { display: none !important; }

    .block-container {
        max-width: 1200px !important;
        padding: 0 2rem 8rem !important;
        margin: 0 auto !important;
    }

    [data-testid="stVerticalBlockBorderWrapper"] { background: transparent !important; }

    ::selection { background: rgba(124,58,237,0.28); color: var(--text-hi); }

    ::-webkit-scrollbar { width: 5px; background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--bg-subtle); border-radius: 99px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.1); }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background: var(--bg-raised) !important;
        border-right: 1px solid var(--border) !important;
    }
    [data-testid="stSidebar"] * {
        color: var(--text) !important;
        font-family: var(--font-sans) !important;
        font-size: 0.78rem !important;
    }
    [data-testid="stSidebar"] h3 {
        color: var(--text-hi) !important;
        font-size: 0.7rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.05em !important;
        text-transform: uppercase !important;
    }
    [data-testid="stSidebar"] input {
        background: var(--bg-subtle) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--r-sm) !important;
        color: var(--text-hi) !important;
        font-family: var(--font-mono) !important;
        font-size: 0.72rem !important;
        padding: 0.45rem 0.65rem !important;
        transition: border-color 0.15s !important;
    }
    [data-testid="stSidebar"] input:focus {
        border-color: var(--border-focus) !important;
        outline: none !important;
        box-shadow: 0 0 0 3px var(--accent-soft) !important;
    }

    /* ── Topbar / Nav ── */
    .site-nav {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0;
        height: 64px;
        border-bottom: 1px solid var(--border);
        animation: fade-up 0.4s ease both;
        margin-bottom: 0;
    }

    .brand {
        display: flex;
        align-items: center;
        gap: 0.85rem;
    }

    .brand-mark {
        width: 30px;
        height: 30px;
        background: var(--accent-soft);
        border: 1px solid rgba(124,58,237,0.3);
        border-radius: var(--r-sm);
        display: grid;
        place-items: center;
        font-size: 0.9rem;
    }

    .brand-text .brand-name {
        display: block;
        font-size: 0.85rem;
        font-weight: 600;
        color: var(--text-hi);
        letter-spacing: -0.01em;
        line-height: 1;
    }

    .brand-text .brand-sub {
        display: block;
        font-size: 0.67rem;
        color: var(--text-dim);
        margin-top: 2px;
        font-family: var(--font-mono);
        letter-spacing: 0.02em;
    }

    .nav-pills {
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .nav-pill {
        display: flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.3rem 0.7rem;
        border-radius: 99px;
        font-size: 0.68rem;
        font-weight: 500;
        letter-spacing: 0.01em;
        font-family: var(--font-mono);
    }

    .nav-pill.online {
        background: rgba(34,197,94,0.1);
        color: #4ade80;
        border: 1px solid rgba(34,197,94,0.2);
    }

    .nav-pill.ready {
        background: var(--accent-soft);
        color: var(--text-accent);
        border: 1px solid rgba(124,58,237,0.25);
    }

    .nav-dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
    }
    .nav-dot.green { background: var(--success); box-shadow: 0 0 5px var(--success); animation: pulse 2.2s ease-in-out infinite; }
    .nav-dot.violet { background: var(--accent-hi); }

    /* ── Hero ── */
    .hero {
        padding: 6rem 0 4rem;
        max-width: 780px;
        animation: fade-up 0.5s 0.05s ease both;
    }

    .hero-eyebrow {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 1.6rem;
        padding: 0.3rem 0.8rem 0.3rem 0.4rem;
        background: var(--accent-soft);
        border: 1px solid rgba(124,58,237,0.25);
        border-radius: 99px;
        font-size: 0.68rem;
        font-weight: 500;
        color: var(--text-accent);
        font-family: var(--font-mono);
        letter-spacing: 0.03em;
    }

    .hero-eyebrow .eyebrow-dot {
        width: 5px;
        height: 5px;
        border-radius: 50%;
        background: var(--accent-hi);
    }

    .hero h1 {
        margin: 0;
        font-size: clamp(2.8rem, 5.5vw, 4.8rem);
        font-weight: 700;
        letter-spacing: -0.04em;
        line-height: 1.05;
        color: var(--text-hi);
    }

    .hero h1 .gradient-word {
        background: linear-gradient(135deg, #a78bfa 0%, #7c3aed 50%, #6d28d9 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }

    .hero-sub {
        margin: 1.4rem 0 0;
        color: var(--text);
        font-size: 1.05rem;
        line-height: 1.75;
        max-width: 540px;
        font-weight: 400;
    }

    .process-strip {
        display: flex;
        gap: 0;
        margin-top: 3rem;
        border: 1px solid var(--border);
        border-radius: var(--r-md);
        overflow: hidden;
        background: var(--bg-raised);
    }

    .process-step {
        flex: 1;
        padding: 1rem 1.1rem;
        border-right: 1px solid var(--border);
        transition: background 0.2s;
    }
    .process-step:last-child { border-right: none; }
    .process-step:hover { background: var(--bg-subtle); }

    .process-step .step-num {
        display: block;
        font-family: var(--font-mono);
        font-size: 0.6rem;
        font-weight: 500;
        color: var(--accent-hi);
        letter-spacing: 0.06em;
        margin-bottom: 0.45rem;
    }
    .process-step .step-label {
        display: block;
        font-size: 0.72rem;
        font-weight: 500;
        color: var(--text-hi);
        margin-bottom: 0.2rem;
    }
    .process-step .step-desc {
        display: block;
        font-size: 0.68rem;
        line-height: 1.5;
        color: var(--text-dim);
    }

    /* ── Input card ── */
    .input-card {
        position: relative;
        margin-top: 0.5rem;
        padding: clamp(1.4rem, 3vw, 2.2rem);
        background: var(--bg-raised);
        border: 1px solid var(--border);
        border-radius: var(--r-lg);
        animation: fade-up 0.5s 0.08s ease both;
        overflow: hidden;
    }

    .input-card::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(124,58,237,0.5), transparent);
    }

    .card-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        margin-bottom: 1.5rem;
    }

    .card-title {
        font-size: 0.92rem;
        font-weight: 600;
        color: var(--text-hi);
        letter-spacing: -0.01em;
        margin: 0;
    }

    .card-badge {
        font-family: var(--font-mono);
        font-size: 0.62rem;
        font-weight: 500;
        color: var(--text-accent);
        background: var(--accent-soft);
        border: 1px solid rgba(124,58,237,0.25);
        border-radius: var(--r-sm);
        padding: 0.22rem 0.55rem;
        letter-spacing: 0.04em;
    }

    /* ── Streamlit inputs overrides ── */
    div[data-testid="stTextArea"] label,
    div[data-testid="stFileUploader"] label {
        color: var(--text-dim) !important;
        font-family: var(--font-mono) !important;
        font-size: 0.65rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.06em !important;
        text-transform: uppercase !important;
    }

    .stTextArea textarea {
        min-height: 140px !important;
        padding: 0.9rem 1rem !important;
        background: var(--bg-subtle) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--r-md) !important;
        color: var(--text-hi) !important;
        font-family: var(--font-sans) !important;
        font-size: 0.9rem !important;
        line-height: 1.75 !important;
        transition: border-color 0.15s, box-shadow 0.15s !important;
        caret-color: var(--accent-hi) !important;
        resize: vertical !important;
    }

    .stTextArea textarea::placeholder { color: var(--text-dim) !important; }

    .stTextArea textarea:focus {
        border-color: var(--border-focus) !important;
        box-shadow: 0 0 0 3px var(--accent-soft) !important;
        outline: none !important;
    }

    [data-testid="stFileUploader"] {
        background: var(--bg-subtle) !important;
        border: 1px dashed rgba(255,255,255,0.1) !important;
        border-radius: var(--r-md) !important;
        transition: border-color 0.15s !important;
    }
    [data-testid="stFileUploader"]:hover { border-color: rgba(124,58,237,0.35) !important; }
    [data-testid="stFileUploader"] * {
        color: var(--text) !important;
        font-family: var(--font-sans) !important;
        font-size: 0.78rem !important;
    }
    [data-testid="stFileUploader"] button {
        background: var(--bg-overlay) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--r-sm) !important;
        color: var(--text-hi) !important;
        font-family: var(--font-sans) !important;
        font-size: 0.72rem !important;
        font-weight: 500 !important;
    }

    .form-hint {
        padding: 0.85rem 1rem;
        background: var(--bg-overlay);
        border: 1px solid var(--border);
        border-radius: var(--r-md);
        font-size: 0.72rem;
        line-height: 1.7;
        color: var(--text-dim);
    }
    .form-hint strong { color: var(--text); font-weight: 500; }

    /* ── Buttons ── */
    .stButton > button {
        min-height: 44px !important;
        width: 100% !important;
        border-radius: var(--r-md) !important;
        font-family: var(--font-sans) !important;
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        letter-spacing: -0.01em !important;
        transition: all 0.15s ease !important;
        cursor: pointer !important;
    }

    .stButton > button[kind="primary"] {
        background: var(--accent) !important;
        border: 1px solid rgba(124,58,237,0.6) !important;
        color: #fff !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px rgba(124,58,237,0.3), inset 0 1px 0 rgba(255,255,255,0.1) !important;
    }

    .stButton > button[kind="primary"]:hover {
        background: var(--accent-hi) !important;
        box-shadow: 0 4px 16px rgba(124,58,237,0.4), 0 0 0 1px rgba(124,58,237,0.5), inset 0 1px 0 rgba(255,255,255,0.12) !important;
        transform: translateY(-1px) !important;
    }

    .stButton > button[kind="primary"]:active {
        transform: translateY(0) !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.4) !important;
    }

    .stButton > button[kind="secondary"],
    .stButton > button:not([kind="primary"]) {
        background: var(--bg-overlay) !important;
        border: 1px solid var(--border) !important;
        color: var(--text) !important;
    }

    .stButton > button:not([kind="primary"]):hover {
        border-color: var(--border-hi) !important;
        color: var(--text-hi) !important;
        background: rgba(255,255,255,0.06) !important;
    }

    /* ── Alerts / Spinner ── */
    [data-testid="stAlert"] {
        border-radius: var(--r-md) !important;
        font-family: var(--font-sans) !important;
    }
    [data-testid="stAlert"] p { font-size: 0.82rem !important; line-height: 1.6 !important; }

    [data-testid="stAlert"]:has([data-testid="stNotificationContentWarning"]) {
        background: rgba(245,158,11,0.08) !important;
        border: 1px solid rgba(245,158,11,0.25) !important;
        color: #fbbf24 !important;
    }
    [data-testid="stAlert"]:has([data-testid="stNotificationContentError"]) {
        background: rgba(239,68,68,0.08) !important;
        border: 1px solid rgba(239,68,68,0.25) !important;
        color: #f87171 !important;
    }

    [data-testid="stSpinner"] p {
        color: var(--text) !important;
        font-family: var(--font-sans) !important;
        font-size: 0.82rem !important;
    }

    /* ── Section divider ── */
    .section-header {
        display: flex;
        align-items: center;
        gap: 1rem;
        margin: 4.5rem 0 2.5rem;
    }

    .section-header-line {
        flex: 1;
        height: 1px;
        background: var(--border);
    }

    .section-header-label {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.72rem;
        font-weight: 500;
        color: var(--text-dim);
        letter-spacing: 0.05em;
        text-transform: uppercase;
        font-family: var(--font-mono);
        white-space: nowrap;
    }

    .section-header-dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: var(--accent-hi);
    }

    /* ── Results / Directive ── */
    .result-header { margin-bottom: 2rem; }

    .result-eyebrow {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.28rem 0.7rem;
        background: rgba(34,197,94,0.1);
        border: 1px solid rgba(34,197,94,0.2);
        border-radius: 99px;
        font-size: 0.65rem;
        font-weight: 500;
        color: #4ade80;
        font-family: var(--font-mono);
        letter-spacing: 0.03em;
        margin-bottom: 1rem;
    }

    .result-eyebrow .result-dot {
        width: 5px;
        height: 5px;
        border-radius: 50%;
        background: var(--success);
        box-shadow: 0 0 4px var(--success);
    }

    .result-title {
        font-size: clamp(1.9rem, 3.5vw, 2.8rem);
        font-weight: 700;
        letter-spacing: -0.04em;
        color: var(--text-hi);
        line-height: 1.1;
        margin: 0;
    }

    /* Directive grid */
    .directive-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 1px;
        background: var(--border);
        border: 1px solid var(--border);
        border-radius: var(--r-lg);
        overflow: hidden;
    }

    .directive-section {
        padding: 1.5rem;
        background: var(--bg-raised);
        position: relative;
        transition: background 0.18s;
    }

    .directive-section:hover { background: var(--bg-subtle); }

    .directive-section:first-child {
        grid-column: 1 / -1;
        background: linear-gradient(135deg, rgba(124,58,237,0.1) 0%, var(--bg-raised) 60%);
        border-bottom: 1px solid var(--border);
    }

    .directive-section:first-child:hover {
        background: linear-gradient(135deg, rgba(124,58,237,0.14) 0%, var(--bg-subtle) 60%);
    }

    .directive-section .sec-label {
        display: flex;
        align-items: center;
        gap: 0.4rem;
        font-size: 0.65rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: var(--text-accent);
        font-family: var(--font-mono);
        margin-bottom: 0.6rem;
    }

    .directive-section .sec-num {
        font-family: var(--font-mono);
        font-size: 0.6rem;
        color: var(--text-dim);
        position: absolute;
        top: 1.2rem;
        right: 1.2rem;
    }

    .directive-section p {
        font-size: 0.88rem;
        line-height: 1.8;
        color: var(--text);
        margin: 0;
    }

    .directive-section:first-child p {
        font-size: 0.94rem;
        color: var(--text-hi);
    }

    /* Export row */
    .export-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        margin-top: 1.2rem;
    }

    .export-note {
        font-size: 0.75rem;
        color: var(--text-dim);
        line-height: 1.5;
    }

    [data-testid="stDownloadButton"] button {
        min-height: 38px !important;
        width: auto !important;
        padding: 0.45rem 1rem !important;
        background: var(--bg-overlay) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--r-sm) !important;
        color: var(--text) !important;
        font-family: var(--font-sans) !important;
        font-size: 0.75rem !important;
        font-weight: 500 !important;
        letter-spacing: 0 !important;
        box-shadow: none !important;
        transition: all 0.15s !important;
    }

    [data-testid="stDownloadButton"] button:hover {
        border-color: var(--border-hi) !important;
        color: var(--text-hi) !important;
        background: rgba(255,255,255,0.06) !important;
    }

    /* ── Expander (audit log) ── */
    [data-testid="stExpander"] {
        margin-top: 2rem !important;
        background: var(--bg-raised) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--r-md) !important;
        overflow: hidden !important;
    }

    [data-testid="stExpander"] summary {
        padding: 1rem 1.2rem !important;
        color: var(--text) !important;
        font-family: var(--font-sans) !important;
        font-size: 0.78rem !important;
        font-weight: 500 !important;
        letter-spacing: -0.01em !important;
        text-transform: none !important;
    }

    [data-testid="stExpander"] summary:hover { color: var(--text-hi) !important; }

    [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
        padding: 0.5rem 1rem 1.4rem !important;
        border-top: 1px solid var(--border) !important;
    }

    .audit-intro {
        max-width: 660px;
        margin: 0.8rem 0 1.5rem;
        font-size: 0.78rem;
        line-height: 1.7;
        color: var(--text-dim);
    }

    /* ── Member cards ── */
    [data-testid="column"] { padding: 0 0.3rem !important; }

    .member-card {
        padding: 1.2rem;
        background: var(--bg-raised);
        border: 1px solid var(--border);
        border-radius: var(--r-md);
        margin: 0.3rem 0;
        height: 100%;
        animation: fade-up 0.4s ease both;
        transition: border-color 0.18s, box-shadow 0.18s;
        position: relative;
    }

    .member-card:hover {
        border-color: var(--border-hi);
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }

    .member-head {
        display: flex;
        align-items: flex-start;
        gap: 0.75rem;
        padding-bottom: 1rem;
        margin-bottom: 1rem;
        border-bottom: 1px solid var(--border);
    }

    .member-avatar {
        flex-shrink: 0;
        width: 32px;
        height: 32px;
        border-radius: var(--r-sm);
        background: var(--accent-soft);
        border: 1px solid rgba(124,58,237,0.25);
        display: grid;
        place-items: center;
        font-family: var(--font-mono);
        font-size: 0.62rem;
        font-weight: 600;
        color: var(--text-accent);
    }

    .member-meta { flex: 1; min-width: 0; }

    .member-name {
        margin: 0 0 0.2rem;
        font-size: 0.85rem;
        font-weight: 600;
        color: var(--text-hi);
        font-family: var(--font-sans);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .member-model {
        margin: 0;
        font-family: var(--font-mono);
        font-size: 0.6rem;
        color: var(--text-dim);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .member-status {
        display: flex;
        align-items: center;
        gap: 0.35rem;
        font-size: 0.62rem;
        font-weight: 500;
        color: #4ade80;
        white-space: nowrap;
        flex-shrink: 0;
    }

    .status-dot {
        width: 5px;
        height: 5px;
        border-radius: 50%;
        background: var(--success);
        box-shadow: 0 0 4px var(--success);
    }

    .phase-badge {
        display: inline-flex;
        align-items: center;
        padding: 0.18rem 0.5rem;
        border-radius: var(--r-sm);
        font-family: var(--font-mono);
        font-size: 0.58rem;
        font-weight: 500;
        letter-spacing: 0.04em;
        color: var(--text-accent);
        background: var(--accent-soft);
        border: 1px solid rgba(124,58,237,0.2);
        margin-bottom: 0.65rem;
    }

    .phase-two {
        color: #4ade80;
        background: rgba(34,197,94,0.08);
        border-color: rgba(34,197,94,0.2);
    }

    .analysis-copy {
        font-size: 0.8rem;
        line-height: 1.75;
        color: var(--text);
        overflow-wrap: anywhere;
        font-family: var(--font-sans);
    }

    .analysis-error {
        font-size: 0.8rem;
        line-height: 1.75;
        color: rgba(239,68,68,0.75);
        font-family: var(--font-sans);
    }

    .phase-divider {
        height: 1px;
        background: var(--border);
        margin: 1rem 0 0.85rem;
    }

    .empty-audit {
        padding: 1.4rem;
        color: var(--text-dim);
        border: 1px dashed var(--border);
        border-radius: var(--r-md);
        font-size: 0.8rem;
        font-family: var(--font-sans);
        text-align: center;
    }

    /* ── Animations ── */
    @keyframes fade-up {
        from { opacity: 0; transform: translateY(8px); }
        to   { opacity: 1; transform: translateY(0); }
    }

    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.45; }
    }

    /* ── Responsive ── */
    @media (max-width: 700px) {
        .block-container { padding: 0 1rem 5rem !important; }
        .hero { padding: 3.5rem 0 2.5rem; }
        .process-strip { flex-direction: column; }
        .process-step { border-right: none; border-bottom: 1px solid var(--border); }
        .process-step:last-child { border-bottom: none; }
        .directive-grid { grid-template-columns: 1fr; }
        .directive-section:first-child { grid-column: auto; }
        .export-row { flex-direction: column; align-items: flex-start; }
        .nav-pills { gap: 0.3rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### // Config")
    backend_url = st.text_input(
        "Backend endpoint",
        value=st.session_state.get("backend_url", "http://localhost:8000"),
        help="Base URL for the FastAPI service. Requests are sent to /ask.",
    ).rstrip("/")
    st.session_state.backend_url = backend_url
    st.caption("→ Use deployed endpoint URL in production.")
    st.divider()
    if st.button("Reset session", use_container_width=True):
        reset_council()
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Navigation
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <nav class="site-nav">
        <div class="brand">
            <div class="brand-mark">⬡</div>
            <div class="brand-text">
                <span class="brand-name">AI Council</span>
                <span class="brand-sub">Multi-agent decision framework &nbsp;·&nbsp; v2.1</span>
            </div>
        </div>
        <div class="nav-pills">
            <span class="nav-pill online"><span class="nav-dot green"></span>Nodes online</span>
            <span class="nav-pill ready"><span class="nav-dot violet"></span>Ready</span>
        </div>
    </nav>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Hero
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <section class="hero">
        <div class="hero-eyebrow">
            <span class="eyebrow-dot"></span>
            SYS:AIC-001 &nbsp;·&nbsp; Consensus Engine
        </div>
        <h1>Structured <span class="gradient-word">intelligence</span><br>for hard decisions.</h1>
        <p class="hero-sub">Submit a decision problem. The council frames it, stress-tests assumptions in parallel, and returns a single structured directive — with guardrails baked in.</p>
        <div class="process-strip">
            <div class="process-step">
                <span class="step-num">01</span>
                <span class="step-label">Frame</span>
                <span class="step-desc">Clarify the decision and its criteria.</span>
            </div>
            <div class="process-step">
                <span class="step-num">02</span>
                <span class="step-label">Analyze</span>
                <span class="step-desc">Specialist nodes assess independently.</span>
            </div>
            <div class="process-step">
                <span class="step-num">03</span>
                <span class="step-label">Challenge</span>
                <span class="step-desc">Claims and biases are pressure-tested.</span>
            </div>
            <div class="process-step">
                <span class="step-num">04</span>
                <span class="step-label">Direct</span>
                <span class="step-desc">One actionable output with guardrails.</span>
            </div>
        </div>
    </section>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Input card
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="input-card">
        <div class="card-header">
            <h2 class="card-title">Input Brief</h2>
            <span class="card-badge">Step 01</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

prompt = st.text_area(
    "Decision query",
    value=st.session_state.get("council_prompt", ""),
    height=148,
    placeholder="Describe the decision, scenario, or strategic question for the council to examine...",
)

upload_col, hint_col = st.columns([1.1, 1], gap="large")
with upload_col:
    uploaded_files = st.file_uploader(
        "Supporting material (up to 5 files)",
        type=["pdf", "png", "jpg", "jpeg", "webp"],
        help="Add up to five PDFs or images. They will be considered by all council nodes.",
        accept_multiple_files=True,
    )

with hint_col:
    st.markdown(
        """
        <div class="form-hint">
            <strong>How it works</strong><br>
            Frame → Analyze → Challenge → Direct<br><br>
            The council identifies decision criteria, stress-tests assumptions, and surfaces a final directive with explicit guardrails and reversal conditions.
        </div>
        """,
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# Primary action
# ─────────────────────────────────────────────────────────────────────────────
ask_clicked = st.button("Initiate deliberation", type="primary", use_container_width=True)

if ask_clicked:
    if not prompt.strip():
        st.warning("Decision query is empty. Add a brief before initiating deliberation.")
    elif not backend_url:
        st.warning("Backend endpoint not configured. Set it in the sidebar.")
    else:
        st.session_state.council_error = None
        st.session_state.council_result = None
        st.session_state.council_prompt = prompt

        files = [
            (
                "files",
                (
                    uploaded_file.name,
                    uploaded_file.getvalue(),
                    uploaded_file.type or "application/octet-stream",
                ),
            )
            for uploaded_file in uploaded_files
        ]

        try:
            with st.spinner("Council nodes are processing your brief — estimated 60–120 seconds…"):
                response = requests.post(
                    f"{backend_url}/ask",
                    data={"prompt": prompt},
                    files=files or None,
                    timeout=(10, 240),
                )
                response.raise_for_status()
                payload = response.json()

            if not isinstance(payload, dict) or not payload.get("final_answer"):
                raise ValueError("The backend returned an incomplete council response.")

            st.session_state.council_result = payload

        except requests.exceptions.ConnectionError:
            st.session_state.council_error = (
                f"Connection refused at {backend_url}. Verify the backend service is running and the endpoint is correct."
            )
        except requests.exceptions.Timeout:
            st.session_state.council_error = "Request timed out. The council did not respond within 240 seconds. Check backend logs."
        except requests.exceptions.HTTPError as error:
            try:
                detail = error.response.json().get("detail", error.response.text)
            except (ValueError, AttributeError):
                detail = getattr(error.response, "text", str(error))
            st.session_state.council_error = f"Error {error.response.status_code}: {detail}"
        except (ValueError, requests.exceptions.RequestException) as error:
            st.session_state.council_error = f"Unexpected error: {error}"

if st.session_state.get("council_error"):
    st.error(st.session_state.council_error)

# ─────────────────────────────────────────────────────────────────────────────
# Results
# ─────────────────────────────────────────────────────────────────────────────
result = st.session_state.get("council_result")

if result:
    st.markdown(
        """
        <div class="section-header">
            <div class="section-header-label">
                <div class="section-header-dot"></div>
                Decision Report
            </div>
            <div class="section-header-line"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="result-header">
            <div class="result-eyebrow">
                <span class="result-dot"></span>
                Consensus reached
            </div>
            <h2 class="result-title">Final Decision Output</h2>
        </div>
        """,
        unsafe_allow_html=True,
    )

    directive_sections = parse_directive(result.get("final_answer"))
    directive_html = "".join(
        f"""
        <div class="directive-section">
            <span class="sec-num">{i + 1:02d}</span>
            <div class="sec-label">{escape_text(heading)}</div>
            <p>{escape_text(content)}</p>
        </div>
        """
        for i, (heading, content) in enumerate(directive_sections)
    )
    st.markdown(f'<div class="directive-grid">{directive_html}</div>', unsafe_allow_html=True)

    export_left, export_right = st.columns([1.4, 0.6])
    with export_left:
        st.markdown(
            '<p class="export-note">Record includes the original query, decision charter, and full directive.</p>',
            unsafe_allow_html=True,
        )
    with export_right:
        st.download_button(
            "Export brief",
            data=decision_brief_text(result),
            file_name="ai-council-decision-brief.txt",
            mime="text/plain",
            use_container_width=True,
        )

    # Audit log
    with st.expander("View council deliberation record", expanded=False):
        st.markdown(
            '<p class="audit-intro">Each node produces an independent analysis (Phase I), then may revise its position after reviewing peer responses (Phase II). The full record is preserved below.</p>',
            unsafe_allow_html=True,
        )

        round_one = result.get("round1") or []
        round_two = result.get("round2") or []
        round_two_by_key = {
            entry.get("key"): entry
            for entry in round_two
            if isinstance(entry, dict) and entry.get("key")
        }
        members = [member for member in round_one if isinstance(member, dict)]

        if not members:
            st.markdown(
                '<div class="empty-audit">No individual deliberation record was returned for this request.</div>',
                unsafe_allow_html=True,
            )
        else:
            for row_start in range(0, len(members), 3):
                row = members[row_start: row_start + 3]
                columns = st.columns(3, gap="medium")
                for offset, member in enumerate(row):
                    with columns[offset]:
                        render_member_card(
                            member,
                            round_two_by_key.get(member.get("key")),
                            row_start + offset,
                        )