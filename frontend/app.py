"""AI Council Streamlit Frontend."""

import json
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from frontend.api import ApiError, CouncilApiClient, CouncilResponse
from frontend.constants import (
    DEFAULT_BACKEND_URL,
    EXPORT_FILENAME,
    EXPORT_MIME_TYPE,
    FALLBACK_AUDIT,
    FALLBACK_CONTENT,
    FALLBACK_ERROR,
    FALLBACK_MODEL,
    FALLBACK_PROVIDER,
    FALLBACK_REVISED_CONTENT,
    FALLBACK_REVISED_ERROR,
    FALLBACK_ROLE_NAME,
    MEMBER_CARDS_PER_ROW,
    SESSION_BACKEND_URL,
    SESSION_COUNCIL_ERROR,
    SESSION_COUNCIL_PROMPT,
    SESSION_COUNCIL_RESULT,
    validate_backend_url,
)
from frontend.parsing import decision_brief_text, parse_directive
from frontend.utils import (
    escape_text,
    safe_member_value,
    sanitize_directive_content,
)

st.set_page_config(
    page_title="AI Council",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- Draft & Undo/Redo State ---
DRAFT_FILE = Path(__file__).parent / ".draft.json"

def load_draft() -> str:
    if DRAFT_FILE.exists():
        try:
            return json.loads(DRAFT_FILE.read_text()).get("prompt", "")
        except:
            pass
    return ""

def save_draft(prompt_text: str) -> None:
    try:
        DRAFT_FILE.write_text(json.dumps({"prompt": prompt_text}))
    except:
        pass

if "prompt_input" not in st.session_state:
    saved_val = st.session_state.get(SESSION_COUNCIL_PROMPT, "")
    draft_val = load_draft()
    if draft_val and not saved_val:
        st.session_state["prompt_input"] = draft_val
    else:
        st.session_state["prompt_input"] = saved_val

if "prompt_history" not in st.session_state:
    st.session_state.prompt_history = [st.session_state["prompt_input"]]
if "history_idx" not in st.session_state:
    st.session_state.history_idx = 0

def on_prompt_change():
    new_prompt = st.session_state.prompt_input
    current = st.session_state.prompt_history[st.session_state.history_idx]
    if new_prompt != current:
        st.session_state.prompt_history = st.session_state.prompt_history[:st.session_state.history_idx + 1]
        st.session_state.prompt_history.append(new_prompt)
        st.session_state.history_idx += 1
        save_draft(new_prompt)

def undo():
    if st.session_state.history_idx > 0:
        st.session_state.history_idx -= 1
        st.session_state.prompt_input = st.session_state.prompt_history[st.session_state.history_idx]
        save_draft(st.session_state.prompt_input)

def redo():
    if st.session_state.history_idx < len(st.session_state.prompt_history) - 1:
        st.session_state.history_idx += 1
        st.session_state.prompt_input = st.session_state.prompt_history[st.session_state.history_idx]
        save_draft(st.session_state.prompt_input)
# -------------------------------


def render_member_card(member: dict[str, Any], revised: dict[str, Any] | None, index: int) -> None:
    """Render a single council member's analysis card using native Streamlit components."""
    role_name = safe_member_value(member, "role_name", FALLBACK_ROLE_NAME)
    provider = safe_member_value(member, "provider", FALLBACK_PROVIDER)
    model = safe_member_value(member, "model", FALLBACK_MODEL)

    with st.container(border=True):
        col_avatar, col_meta, col_status = st.columns([0.1, 0.7, 0.2])
        with col_avatar:
            st.markdown(f"**{index + 1:02d}**")
        with col_meta:
            st.subheader(role_name)
            
            switched = member.get("switched_from_model")
            if switched:
                st.caption(f"{provider} / {model} (auto-switched from {switched})")
            else:
                st.caption(f"{provider} / {model}")
        with col_status:
            if member.get("success"):
                st.success("Active")
            else:
                st.error("Failed")

        st.markdown("**Phase I: Independent Analysis**")

        if member.get("success"):
            content = safe_member_value(member, "content", FALLBACK_CONTENT)
            st.markdown(sanitize_directive_content(content))

            rec = member.get("recommendation")
            risk = member.get("key_risk")
            conf = member.get("confidence")

            if rec or risk:
                with st.expander("Details", expanded=False):
                    if rec:
                        conf_str = f" (Confidence: {conf:.2f})" if conf is not None else ""
                        st.markdown(f"**Recommendation:** {escape_text(rec)}{conf_str}")
                    if risk:
                        st.markdown(f"**Key Risk:** {escape_text(risk)}")
        else:
            error_msg = safe_member_value(member, "error", FALLBACK_ERROR)
            st.error(error_msg)

        if revised:
            st.divider()
            st.markdown("**Phase II: Final Position**")

            if revised.get("success"):
                revised_content = safe_member_value(revised, "content", FALLBACK_REVISED_CONTENT)
                st.markdown(sanitize_directive_content(revised_content))

                r_rec = revised.get("recommendation")
                r_risk = revised.get("key_risk")
                r_conf = revised.get("confidence")

                if r_rec or r_risk:
                    with st.expander("Details", expanded=False):
                        if r_rec:
                            r_conf_str = f" (Confidence: {r_conf:.2f})" if r_conf is not None else ""
                            st.markdown(f"**Recommendation:** {escape_text(r_rec)}{r_conf_str}")
                        if r_risk:
                            st.markdown(f"**Key Risk:** {escape_text(r_risk)}")
            else:
                revised_error = safe_member_value(revised, "error", FALLBACK_REVISED_ERROR)
                st.error(revised_error)


def render_skeleton_cards(count: int = 3) -> None:
    """Render skeleton placeholder cards while loading."""
    for i in range(count):
        with st.container(border=True):
            col_avatar, col_meta, col_status = st.columns([0.1, 0.7, 0.2])
            with col_avatar:
                st.markdown("**--**")
            with col_meta:
                st.markdown("`Loading...`")
                st.markdown("`Loading...`")
            with col_status:
                st.empty()
            st.markdown("**Phase I: Independent Analysis**")
            st.markdown("`Analyzing...`")


def render_directive_grid(directive_sections: list[tuple[str, str]]) -> None:
    """Render the directive as a grid of sections using native components."""
    for i, (heading, content) in enumerate(directive_sections):
        with st.container(border=True):
            st.markdown(f"**{i + 1:02d}. {heading}**")
            st.markdown(sanitize_directive_content(content))


def render_copy_button(text: str, label: str = "Copy") -> None:
    """Render a copy-to-clipboard button using JavaScript."""
    import streamlit.components.v1 as components
    
    # Create a unique key for this button
    button_key = f"copy_{hash(text) % 1000000}"
    
    # Use HTML + JavaScript for actual clipboard copy
    html_code = f"""
    <button id="{button_key}" onclick="copyToClipboard()" style="
        background-color: #7c3aed;
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 0.375rem;
        cursor: pointer;
        font-size: 0.875rem;
        font-weight: 500;
    ">{label}</button>
    <script>
        function copyToClipboard() {{
            const text = {json.dumps(text)};
            navigator.clipboard.writeText(text).then(function() {{
                const btn = document.getElementById("{button_key}");
                const originalText = btn.innerText;
                btn.innerText = "Copied!";
                btn.style.backgroundColor = "#22c55e";
                setTimeout(function() {{
                    btn.innerText = originalText;
                    btn.style.backgroundColor = "#7c3aed";
                }}, 2000);
            }}, function(err) {{
                console.error("Failed to copy: ", err);
                alert("Failed to copy to clipboard");
            }});
        }}
    </script>
    """
    components.html(html_code, height=50)


def parse_decision_matrix(raw_matrix: str) -> tuple[str, list[tuple[str, float]]]:
    """Turn simple weighted rows into context the council can use.

    Format: criterion | weight | option A score | option B score
    """
    rows: list[tuple[str, float]] = []
    lines = [line.strip() for line in raw_matrix.splitlines() if line.strip()]
    if not lines:
        return "", rows
    for line in lines:
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 4:
            raise ValueError("Each matrix row needs: criterion | weight | score A | score B")
        criterion, weight_text, score_a_text, score_b_text = parts[:4]
        weight, score_a, score_b = float(weight_text), float(score_a_text), float(score_b_text)
        if weight <= 0 or not all(0 <= score <= 10 for score in (score_a, score_b)):
            raise ValueError("Weights must be positive and scores must be between 0 and 10.")
        rows.append((criterion, weight * (score_a - score_b)))
    summary = "\n".join(f"- {name}: weighted difference {difference:+.2f} (A minus B)" for name, difference in rows)
    return "\nDECISION MATRIX (user-provided scores; verify assumptions):\n" + summary, rows


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
        pass

def inject_keyboard_shortcuts():
    import streamlit.components.v1 as components
    components.html("""
    <script>
        const doc = window.parent.document;
        if (!doc.getElementById('aicouncil-shortcuts')) {
            const script = doc.createElement('script');
            script.id = 'aicouncil-shortcuts';
            script.innerHTML = `
                document.addEventListener('keydown', function(e) {
                    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                        const buttons = document.querySelectorAll('button');
                        for (const btn of buttons) {
                            if (btn.innerText.includes('Initiate deliberation')) {
                                btn.click();
                                break;
                            }
                        }
                    }
                    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                        e.preventDefault();
                        const textareas = document.querySelectorAll('textarea');
                        if (textareas.length > 0) textareas[0].focus();
                    }
                    if (e.key === '?' && !['INPUT', 'TEXTAREA'].includes(e.target.tagName)) {
                        const buttons = document.querySelectorAll('button');
                        for (const btn of buttons) {
                            if (btn.innerText.includes('Help (?')) {
                                btn.click();
                                break;
                            }
                        }
                    }
                });
            `;
            doc.head.appendChild(script);
        }
    </script>
    """, height=0, width=0)

# ── Page Setup ──
load_css()
inject_keyboard_shortcuts()

# Initialize backend URL in session state if not present
if SESSION_BACKEND_URL not in st.session_state:
    st.session_state[SESSION_BACKEND_URL] = DEFAULT_BACKEND_URL

backend_url = st.session_state[SESSION_BACKEND_URL]

with st.sidebar:
    st.header("Settings")
    theme_mode = st.toggle("Light mode", key="theme_toggle")
    
    if theme_mode:
        st.markdown("""
        <style>
        :root {
            --bg:          #fafafa;
            --bg-raised:   #ffffff;
            --bg-subtle:   #f4f4f5;
            --bg-overlay:  rgba(0,0,0,0.04);
            --border:      rgba(0,0,0,0.08);
            --border-hi:   rgba(0,0,0,0.14);
            --border-focus:rgba(124,58,237,0.6);
            --accent:      #7c3aed;
            --accent-hi:   #6d28d9;
            --accent-soft: rgba(124,58,237,0.1);
            --accent-glow: rgba(124,58,237,0.15);
            --text-hi:     #18181b;
            --text:        #3f3f46;
            --text-dim:    #71717a;
            --text-accent: #6d28d9;
            --shadow-sm:   0 1px 3px rgba(0,0,0,0.1), 0 0 0 1px var(--border);
            --shadow-md:   0 4px 16px rgba(0,0,0,0.1), 0 0 0 1px var(--border);
            --shadow-lg:   0 12px 40px rgba(0,0,0,0.12), 0 0 0 1px var(--border);
        }
        [data-testid="stAppViewContainer"] { background-image: none !important; }
        .directive-section:first-child { background: linear-gradient(135deg, rgba(124,58,237,0.05) 0%, var(--bg-raised) 60%) !important; }
        </style>
        """, unsafe_allow_html=True)
    
    if st.button("Help (? Keyboard shortcuts)", key="help_button_sidebar"):
        @st.dialog("Keyboard Shortcuts")
        def help_dialog():
            st.markdown("""
            - **Ctrl+Enter**: Submit decision query
            - **Ctrl+K**: Focus quick search / input area
            - **?**: Show this help dialog
            """)
        help_dialog()
        
    st.divider()

    st.header("Council status")
    try:
        with CouncilApiClient(backend_url) as client:
            provider_data = client.providers()
        for provider in provider_data.get("providers", []):
            label = provider["name"]
            (st.success if provider["configured"] else st.warning)(
                f"{label}: {'ready' if provider['configured'] else 'API key missing'}"
            )
        with st.expander("Active model configuration"):
            for role in provider_data.get("roles", []):
                st.caption(f"{role['role']}: {role['provider']} / {role['model']}")
    except ApiError:
        st.caption("Backend status is unavailable.")

    st.divider()
    st.header("Recent decisions")
    try:
        with CouncilApiClient(backend_url) as client:
            recent_decisions = client.history()
        for decision in recent_decisions[:8]:
            with st.expander(decision["question"][:55] or "Untitled decision"):
                st.caption(decision["created_at"])
                if decision.get("rating"):
                    st.write(f"Outcome rating: {decision['rating']}/5")
                if st.button("Load", key=f"load_{decision['id']}"):
                    st.session_state[SESSION_COUNCIL_RESULT] = decision["result"]
                    st.session_state[SESSION_COUNCIL_PROMPT] = decision["question"]
                    st.session_state["prompt_input"] = decision["question"]
                    st.rerun()
    except ApiError:
        st.caption("Run a decision to start history.")

    st.divider()
    st.header("Service metrics")
    try:
        with CouncilApiClient(backend_url) as client:
            metric_data = client.metrics()
        request_metrics = metric_data.get("requests", {})
        st.metric("Requests", request_metrics.get("total", 0))
        st.caption(f"Cache hit rate: {request_metrics.get('cache_hit_rate', 0):.0%}")
        st.caption(f"LLM failures: {metric_data.get('llm_calls', {}).get('failures', 0)}")
    except ApiError:
        st.caption("Metrics require an authorized backend connection.")

# ── Top Navigation ──
st.markdown(
    """
    <div style="display: flex; justify-content: space-between; align-items: center; padding: 1rem 0; border-bottom: 1px solid rgba(255,255,255,0.1); margin-bottom: 2rem;">
        <div style="display: flex; align-items: center; gap: 0.75rem;">
            <div style="font-size: 2rem;">⬡</div>
            <div>
                <div style="font-size: 1.5rem; font-weight: 700;">AI Council</div>
                <div style="font-size: 0.85rem; color: #888;">Multi-agent decision framework · v2.1</div>
            </div>
        </div>
        <div style="display: flex; gap: 1rem;">
            <span style="display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.25rem 0.75rem; background: rgba(34,197,94,0.15); border: 1px solid rgba(34,197,94,0.3); border-radius: 999px; font-size: 0.75rem; color: #4ade80;">
                <span style="width: 6px; height: 6px; background: #22c55e; border-radius: 50%;"></span> Nodes online
            </span>
            <span style="display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.25rem 0.75rem; background: rgba(124,58,237,0.15); border: 1px solid rgba(124,58,237,0.3); border-radius: 999px; font-size: 0.75rem; color: #a78bfa;">
                <span style="width: 6px; height: 6px; background: #7c3aed; border-radius: 50%;"></span> Ready
            </span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Hero ──
st.markdown(
    """
    <div style="margin-bottom: 3rem;">
        <div style="display: inline-flex; align-items: center; gap: 0.5rem; font-size: 0.75rem; color: #7c3aed; margin-bottom: 1rem;">
            <span style="width: 8px; height: 8px; background: #7c3aed; border-radius: 50%; animation: pulse 2s infinite;"></span>
            SYS:AIC-001 · Consensus Engine
        </div>
        <h1 style="font-size: 3rem; font-weight: 800; line-height: 1.1; margin: 0 0 1rem;">
            Structured <span style="background: linear-gradient(90deg, #7c3aed, #22d3ee); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;">intelligence</span><br>for hard decisions.
        </h1>
        <p style="font-size: 1.15rem; color: #a1a1aa; max-width: 60ch; margin: 0 0 2rem;">
            Submit a decision problem. The council frames it, stress-tests assumptions in parallel, and returns a single structured directive — with guardrails baked in.
        </p>
    </div>
    <style>
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
    </style>
    """,
    unsafe_allow_html=True,
)

# Process steps
col1, col2, col3, col4 = st.columns(4)
steps = [
    ("01", "Frame", "Clarify the decision and its criteria."),
    ("02", "Analyze", "Specialist nodes assess independently."),
    ("03", "Challenge", "Claims and biases are pressure-tested."),
    ("04", "Direct", "One actionable output with guardrails."),
]
for col, (num, label, desc) in zip([col1, col2, col3, col4], steps):
    with col:
        st.markdown(
            f"""
            <div style="text-align: center; padding: 1rem; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 12px;">
                <div style="font-size: 1.5rem; font-weight: 700; color: #7c3aed;">{num}</div>
                <div style="font-weight: 600; margin: 0.5rem 0;">{label}</div>
                <div style="font-size: 0.85rem; color: #888;">{desc}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ── Input Card ──
st.markdown(
    """
    <div style="margin: 2rem 0 1rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
            <h2 style="margin: 0;">Input Brief</h2>
            <span style="padding: 0.2rem 0.75rem; background: rgba(124,58,237,0.15); border: 1px solid rgba(124,58,237,0.3); border-radius: 999px; font-size: 0.75rem; color: #a78bfa;">Step 01</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

col_undo, col_redo, _ = st.columns([0.1, 0.1, 0.8])
with col_undo:
    st.button("Undo", on_click=undo, disabled=(st.session_state.history_idx == 0))
with col_redo:
    st.button("Redo", on_click=redo, disabled=(st.session_state.history_idx == len(st.session_state.prompt_history) - 1))

prompt = st.text_area(
    "Decision query",
    key="prompt_input",
    on_change=on_prompt_change,
    height=148,
    placeholder="Describe the decision, scenario, or strategic question for the council to examine...",
    label_visibility="collapsed",
)

# --- Decision Preview ---
word_count = len(prompt.split())
if word_count < 20:
    complexity = "Low"
    time_est = "~15 seconds"
    color = "#22c55e" # green
elif word_count < 100:
    complexity = "Medium"
    time_est = "~30 seconds"
    color = "#f59e0b" # yellow
else:
    complexity = "High"
    time_est = "~60 seconds"
    color = "#ef4444" # red

try:
    num_nodes = len(provider_data.get("roles", [])) if "provider_data" in locals() else 3
except:
    num_nodes = 3

st.markdown(f"""
    <div style="display: flex; gap: 1.5rem; font-size: 0.8rem; color: #888; padding: 0.5rem 1rem; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 8px; margin-top: -0.5rem; margin-bottom: 1rem;">
        <div><strong>Est. time:</strong> {time_est}</div>
        <div><strong>Complexity:</strong> <span style="color: {color}">{complexity}</span></div>
        <div><strong>Required nodes:</strong> {num_nodes} members</div>
        <div><strong>Draft:</strong> Auto-saved</div>
    </div>
""", unsafe_allow_html=True)

with st.expander("Optional weighted decision matrix"):
    matrix_input = st.text_area(
        "Rows: criterion | weight | option A score | option B score",
        placeholder="Speed to value | 4 | 8 | 5\nExecution risk | 5 | 6 | 8",
        height=100,
    )

run_debate = st.toggle(
    "Run peer challenge round",
    value=False,
    help="Uses substantially more provider tokens. Turn it on only for high-stakes or complex decisions.",
)

st.markdown(
    """
    <div style="margin-top: 1rem; padding: 1rem; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 8px; font-size: 0.85rem; color: #888;">
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
        is_valid, error_msg = validate_backend_url(backend_url)
        if not is_valid:
            st.error(f"Invalid backend URL: {error_msg}")
        else:
            st.session_state[SESSION_COUNCIL_ERROR] = None
            st.session_state[SESSION_COUNCIL_RESULT] = None
            st.session_state[SESSION_COUNCIL_PROMPT] = prompt

            try:
                matrix_context, matrix_rows = parse_decision_matrix(matrix_input)
                council_prompt = prompt + matrix_context
                with st.status("Council nodes are processing your brief...", expanded=True) as status:
                    st.write("Initializing deliberation...")

                    def show_progress(event: str, payload: dict[str, Any]) -> None:
                        if event == "charter_ready":
                            st.write("Decision charter ready. Specialists selected.")
                        elif event == "member_done":
                            member = payload.get("role_name", "Council member")
                            phase = payload.get("round", 1)
                            if payload.get("success"):
                                st.write(f"{member} completed phase {phase}.")
                            else:
                                st.warning(f"{member} failed phase {phase}: {payload.get('error', 'provider unavailable')}")
                        elif event == "debate_skipped":
                            st.write("Challenge round skipped: recommendations already aligned.")

                    with CouncilApiClient(backend_url) as client:
                        response: CouncilResponse = client.ask_stream(
                            council_prompt, debate=run_debate, on_event=show_progress,
                        )
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
                    "request_id": response.request_id,
                    "sources": response.sources,
                    "agreement_score": response.agreement_score,
                    "confidence_score": response.confidence_score,
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
        <div style="display: flex; align-items: center; gap: 1rem; margin: 3rem 0 2rem; padding-bottom: 1rem; border-bottom: 1px solid rgba(255,255,255,0.1);">
            <div style="width: 8px; height: 8px; background: #7c3aed; border-radius: 50%;"></div>
            <div style="font-weight: 600; font-size: 1.1rem;">Decision Report</div>
            <div style="flex: 1; height: 1px; background: rgba(255,255,255,0.1);"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div style="margin-bottom: 2rem;">
            <div style="display: inline-flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; color: #22c55e; margin-bottom: 0.5rem;">
                <span style="width: 8px; height: 8px; background: #22c55e; border-radius: 50%;"></span>
                Consensus reached
            </div>
            <h2 style="margin: 0; font-size: 1.75rem; font-weight: 700;">Final Decision Output</h2>
        </div>
        """,
        unsafe_allow_html=True,
    )

    directive_sections = parse_directive(result.get("final_answer"))
    render_directive_grid(directive_sections)

    if result.get("agreement_score") is not None:
        agreement, confidence = st.columns(2)
        agreement.metric("Recommendation alignment", f"{result['agreement_score']:.0%}")
        confidence.metric("Mean confidence", f"{(result.get('confidence_score') or 0):.0%}")

    # Export row
    brief_text = decision_brief_text(result, st.session_state.get(SESSION_COUNCIL_PROMPT))
    export_note, export_copy, export_download = st.columns([1.2, 0.35, 0.45])
    with export_note:
        st.caption("Record includes the original query, decision charter, and full directive.")
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

    if result.get("request_id"):
        with st.expander("Did this decision help?"):
            rating = st.slider("Outcome rating", 1, 5, 3, key=f"rating_{result['request_id']}")
            outcome_note = st.text_area("What happened after this decision?", key=f"note_{result['request_id']}")
            if st.button("Save outcome feedback", key=f"feedback_{result['request_id']}"):
                try:
                    with CouncilApiClient(backend_url) as client:
                        client.save_feedback(result["request_id"], rating, outcome_note)
                    st.success("Outcome feedback saved.")
                except ApiError as error:
                    st.error(str(error))

    # ── Audit Log ──
    with st.expander("View council deliberation record", expanded=False):
        st.markdown(
            """
            <div style="font-size: 0.9rem; color: #888; margin-bottom: 1.5rem;">
                Each node produces an independent analysis (Phase I), then may revise its position after reviewing peer responses (Phase II). The full record is preserved below.
            </div>
            """,
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
            st.info(escape_text(FALLBACK_AUDIT))
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
