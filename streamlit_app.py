"""
streamlit_app.py — CeCe Course Analysis Agent
Web interface — deploy to Streamlit Community Cloud for a shareable URL.
"""

import streamlit as st
import io
import os
import sys
import traceback

# ── Page config (must be first Streamlit call) ──────────────────
st.set_page_config(
    page_title="CeCe Course Analysis Agent",
    page_icon="🎓",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── Import the analysis engine ──────────────────────────────────
try:
    from analyze import (
        read_imscc,
        extract_course_identity,
        extract_modules,
        extract_grading_structure,
        extract_rubrics,
        extract_learning_objectives,
        run_qm_precheck,
        run_udl_precheck,
        calculate_health_score,
        build_analysis_document,
    )
except ImportError as e:
    st.error(f"Could not load analyze.py: {e}")
    st.stop()


# ── Styles ──────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Header accent bar */
    .header-bar {
        background: linear-gradient(135deg, #e94560, #c73652);
        border-radius: 12px;
        padding: 2rem 2rem 1.5rem 2rem;
        margin-bottom: 1.5rem;
        text-align: center;
        color: white;
    }
    .header-bar h1 {
        font-size: 2.4rem;
        font-weight: 800;
        margin: 0;
        letter-spacing: -1px;
    }
    .header-bar p {
        margin: 0.3rem 0 0 0;
        opacity: 0.85;
        font-size: 1rem;
    }

    /* Stat cards */
    .stat-card {
        background: #f8f9ff;
        border: 1px solid #e0e4f0;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
    .stat-number {
        font-size: 2rem;
        font-weight: 700;
        color: #e94560;
        line-height: 1;
    }
    .stat-label {
        font-size: 0.8rem;
        color: #666;
        margin-top: 4px;
    }

    /* Section headers */
    .section-header {
        font-size: 0.85rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #888;
        margin: 1.5rem 0 0.5rem 0;
    }

    /* QM badge colors */
    .badge-pass    { background:#d4edda; color:#155724; padding:3px 10px; border-radius:20px; font-size:0.85rem; font-weight:600; }
    .badge-review  { background:#fff3cd; color:#856404; padding:3px 10px; border-radius:20px; font-size:0.85rem; font-weight:600; }
    .badge-redesign{ background:#f8d7da; color:#721c24; padding:3px 10px; border-radius:20px; font-size:0.85rem; font-weight:600; }

    /* Download button override */
    .stDownloadButton > button {
        background: #e94560 !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.6rem 2rem !important;
        font-size: 1rem !important;
        width: 100%;
    }
    .stDownloadButton > button:hover {
        background: #c73652 !important;
    }

    /* Hide Streamlit branding */
    footer { visibility: hidden; }
    #MainMenu { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ── Header ──────────────────────────────────────────────────────
st.markdown("""
<div class="header-bar">
    <h1>🎓 CeCe</h1>
    <p>Course Analysis Agent &nbsp;·&nbsp; Quality Matters · UDL · Fink's Framework</p>
</div>
""", unsafe_allow_html=True)


# ── Intro ────────────────────────────────────────────────────────
st.markdown("""
Upload your Canvas course export and CeCe will analyze it against 
**Quality Matters 7th Edition**, **UDL**, and **Fink's Significant Learning** 
framework — producing a ready-to-use consultation document for any AI assistant.
""")

with st.expander("ℹ️ How to export your course from Canvas"):
    st.markdown("""
    1. Open your course in Canvas
    2. Go to **Settings** (bottom of the left menu)
    3. Click **Export Course Content**
    4. Select **Course** and click **Create Export**
    5. When ready, click **Download** — you'll get a `.imscc` file
    6. Upload that file below
    """)


# ── File uploader ────────────────────────────────────────────────
st.markdown('<p class="section-header">Step 1 — Upload your course file</p>',
            unsafe_allow_html=True)

uploaded = st.file_uploader(
    label="Select your Canvas .imscc export",
    type=["imscc", "zip"],
    help="Canvas course exports end in .imscc — this is a ZIP file containing your course content.",
    label_visibility="collapsed",
)

if uploaded is None:
    st.info("Upload a .imscc file above to get started. "
            "If your file ends in .zip, that works too.")
    st.stop()


# ── Run analysis ─────────────────────────────────────────────────
st.markdown('<p class="section-header">Step 2 — Analyze</p>',
            unsafe_allow_html=True)

run_button = st.button("▶  Run Analysis", type="primary", use_container_width=True)

if not run_button and "last_result" not in st.session_state:
    st.stop()

# Run (or use cached result if file hasn't changed)
file_id = f"{uploaded.name}_{uploaded.size}"

if run_button or st.session_state.get("last_file_id") != file_id:

    with st.spinner("Reading course content and running QM/UDL pre-check..."):
        try:
            # Capture print() output for the progress log
            import sys
            from io import StringIO
            log_capture = StringIO()
            sys.stdout = log_capture

            # Read the uploaded file bytes
            file_bytes = uploaded.read()

            # Run the analysis engine
            data           = read_imscc(uploaded.name, file_bytes=file_bytes)
            identity       = extract_course_identity(data)
            modules        = extract_modules(data)
            grading_groups = extract_grading_structure(data)
            rubrics        = extract_rubrics(data)
            objectives     = extract_learning_objectives(data, modules)
            qm_results     = run_qm_precheck(data, modules, grading_groups, objectives)
            udl_results    = run_udl_precheck(data)
            qm_counts      = calculate_health_score(qm_results)
            document       = build_analysis_document(
                                data, identity, modules, grading_groups,
                                objectives, qm_results, udl_results,
                                rubrics, qm_counts)

            sys.stdout = sys.__stdout__
            log_output = log_capture.getvalue()

            # Cache result
            st.session_state["last_result"]  = {
                "document":       document,
                "identity":       identity,
                "modules":        modules,
                "grading_groups": grading_groups,
                "objectives":     objectives,
                "qm_results":     qm_results,
                "qm_counts":      qm_counts,
                "data":           data,
                "log":            log_output,
                "filename":       uploaded.name,
            }
            st.session_state["last_file_id"] = file_id

        except Exception as e:
            sys.stdout = sys.__stdout__
            st.error(f"Analysis failed: {e}")
            with st.expander("Error details"):
                st.code(traceback.format_exc())
            st.stop()


# ── Display results ──────────────────────────────────────────────
result = st.session_state.get("last_result")
if not result:
    st.stop()

met, partial, not_met, review_ct, recommendation = result["qm_counts"]
identity   = result["identity"]
modules    = result["modules"]
objectives = result["objectives"]
data       = result["data"]
stats      = data.get("publish_stats", {})

st.success("✅ Analysis complete!")

st.markdown('<p class="section-header">Results Summary</p>', unsafe_allow_html=True)

# ── Course identity ──
st.markdown(f"### {identity['title']} — {identity['code']}")
st.caption(f"{identity['modality']} · {identity['start_date']} to {identity['end_date']}")

# ── Stat cards ──
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.markdown(f'<div class="stat-card"><div class="stat-number">{len(modules)}</div>'
                f'<div class="stat-label">Modules</div></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div class="stat-card"><div class="stat-number">'
                f'{stats.get("assign_published", 0)}</div>'
                f'<div class="stat-label">Assignments</div></div>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<div class="stat-card"><div class="stat-number">{len(objectives)}</div>'
                f'<div class="stat-label">Objectives</div></div>', unsafe_allow_html=True)
with col4:
    st.markdown(f'<div class="stat-card"><div class="stat-number">'
                f'{stats.get("wiki_published", 0)}</div>'
                f'<div class="stat-label">Pages</div></div>', unsafe_allow_html=True)
with col5:
    st.markdown(f'<div class="stat-card"><div class="stat-number">'
                f'{stats.get("wiki_unpublished", 0)}</div>'
                f'<div class="stat-label">Unpublished</div></div>', unsafe_allow_html=True)

st.markdown("")

# ── QM health score ──
badge_class = (
    "badge-pass"     if recommendation.startswith("PASS")     else
    "badge-review"   if recommendation.startswith("REVIEW")   else
    "badge-redesign"
)
badge_label = recommendation.split("—")[0].strip()
badge_note  = recommendation.split("—")[1].strip() if "—" in recommendation else ""

st.markdown(
    f'**QM Recommendation:** <span class="{badge_class}">{badge_label}</span> &nbsp; {badge_note}',
    unsafe_allow_html=True
)

# ── QM breakdown ──
col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric("✅ Met",          met)
col_b.metric("⚠️ Partial",      partial)
col_c.metric("❌ Not Met",      not_met)
col_d.metric("🔍 Needs Review", review_ct)

# ── Syllabus status ──
st.markdown("")
lti_tool = data.get("syllabus_lti_tool")
syl_source = data.get("syllabus_source")

if lti_tool:
    st.warning(f"**Syllabus:** Delivered via **{lti_tool}** (LTI tool) — "
               f"content cannot be extracted. CeCe will ask you to paste it during consultation.")
elif data.get("syllabus_is_embed"):
    st.warning("**Syllabus:** External embed detected — content not readable. "
               "CeCe will ask you to share it.")
elif syl_source == "wiki_page":
    st.success("**Syllabus:** Found in a Canvas wiki page and included in the analysis.")
elif data.get("syllabus_text"):
    st.success("**Syllabus:** Read from Canvas syllabus tab.")
else:
    st.warning("**Syllabus:** Not found. CeCe will ask for it during consultation.")

# ── Unpublished note ──
unpub_assign = stats.get("assign_unpublished", 0)
unpub_pages  = stats.get("wiki_unpublished",   0)
if unpub_assign > 0 or unpub_pages > 0:
    st.info(f"ℹ️ **{unpub_pages} pages** and **{unpub_assign} assignments** were unpublished "
            f"and excluded from the analysis.")


# ── Download ─────────────────────────────────────────────────────
st.markdown('<p class="section-header">Step 3 — Download & consult</p>',
            unsafe_allow_html=True)

base_name    = os.path.splitext(result["filename"])[0]
download_name = f"{base_name}_analysis.md"

st.download_button(
    label="⬇  Download Analysis Document (.md)",
    data=result["document"].encode("utf-8"),
    file_name=download_name,
    mime="text/markdown",
    use_container_width=True,
)

st.markdown("""
**After downloading:**
1. Open the `.md` file in any text editor
2. Select all (Ctrl+A / Cmd+A) and copy
3. Paste into [Claude.ai](https://claude.ai), ChatGPT, or your preferred AI assistant
4. The CeCe consultation prompt is at the bottom of the document
""")


# ── Preview ──────────────────────────────────────────────────────
with st.expander("🔍 Preview the analysis document"):
    st.markdown(result["document"][:8000] + "\n\n*[truncated for preview — download for full document]*")

with st.expander("📋 Analysis log"):
    st.code(result["log"], language=None)


# ── Footer ───────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "CeCe Course Analysis Agent · Built on Fink's Significant Learning, "
    "Quality Matters 7th Edition, and UDL · Developed for TOPkit / Florida SUS"
)
