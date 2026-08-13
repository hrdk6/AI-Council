"""AI Council Streamlit Frontend."""

import html
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st
from streamlit.components.v1 import html as st_html

from frontend.api import CouncilApiClient, ApiError, CouncilResponse
from frontend.constants import (
    SESSION_BACKEND_URL,
    SESSION_COUNCIL_RESULT,
    SESSION_COUNCIL_ERROR,
    SESSION_COUNCIL_PROMPT,
    DEFAULT_BACKEND_URL,
    MAX_ANIMATION_DELAY,
    ANIMATION_DELAY_STEP,
    MEMBER_CARDS_PER_ROW,
    EXPORT_FILENAME,
    EXPORT_MIME_TYPE,
    FALLBACK_ROLE_NAME,
    FALLBACK_PROVIDER,
    FALLBACK_MODEL,
    FALLBACK_CONTENT,
    FALLBACK_REVISED_CONTENT,
    FALLBACK_ERROR,
    FALLBACK_REVISED_ERROR,
    FALLBACK_AUDIT,
)
from frontend.parsing import parse_directive, decision_brief_text
from frontend.utils import (
    escape_text,
    sanitize_directive_content,
    safe_member_value,
)

st.set_page_config(
    page_title="AI Council",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def render_member_card(member: dict[str, Any], revised: dict[str, Any] | None, index: int) -> None:
    """Render a single council member's analysis card."""
    role_name = safe_member_value(member, "role_name", FALLBACK_ROLE_NAME)
    provider = safe_member_value(member, "provider", FALLBACK_PROVIDER)
    model = safe_member_value(member, "model", FALLBACK_MODEL)

    if member.get("success"):
        content_html = safe_member_value(member, "content", FALLBACK_CONTENT)
        rec = member.get("recommendation")
        risk = member.get("key_risk")
        conf = member.get("confidence")

        extras = ""
        if rec or risk:
            conf_str = f" (Confidence: {conf:.2f})" if conf is not None else ""
            extras = f'<div class="analysis-meta"><strong>Recommendation:</strong> {escape_text(rec)}{conf_str}<br><strong>Key Risk:</strong> {escape_text(risk)}</div>'

        first_take = f'<div class="analysis-copy">{extras}{content_html}</div>'
    else:
        first_take = f'<div class="analysis-error">{safe_member_value(member, "error", FALLBACK_ERROR)}</div>'

    revised_take = ""
    if revised:
        if revised.get("success"):
            revised_content_html = safe_member_value(revised, "content", FALLBACK_REVISED_CONTENT)
            r_rec = revised.get("recommendation")
            r_risk = revised.get("key_risk")
            r_conf = revised.get("confidence")

            r_extras = ""
            if r_rec or r_risk:
                r_conf_str = f" (Confidence: {r_conf:.2f})" if r_conf is not None else ""
                r_extras = f'<div class="analysis-meta"><strong>Recommendation:</strong> {escape_text(r_rec)}{r_conf_str}<br><strong>Key Risk:</strong> {escape_text(r_risk)}</div>'

            revised_content = f'<div class="analysis-copy">{r_extras}{revised_content_html}</div>'
        else:
            revised_content = f'<div class="analysis-error">{safe_member_value(revised, "error", FALLBACK_REVISED_ERROR)}</div>'

        revised_take = f"""
<div class="phase-divider"></div>
<div class="phase-badge phase-two">Phase II &nbsp;·&nbsp; Final Position</div>
{revised_content}
"""

    delay = min(index * ANIMATION_DELAY_STEP, MAX_ANIMATION_DELAY)
    st.markdown(
        f"""
<article class="member-card" style="animation-delay: {delay:.2f}s;">
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


def render_skeleton_cards(count: int = 3) -> None:
    """Render skeleton placeholder cards while loading."""
    skeleton_html = "".join(
        f"""
<article class="member-card skeleton" style="animation-delay: {min(i * ANIMATION_DELAY_STEP, MAX_ANIMATION_DELAY):.2f}s;">
    <div class="member-head">
        <div class="member-avatar skeleton-avatar"></div>
        <div class="member-meta">
            <div class="skeleton-line skeleton-name"></div>
            <div class="skeleton-line skeleton-model"></div>
        </div>
    </div>
    <div class="skeleton-line skeleton-badge"></div>
    <div class="skeleton-line"></div>
    <div class="skeleton-line"></div>
    <div class="skeleton-line"></div>
</article>
        """
        for i in range(count)
    )
    st.markdown(f'<div class="member-grid">{skeleton_html}</div>', unsafe_allow_html=True)


def render_directive_grid(directive_sections: list[tuple[str, str]]) -> None:
    """Render the directive as a grid of sections."""
    directive_html = "".join(
        f"""
        <div class="directive-section">
            <span class="sec-num">{i + 1:02d}</span>
            <div class="sec-label">{escape_text(heading)}</div>
            <p>{sanitize_directive_content(content)}</p>
        </div>
        """
        for i, (heading, content) in enumerate(directive_sections)
    )
    st.markdown(f'<div class="directive-grid">{directive_html}</div>', unsafe_allow_html=True)


def render_copy_button(text: str, label: str = "Copy") -> None:
    """Render a self-contained copy-to-clipboard button.

    Rendered via an iframe component (Streamlit strips <script> in markdown).
    Uses execCommand('copy') as a same-document fallback so it works even in
    isolated/srcdoc iframe contexts where the Clipboard API is unavailable.
    """
    escaped = html.escape(text, quote=True)
    component_html = f"""
<div style="padding:0;margin:0;">
  <style>
    .copy-wrap {{ display:inline-block; }}
    .copy-btn {{
      display:inline-flex; align-items:center; justify-content:center; gap:0.4rem;
      min-height:38px; padding:0.45rem 1rem;
      background:rgba(255,255,255,0.04); color:#a1a1aa;
      border:1px solid rgba(255,255,255,0.08); border-radius:6px;
      font-family:'Inter',sans-serif; font-size:0.75rem; font-weight:500;
      cursor:pointer; transition:all 0.15s;
    }}
    .copy-btn:hover {{ border-color:rgba(255,255,255,0.14); color:#fafafa; background:rgba(255,255,255,0.06); }}
    .copy-btn.copied {{ color:#4ade80; border-color:rgba(34,197,94,0.35); }}
  </style>
  <textarea id="copy-source" style="position:absolute;left:-9999px;top:0;" readonly>{escaped}</textarea>
  <button class="copy-btn" id="copy-trigger">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
    </svg>
    {html.escape(label)}
  </button>
  <script>
  (function() {{
    var btn = document.getElementById('copy-trigger');
    var src = document.getElementById('copy-source');
    btn.addEventListener('click', function() {{
      var done = function() {{
        btn.classList.add('copied');
        btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg> Copied';
        setTimeout(function() {{
          btn.classList.remove('copied');
          btn.innerHTML = '{html.escape(label)}';
        }}, 1600);
      }};
      try {{
        if (navigator.clipboard && window.isSecureContext) {{
          navigator.clipboard.writeText(src.value).then(done).catch(function() {{ legacyCopy(src, done); }});
        }} else {{
          legacyCopy(src, done);
        }}
      }} catch (e) {{
        legacyCopy(src, done);
      }}
    }});
    function legacyCopy(src, done) {{
      src.style.position = 'fixed';
      src.style.left = '0';
      src.style.top = '0';
      src.focus();
      src.select();
      src.setSelectionRange(0, src.value.length);
      try {{
        document.execCommand('copy');
      }} catch (e) {{}}
      done();
    }}
  }})();
  </script>
</div>
"""
    st_html(component_html, height=80, scrolling=False)


def reset_council() -> None:
    """Clear council-related session state."""
    for key in (SESSION_COUNCIL_RESULT, SESSION_COUNCIL_ERROR, SESSION_COUNCIL_PROMPT):
        st.session_state.pop(key, None)


def load_css() -> None:
    """Load CSS from external file."""
    styles_path = Path(__file__).parent / "static" / "styles.css"
    try:
        with styles_path.open("r", encoding="utf-8") as f:
            css = f.read()
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except (FileNotFoundError, OSError):
        # Fallback: inline critical CSS if file not found
        st.markdown(
            """
<style>
:root { --bg:#0a0a0b; --bg-raised:#111113; --border:rgba(255,255,255,0.08); --accent:#7c3aed; --text:#a1a1aa; --text-hi:#fafafa; }
body, [data-testid="stAppViewContainer"] { background:var(--bg)!important; color:var(--text)!important; font-family:'Inter',sans-serif!important; }
.block-container { max-width:1200px!important; padding:0 2rem 8rem!important; }
</style>
            """,
            unsafe_allow_html=True,
        )


# ── Page Setup ──
load_css()

# ── Sidebar ──
with st.sidebar:
    st.markdown("### // Config")
    backend_url = st.text_input(
        "Backend endpoint",
        value=st.session_state.get(SESSION_BACKEND_URL, DEFAULT_BACKEND_URL),
        help="Base URL for the FastAPI service. Requests are sent to /ask.",
    ).rstrip("/")
    st.session_state[SESSION_BACKEND_URL] = backend_url
    st.caption("→ Use deployed endpoint URL in production.")
    st.divider()
    if st.button("Reset session", use_container_width=True):
        reset_council()
        st.rerun()

# ── Top Navigation ──
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

# ── Hero ──
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

# ── Input Card ──
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
    value=st.session_state.get(SESSION_COUNCIL_PROMPT, ""),
    height=148,
    placeholder="Describe the decision, scenario, or strategic question for the council to examine...",
)

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

ask_clicked = st.button("Initiate deliberation", type="primary", use_container_width=True)

# ── Deliberation Logic ──
if ask_clicked:
    if not prompt.strip():
        st.warning("Decision query is empty. Add a brief before initiating deliberation.")
    elif not backend_url:
        st.warning("Backend endpoint not configured. Set it in the sidebar.")
    else:
        st.session_state[SESSION_COUNCIL_ERROR] = None
        st.session_state[SESSION_COUNCIL_RESULT] = None
        st.session_state[SESSION_COUNCIL_PROMPT] = prompt

        try:
            with st.status("Council nodes are processing your brief...", expanded=True) as status:
                st.write("Initializing deliberation...")
                with CouncilApiClient(backend_url) as client:
                    response: CouncilResponse = client.ask(prompt, debate=True)
                status.update(label="Deliberation complete!", state="complete")

            if not response.final_answer:
                raise ValueError("The backend returned an incomplete council response.")

            # Convert to dict for session storage
            st.session_state[SESSION_COUNCIL_RESULT] = {
                "question": response.question,
                "decision_charter": response.decision_charter,
                "final_answer": response.final_answer,
                "round1": [m.model_dump() for m in response.round_one],
                "round2": [m.model_dump() for m in response.round_two],
            }

        except ApiError as e:
            st.session_state[SESSION_COUNCIL_ERROR] = str(e)
        except ValueError as e:
            st.session_state[SESSION_COUNCIL_ERROR] = f"Invalid response: {e}"
        except Exception as e:
            st.session_state[SESSION_COUNCIL_ERROR] = f"Unexpected error: {e}"

if st.session_state.get(SESSION_COUNCIL_ERROR):
    st.error(st.session_state[SESSION_COUNCIL_ERROR])

# ── Results ──
result = st.session_state.get(SESSION_COUNCIL_RESULT)

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
    render_directive_grid(directive_sections)

    # Export row
    brief_text = decision_brief_text(result, st.session_state.get(SESSION_COUNCIL_PROMPT))
    export_note, export_copy, export_download = st.columns([1.2, 0.35, 0.45])
    with export_note:
        st.markdown(
            '<p class="export-note">Record includes the original query, decision charter, and full directive.</p>',
            unsafe_allow_html=True,
        )
    with export_copy:
        render_copy_button(brief_text, label="Copy brief")
    with export_download:
        st.download_button(
            "Export brief",
            data=brief_text,
            file_name=EXPORT_FILENAME,
            mime=EXPORT_MIME_TYPE,
            use_container_width=True,
        )

    # ── Audit Log ──
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
                f'<div class="empty-audit">{escape_text(FALLBACK_AUDIT)}</div>',
                unsafe_allow_html=True,
            )
        else:
            for row_start in range(0, len(members), MEMBER_CARDS_PER_ROW):
                row = members[row_start: row_start + MEMBER_CARDS_PER_ROW]
                columns = st.columns(len(row), gap="medium")
                for offset, member in enumerate(row):
                    with columns[offset]:
                        render_member_card(
                            member,
                            round_two_by_key.get(member.get("key")),
                            row_start + offset,
                        )