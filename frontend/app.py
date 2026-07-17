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
            <div class="phase-rule"></div>
            <div class="phase-label phase-two">PHZ-II &middot; FINAL POSITION</div>
            {revised_content}
        """
    st.markdown(
        f"""
        <article class="member-card" style="animation-delay: {min(index * 0.06, 0.3):.2f}s;">
            <div class="member-head">
                <div class="member-meta">
                    <div class="member-id">NODE_{index + 1:02d}</div>
                    <h3>{role_name}</h3>
                    <p class="member-model">{provider} / {model}</p>
                </div>
                <div class="member-status"><span class="status-pip active"></span>ACTIVE</div>
            </div>
            <div class="phase-label">PHZ-I &middot; INDEPENDENT ANALYSIS</div>
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
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');
    :root {
        --bg:        #080c10;
        --bg-1:      #0c1117;
        --bg-2:      #101620;
        --bg-3:      #151d28;
        --surface:   rgba(16, 22, 32, 0.92);
        --border:    rgba(0, 180, 255, 0.12);
        --border-hi: rgba(0, 220, 255, 0.35);
        --cyan:      #00d4ff;
        --cyan-dim:  rgba(0, 212, 255, 0.6);
        --cyan-glow: rgba(0, 212, 255, 0.08);
        --green:     #00e5a0;
        --green-dim: rgba(0, 229, 160, 0.55);
        --amber:     #f5a623;
        --amber-dim: rgba(245, 166, 35, 0.55);
        --red:       #ff4757;
        --text:      #c8d8e8;
        --text-dim:  #5a7a94;
        --text-hi:   #e8f4ff;
        --mono:      'JetBrains Mono', 'Courier New', monospace;
        --sans:      'Space Grotesk', 'Inter', sans-serif;
        --shadow:    0 0 0 1px var(--border), 0 8px 32px rgba(0, 10, 20, 0.6);
        --glow-cyan: 0 0 20px rgba(0, 212, 255, 0.15), 0 0 60px rgba(0, 212, 255, 0.05);
    }
    * { box-sizing: border-box; }
    html, body, [data-testid="stAppViewContainer"] {
        background: var(--bg) !important;
        color: var(--text) !important;
        font-family: var(--sans) !important;
    }
    /* Scanline + grid texture */
    [data-testid="stAppViewContainer"] {
        background-image:
            linear-gradient(rgba(0, 212, 255, 0.025) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0, 212, 255, 0.025) 1px, transparent 1px),
            radial-gradient(ellipse at 70% 0%, rgba(0, 180, 255, 0.07) 0%, transparent 55%),
            radial-gradient(ellipse at 20% 80%, rgba(0, 229, 160, 0.04) 0%, transparent 45%) !important;
        background-size: 40px 40px, 40px 40px, 100% 100%, 100% 100% !important;
    }
    /* Scanline overlay */
    [data-testid="stAppViewContainer"]::after {
        content: '';
        position: fixed;
        inset: 0;
        pointer-events: none;
        background: repeating-linear-gradient(
            0deg,
            transparent,
            transparent 2px,
            rgba(0,0,0,0.07) 2px,
            rgba(0,0,0,0.07) 4px
        );
        z-index: 9999;
    }
    [data-testid="stMain"], .block-container { position: relative; z-index: 1; }
    #MainMenu, header, footer, [data-testid="stToolbar"], [data-testid="stStatusWidget"], [data-testid="stDecoration"] { display: none !important; }
    .block-container { max-width: 1320px !important; padding: 0 2rem 6rem !important; }
    [data-testid="stVerticalBlockBorderWrapper"] { background: transparent !important; }
    ::selection { background: rgba(0, 212, 255, 0.2); color: #fff; }
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: var(--bg-1); }
    ::-webkit-scrollbar-thumb { background: rgba(0, 212, 255, 0.2); border-radius: 0; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(0, 212, 255, 0.4); }
    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background: var(--bg-1) !important;
        border-right: 1px solid var(--border) !important;
    }
    [data-testid="stSidebar"] * { color: var(--text) !important; font-family: var(--mono) !important; font-size: .75rem !important; }
    [data-testid="stSidebar"] h3 { color: var(--cyan) !important; font-size: .7rem !important; letter-spacing: .12em !important; text-transform: uppercase !important; }
    [data-testid="stSidebar"] input {
        background: var(--bg-2) !important;
        border: 1px solid var(--border) !important;
        border-radius: 0 !important;
        color: var(--cyan) !important;
        font-family: var(--mono) !important;
        font-size: .73rem !important;
    }
    [data-testid="stSidebar"] input:focus { border-color: var(--cyan) !important; box-shadow: 0 0 0 2px rgba(0,212,255,.12) !important; }
    /* ── Topbar / Nav ── */
    .site-nav {
        display: flex; align-items: center; justify-content: space-between;
        min-height: 56px;
        border-bottom: 1px solid var(--border);
        animation: rise .4s ease both;
    }
    .brand { display: flex; align-items: center; gap: 1rem; }
    .brand-hex {
        width: 32px; height: 32px;
        border: 1px solid var(--cyan);
        clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
        background: rgba(0, 212, 255, 0.08);
        display: grid; place-items: center;
        font-family: var(--mono);
        font-size: .65rem;
        color: var(--cyan);
        box-shadow: 0 0 12px rgba(0,212,255,0.2);
    }
    .brand-name {
        font-family: var(--mono);
        font-size: .7rem;
        font-weight: 600;
        letter-spacing: .2em;
        text-transform: uppercase;
        color: var(--text-hi);
    }
    .brand-version {
        font-family: var(--mono);
        font-size: .55rem;
        color: var(--text-dim);
        letter-spacing: .08em;
    }
    .nav-right { display: flex; align-items: center; gap: 1.5rem; }
    .nav-stat {
        display: flex; align-items: center; gap: .5rem;
        font-family: var(--mono);
        font-size: .58rem;
        letter-spacing: .1em;
        text-transform: uppercase;
        color: var(--text-dim);
    }
    .nav-stat .pip { width: 6px; height: 6px; border-radius: 50%; }
    .pip.online { background: var(--green); box-shadow: 0 0 6px var(--green); animation: pulse 2s infinite; }
    .pip.ready  { background: var(--cyan);  box-shadow: 0 0 6px var(--cyan); }
    /* ── Hero ── */
    .hero { max-width: 900px; padding: 5rem 0 3.5rem; animation: rise .6s .06s ease both; }
    .sys-id {
        display: inline-flex; align-items: center; gap: .65rem;
        margin-bottom: 1.5rem;
        font-family: var(--mono);
        font-size: .62rem;
        letter-spacing: .14em;
        text-transform: uppercase;
        color: var(--cyan-dim);
    }
    .sys-id::before { content: ''; display: inline-block; width: 24px; height: 1px; background: var(--cyan); }
    .hero h1 {
        margin: 0;
        font-family: var(--sans);
        font-size: clamp(2.8rem, 6vw, 5.2rem);
        font-weight: 700;
        letter-spacing: -.04em;
        line-height: 1;
        color: var(--text-hi);
    }
    .hero h1 .accent { color: var(--cyan); position: relative; }
    .hero h1 .accent::after {
        content: '';
        position: absolute;
        bottom: 4px; left: 0; right: 0;
        height: 2px;
        background: linear-gradient(90deg, var(--cyan), transparent);
    }
    .hero-sub {
        margin: 1.2rem 0 0;
        color: var(--text-dim);
        font-size: .92rem;
        line-height: 1.85;
        max-width: 580px;
        font-family: var(--sans);
    }
    .process-strip {
        display: grid; grid-template-columns: repeat(4, 1fr);
        max-width: 780px; margin-top: 2.5rem;
        border: 1px solid var(--border);
    }
    .process-step {
        padding: .85rem 1rem;
        border-right: 1px solid var(--border);
        position: relative;
        overflow: hidden;
    }
    .process-step:last-child { border-right: none; }
    .process-step::before {
        content: '';
        position: absolute; top: 0; left: 0; right: 0;
        height: 2px;
        background: linear-gradient(90deg, var(--cyan), transparent);
        opacity: 0;
        transition: opacity .3s;
    }
    .process-step:hover::before { opacity: 1; }
    .process-step b {
        display: block;
        font-family: var(--mono);
        font-size: .56rem;
        font-weight: 600;
        letter-spacing: .12em;
        text-transform: uppercase;
        color: var(--cyan);
    }
    .process-step span {
        display: block;
        margin-top: .35rem;
        font-size: .7rem;
        line-height: 1.45;
        color: var(--text-dim);
    }
    /* ── Brief shell (form card) ── */
    .brief-shell {
        position: relative;
        margin-top: .35rem;
        padding: clamp(1.2rem, 2.5vw, 2.2rem);
        background: var(--surface);
        border: 1px solid var(--border);
        animation: rise .65s .1s ease both;
        overflow: hidden;
    }
    .brief-shell::before {
        content: '';
        position: absolute; top: 0; left: 0; right: 0;
        height: 2px;
        background: linear-gradient(90deg, var(--cyan), var(--green), transparent);
    }
    .brief-shell::after {
        content: '';
        position: absolute; top: 0; right: 0;
        width: 200px; height: 200px;
        background: radial-gradient(circle at top right, rgba(0,212,255,0.06), transparent 70%);
        pointer-events: none;
    }
    .brief-shell > * { position: relative; z-index: 1; }
    .brief-heading {
        display: flex; align-items: center; justify-content: space-between;
        gap: 1rem; margin: 0 0 1.5rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid var(--border);
    }
    .brief-heading h2 {
        margin: 0;
        font-family: var(--sans);
        font-size: 1.05rem;
        font-weight: 600;
        color: var(--text-hi);
        letter-spacing: -.02em;
    }
    .brief-tag {
        font-family: var(--mono);
        font-size: .58rem;
        letter-spacing: .12em;
        text-transform: uppercase;
        color: var(--cyan);
        border: 1px solid rgba(0,212,255,.25);
        padding: .25rem .55rem;
    }
    /* ── Inputs ── */
    div[data-testid="stTextArea"] label, div[data-testid="stFileUploader"] label {
        color: var(--cyan-dim) !important;
        font-family: var(--mono) !important;
        font-size: .6rem !important;
        font-weight: 500 !important;
        letter-spacing: .14em !important;
        text-transform: uppercase !important;
    }
    .stTextArea textarea {
        min-height: 148px !important;
        padding: 1rem !important;
        background: var(--bg-2) !important;
        border: 1px solid var(--border) !important;
        border-radius: 0 !important;
        color: var(--text-hi) !important;
        font-family: var(--mono) !important;
        font-size: .82rem !important;
        line-height: 1.8 !important;
        transition: border-color .2s, box-shadow .2s !important;
        caret-color: var(--cyan) !important;
    }
    .stTextArea textarea::placeholder { color: var(--text-dim) !important; }
    .stTextArea textarea:focus {
        border-color: var(--cyan) !important;
        box-shadow: 0 0 0 2px rgba(0,212,255,.1), inset 0 0 30px rgba(0,212,255,.02) !important;
    }
    [data-testid="stFileUploader"] {
        background: var(--bg-2) !important;
        border: 1px dashed var(--border) !important;
        border-radius: 0 !important;
    }
    [data-testid="stFileUploader"]:hover { border-color: rgba(0,212,255,.35) !important; }
    [data-testid="stFileUploader"] * { color: var(--text-dim) !important; font-family: var(--mono) !important; font-size: .7rem !important; }
    [data-testid="stFileUploader"] button {
        background: var(--bg-3) !important;
        border: 1px solid var(--border) !important;
        border-radius: 0 !important;
        color: var(--cyan) !important;
        font-family: var(--mono) !important;
        font-size: .65rem !important;
        letter-spacing: .08em !important;
    }
    .form-note {
        font-family: var(--mono);
        font-size: .65rem;
        line-height: 1.7;
        color: var(--text-dim);
        border-left: 2px solid rgba(0,212,255,.2);
        padding-left: .75rem;
    }
    .form-note .note-key { color: var(--green); }
    /* ── Buttons ── */
    .stButton > button {
        min-height: 48px !important;
        width: 100% !important;
        border-radius: 0 !important;
        font-family: var(--mono) !important;
        font-size: .65rem !important;
        font-weight: 700 !important;
        letter-spacing: .18em !important;
        text-transform: uppercase !important;
        transition: all .18s ease !important;
        position: relative !important;
    }
    .stButton > button[kind="primary"] {
        background: transparent !important;
        border: 1px solid var(--cyan) !important;
        color: var(--cyan) !important;
        box-shadow: 0 0 20px rgba(0,212,255,.1), inset 0 0 20px rgba(0,212,255,.03) !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: rgba(0,212,255,.1) !important;
        box-shadow: 0 0 35px rgba(0,212,255,.2), inset 0 0 30px rgba(0,212,255,.06) !important;
        transform: translateY(-1px) !important;
    }
    .stButton > button[kind="secondary"], .stButton > button:not([kind="primary"]) {
        background: transparent !important;
        border: 1px solid var(--border) !important;
        color: var(--text-dim) !important;
    }
    .stButton > button:not([kind="primary"]):hover {
        border-color: var(--border-hi) !important;
        color: var(--cyan) !important;
    }
    /* ── Alerts / Spinner ── */
    [data-testid="stAlert"] { border-radius: 0 !important; font-family: var(--mono) !important; }
    [data-testid="stAlert"] p { font-size: .75rem !important; line-height: 1.65 !important; }
    [data-testid="stAlert"]:has([data-testid="stNotificationContentWarning"]) {
        background: rgba(245,166,35,.06) !important;
        border: 1px solid rgba(245,166,35,.3) !important;
        color: var(--amber) !important;
    }
    [data-testid="stAlert"]:has([data-testid="stNotificationContentError"]) {
        background: rgba(255,71,87,.06) !important;
        border: 1px solid rgba(255,71,87,.3) !important;
        color: var(--red) !important;
    }
    [data-testid="stSpinner"] p {
        color: var(--cyan-dim) !important;
        font-family: var(--mono) !important;
        font-size: .67rem !important;
        letter-spacing: .08em !important;
    }
    /* ── Results section ── */
    .section-divider {
        display: flex; align-items: center; gap: 1.2rem;
        margin: 5rem 0 2rem;
        font-family: var(--mono);
        font-size: .6rem;
        letter-spacing: .14em;
        text-transform: uppercase;
        color: var(--cyan-dim);
    }
    .section-divider::before { content: ''; flex: 0 0 12px; height: 12px; border: 1px solid var(--cyan); transform: rotate(45deg); background: rgba(0,212,255,.1); }
    .section-divider::after  { content: ''; flex: 1; height: 1px; background: linear-gradient(90deg, var(--border-hi), transparent); }
    .directive-header { margin-bottom: 1.5rem; }
    .directive-kicker {
        font-family: var(--mono);
        font-size: .6rem;
        letter-spacing: .16em;
        text-transform: uppercase;
        color: var(--green);
        display: flex; align-items: center; gap: .65rem;
    }
    .directive-kicker::before {
        content: 'OUTPUT';
        padding: .2rem .45rem;
        border: 1px solid rgba(0,229,160,.35);
        font-size: .52rem;
    }
    .directive-title {
        margin: .6rem 0 0;
        font-family: var(--sans);
        font-size: clamp(1.7rem, 3.5vw, 2.6rem);
        font-weight: 700;
        letter-spacing: -.04em;
        color: var(--text-hi);
        line-height: 1.1;
    }
    /* Charter */
    .charter-card {
        margin: 1.2rem 0 1.8rem;
        padding: 1rem 1.25rem;
        background: var(--bg-2);
        border: 1px solid var(--border);
        border-left: 3px solid var(--cyan);
        position: relative;
    }
    .charter-card::before {
        content: 'DECISION_CHARTER';
        position: absolute; top: .7rem; right: .9rem;
        font-family: var(--mono); font-size: .5rem;
        letter-spacing: .1em;
        color: var(--text-dim);
    }
    .charter-card h3 {
        margin: 0 0 .5rem;
        font-family: var(--mono);
        font-size: .58rem;
        font-weight: 600;
        letter-spacing: .14em;
        text-transform: uppercase;
        color: var(--cyan);
    }
    .charter-card p {
        margin: 0;
        color: var(--text-dim);
        font-size: .82rem;
        line-height: 1.75;
        font-family: var(--sans);
    }
    /* Directive grid */
    .directive-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 1px;
        background: var(--border);
        border: 1px solid var(--border);
    }
    .directive-section {
        min-height: 150px;
        padding: 1.35rem;
        background: var(--bg-2);
        position: relative;
    }
    .directive-section:first-child {
        grid-column: 1 / -1;
        min-height: auto;
        background: linear-gradient(135deg, var(--bg-3), var(--bg-2));
        border-top: 2px solid var(--cyan);
    }
    .directive-section h3 {
        margin: 0 0 .6rem;
        font-family: var(--mono);
        font-size: .57rem;
        font-weight: 600;
        letter-spacing: .14em;
        text-transform: uppercase;
        color: var(--cyan);
    }
    .directive-section p {
        margin: 0;
        color: var(--text);
        font-size: .86rem;
        line-height: 1.8;
        font-family: var(--sans);
    }
    .directive-section .sec-num {
        position: absolute; top: 1rem; right: 1rem;
        font-family: var(--mono); font-size: .5rem;
        color: var(--text-dim);
    }
    /* Download / action row */
    .decision-actions { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-top: 1.2rem; }
    .decision-actions p { margin: 0; color: var(--text-dim); font-size: .72rem; line-height: 1.55; font-family: var(--mono); }
    [data-testid="stDownloadButton"] button {
        min-height: 38px !important;
        width: auto !important;
        padding: .5rem .9rem !important;
        background: transparent !important;
        border: 1px solid var(--border) !important;
        border-radius: 0 !important;
        color: var(--text-dim) !important;
        font-family: var(--mono) !important;
        font-size: .6rem !important;
        letter-spacing: .1em !important;
        box-shadow: none !important;
    }
    [data-testid="stDownloadButton"] button:hover {
        border-color: var(--cyan) !important;
        color: var(--cyan) !important;
    }
    /* ── Expander (audit) ── */
    [data-testid="stExpander"] {
        margin-top: 2rem !important;
        background: var(--bg-1) !important;
        border: 1px solid var(--border) !important;
        border-radius: 0 !important;
        overflow: hidden !important;
    }
    [data-testid="stExpander"] summary {
        padding: .9rem 1.1rem !important;
        color: var(--text-dim) !important;
        font-family: var(--mono) !important;
        font-size: .62rem !important;
        font-weight: 600 !important;
        letter-spacing: .14em !important;
        text-transform: uppercase !important;
    }
    [data-testid="stExpander"] summary:hover { color: var(--cyan) !important; }
    [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
        padding: .45rem 1rem 1.2rem !important;
        border-top: 1px solid var(--border) !important;
    }
    .audit-note {
        max-width: 700px;
        margin: .7rem 0 1.4rem;
        color: var(--text-dim);
        font-size: .75rem;
        line-height: 1.7;
        font-family: var(--mono);
    }
    /* ── Member cards ── */
    [data-testid="column"] { padding: 0 .35rem !important; }
    .member-card {
        height: 100%;
        margin: .35rem 0;
        padding: 1.15rem;
        background: var(--bg-2);
        border: 1px solid var(--border);
        animation: rise .45s ease both;
        transition: border-color .2s ease, box-shadow .2s ease;
        position: relative;
        overflow: hidden;
    }
    .member-card::before {
        content: '';
        position: absolute; top: 0; left: 0; right: 0;
        height: 1px;
        background: linear-gradient(90deg, var(--cyan), transparent);
        opacity: 0;
        transition: opacity .25s;
    }
    .member-card:hover { border-color: rgba(0,212,255,.25); box-shadow: 0 0 20px rgba(0,212,255,.06); }
    .member-card:hover::before { opacity: 1; }
    .member-head {
        display: flex; justify-content: space-between; align-items: flex-start;
        gap: .8rem; margin-bottom: 1rem;
        padding-bottom: .85rem;
        border-bottom: 1px solid var(--border);
    }
    .member-id {
        font-family: var(--mono);
        font-size: .52rem;
        letter-spacing: .1em;
        color: var(--cyan);
        margin-bottom: .3rem;
    }
    .member-head h3 { margin: 0 0 .25rem; color: var(--text-hi); font-size: .88rem; font-weight: 600; font-family: var(--sans); }
    .member-model { margin: 0; color: var(--text-dim); font-family: var(--mono); font-size: .57rem; letter-spacing: .04em; }
    .member-status {
        display: flex; align-items: center; gap: .4rem;
        font-family: var(--mono); font-size: .5rem;
        letter-spacing: .1em;
        color: var(--green-dim);
        white-space: nowrap;
    }
    .status-pip { width: 5px; height: 5px; border-radius: 50%; }
    .status-pip.active { background: var(--green); box-shadow: 0 0 5px var(--green); }
    .phase-label {
        display: inline-block;
        margin-bottom: .55rem;
        padding: .2rem .4rem;
        background: rgba(0,212,255,.06);
        color: var(--cyan-dim);
        font-family: var(--mono);
        font-size: .52rem;
        letter-spacing: .08em;
        text-transform: uppercase;
        border: 1px solid rgba(0,212,255,.15);
    }
    .phase-two {
        background: rgba(0,229,160,.05);
        color: var(--green-dim);
        border-color: rgba(0,229,160,.15);
    }
    .analysis-copy, .analysis-error { color: var(--text-dim); font-size: .78rem; line-height: 1.75; overflow-wrap: anywhere; font-family: var(--sans); }
    .analysis-error { color: rgba(255,71,87,.7); }
    .phase-rule { height: 1px; margin: .95rem 0 .85rem; background: var(--border); }
    .empty-audit {
        padding: 1.2rem;
        color: var(--text-dim);
        border: 1px dashed var(--border);
        font-size: .75rem;
        font-family: var(--mono);
        letter-spacing: .06em;
    }
    /* ── Animations ── */
    @keyframes rise    { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
    @keyframes pulse   { 0%, 100% { opacity: 1; } 50% { opacity: .4; } }
    /* ── Responsive ── */
    @media (max-width: 640px) {
        .block-container { padding: 0 1rem 3.5rem !important; }
        .site-nav { min-height: 52px; }
        .hero { padding: 3.2rem 0 2.2rem; }
        .process-strip { grid-template-columns: repeat(2, 1fr); }
        .process-step:nth-child(3) { border-top: 1px solid var(--border); }
        .process-step:nth-child(4) { border-top: 1px solid var(--border); }
        .brief-shell { padding: 1.1rem; }
        .brief-heading { flex-direction: column; align-items: flex-start; gap: .5rem; }
        .directive-grid { grid-template-columns: 1fr; }
        .directive-section:first-child { grid-column: auto; }
        .decision-actions { flex-direction: column; align-items: flex-start; }
        .nav-right { gap: .8rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)
with st.sidebar:
    st.markdown("### // CONFIG")
    backend_url = st.text_input(
        "Backend endpoint",
        value=st.session_state.get("backend_url", "http://localhost:8000"),
        help="Base URL for the FastAPI service. Requests are sent to /ask.",
    ).rstrip("/")
    st.session_state.backend_url = backend_url
    st.caption("→ Use deployed endpoint URL in production.")
    st.divider()
    if st.button("RESET SESSION", use_container_width=True):
        reset_council()
        st.rerun()
st.markdown(
    """
    <nav class="site-nav">
        <div class="brand">
            <div class="brand-hex">⬡</div>
            <div>
                <div class="brand-name">AI Council</div>
                <div class="brand-version">SYS v2.1 &nbsp;·&nbsp; MULTI-AGENT DECISION FRAMEWORK</div>
            </div>
        </div>
        <div class="nav-right">
            <div class="nav-stat"><span class="pip online"></span>NODES ONLINE</div>
            <div class="nav-stat"><span class="pip ready"></span>READY</div>
        </div>
    </nav>
    <section class="hero">
        <div class="sys-id">SYS:AIC-001 &nbsp;&middot;&nbsp; MULTI-AGENT CONSENSUS ENGINE</div>
        <h1>Structured<br><span class="accent">intelligence</span><br>for hard decisions.</h1>
        <p class="hero-sub">Submit a decision problem. The council frames it, stress-tests the assumptions in parallel, and returns a single structured directive — with guardrails baked in.</p>
        <div class="process-strip">
            <div class="process-step"><b>01 / FRAME</b><span>Clarify the decision and its criteria.</span></div>
            <div class="process-step"><b>02 / ANALYZE</b><span>Specialist nodes assess independently.</span></div>
            <div class="process-step"><b>03 / CHALLENGE</b><span>Claims and biases are pressure-tested.</span></div>
            <div class="process-step"><b>04 / DIRECT</b><span>One actionable output with guardrails.</span></div>
        </div>
    </section>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    '<section class="brief-shell"><div class="brief-heading"><h2>Input Brief</h2><span class="brief-tag">01 / SUBMIT</span></div>',
    unsafe_allow_html=True,
)
prompt = st.text_area(
    "// DECISION QUERY",
    value=st.session_state.get("council_prompt", ""),
    height=158,
    placeholder="Describe the decision, scenario, or strategic question for the council to examine...",
)
upload_column, details_column = st.columns([1.1, 1], gap="large")
with upload_column:
    uploaded_files = st.file_uploader(
        "// ATTACH SUPPORTING MATERIAL  [ MAX 5 FILES ]",
        type=["pdf", "png", "jpg", "jpeg", "webp"],
        help="Add up to five PDFs or images. They will be considered by all council nodes.",
        accept_multiple_files=True,
    )
with details_column:
    st.markdown(
        """
        <div class="form-note">
            <span class="note-key">PROCESS</span> → Frame → Analyze → Challenge → Direct<br>
            The council identifies decision criteria, stress-tests assumptions, and provides a final directive with explicit guardrails and reversal conditions.
        </div>
        """,
        unsafe_allow_html=True,
    )
st.markdown("</section>", unsafe_allow_html=True)
ask_clicked = st.button("INITIATE DELIBERATION", type="primary", use_container_width=True)
if ask_clicked:
    if not prompt.strip():
        st.warning("WARN: Decision query is empty. Add a brief before initiating deliberation.")
    elif not backend_url:
        st.warning("WARN: Backend endpoint not configured. Set it in the sidebar config panel.")
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
            with st.spinner("// Council nodes are processing the brief. Estimated time: 60–120s..."):
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
                f"ERR: Connection refused at {backend_url}. Verify the backend service is running and the endpoint is correct."
            )
        except requests.exceptions.Timeout:
            st.session_state.council_error = "ERR: Request timed out. The council did not respond within 240s. Check backend logs."
        except requests.exceptions.HTTPError as error:
            try:
                detail = error.response.json().get("detail", error.response.text)
            except (ValueError, AttributeError):
                detail = getattr(error.response, "text", str(error))
            st.session_state.council_error = f"ERR [{error.response.status_code}]: {detail}"
        except (ValueError, requests.exceptions.RequestException) as error:
            st.session_state.council_error = f"ERR: {error}"
if st.session_state.get("council_error"):
    st.error(st.session_state.council_error)
result = st.session_state.get("council_result")
if result:
    st.markdown('<div class="section-divider">DECISION REPORT &nbsp;/&nbsp; COUNCIL OUTPUT</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="directive-header">
            <div class="directive-kicker">Consensus Directive</div>
            <h2 class="directive-title">Final Decision Output</h2>
        </div>
        """,
        unsafe_allow_html=True,
    )
    decision_charter = result.get("decision_charter")
    if decision_charter:
        st.markdown(
            f'<div class="charter-card"><h3>// decision_charter.json</h3><p>{escape_text(decision_charter)}</p></div>',
            unsafe_allow_html=True,
        )
    directive_sections = parse_directive(result.get("final_answer"))
    directive_html = "".join(
        f'<div class="directive-section"><span class="sec-num">[{i+1:02d}]</span><h3>{escape_text(heading)}</h3><p>{escape_text(content)}</p></div>'
        for i, (heading, content) in enumerate(directive_sections)
    )
    st.markdown(f'<div class="directive-grid">{directive_html}</div>', unsafe_allow_html=True)
    action_copy, action_export = st.columns([1.4, 0.6])
    with action_copy:
        st.markdown('<div class="decision-actions"><p>// Record includes original query, decision charter, and final directive.</p></div>', unsafe_allow_html=True)
    with action_export:
        st.download_button(
            "EXPORT BRIEF",
            data=decision_brief_text(result),
            file_name="ai-council-decision-brief.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with st.expander("// VIEW COUNCIL RECORD  [ DELIBERATION AUDIT ]", expanded=False):
        st.markdown(
            '<p class="audit-note">// Each node produces an independent analysis (Phase I), then may revise its position after reviewing peer responses (Phase II). Full record is preserved below.</p>',
            unsafe_allow_html=True,
        )
        round_one = result.get("round1") or []
        round_two = result.get("round2") or []
        round_two_by_key = {
            entry.get("key"): entry for entry in round_two if isinstance(entry, dict) and entry.get("key")
        }
        members = [member for member in round_one if isinstance(member, dict)]
        if not members:
            st.markdown('<div class="empty-audit">// NO_DATA: Individual deliberation record was not returned for this request.</div>', unsafe_allow_html=True)
        else:
            for row_start in range(0, len(members), 3):
                row = members[row_start : row_start + 3]
                columns = st.columns(3, gap="medium")
                for offset, member in enumerate(row):
                    with columns[offset]:
                        render_member_card(
                            member,
                            round_two_by_key.get(member.get("key")),
                            row_start + offset,
                        )
