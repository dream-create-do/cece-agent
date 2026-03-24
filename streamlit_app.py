"""
streamlit_app.py — CeCe Course DNA Extraction Agent v6
Vice/Spring palette · Lexend typography · DNA + graduation cap branding
"""

import streamlit as st
import io
import os
import sys
import traceback

st.set_page_config(page_title="CeCe — Course DNA", page_icon="🧬", layout="centered")

try:
    from analyze import (
        read_imscc, extract_course_identity, extract_modules,
        extract_grading_structure, extract_rubrics, build_course_dna,
    )
except ImportError as e:
    st.error(f"Could not load analyze.py: {e}")
    st.stop()


# ── Styles ──────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Lexend:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Lexend', sans-serif !important; }

    .header-bar {
        background: linear-gradient(135deg, #ff6b9d 0%, #c44dff 50%, #6c5ce7 100%);
        border-radius: 16px;
        padding: 2.5rem 2rem 2rem;
        margin-bottom: 1.5rem;
        text-align: center;
        color: white;
    }
    .header-bar h1 {
        font-family: 'Lexend', sans-serif !important;
        font-size: 2.2rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: 2px;
    }
    .header-bar p {
        margin: 0.25rem 0 0 0;
        opacity: 0.85;
        font-size: 0.9rem;
        font-weight: 300;
        letter-spacing: 1.5px;
        text-transform: uppercase;
    }

    .intro-box {
        border: 1px solid #eee;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1.5rem;
    }
    .intro-box p { font-size: 15px; line-height: 1.7; margin: 0; }
    .intro-box .sub { font-size: 13.5px; color: #888; margin-top: 0.5rem; }
    .highlight { color: #c44dff; font-weight: 600; }

    .step-row { display: flex; gap: 12px; margin-bottom: 1.5rem; }
    .step-card {
        flex: 1;
        background: #f8f9fa;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
    .step-card .num {
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 4px;
    }
    .step-card .title { font-size: 13px; font-weight: 500; color: #333; }
    .step-card .desc { font-size: 11.5px; color: #888; margin-top: 2px; }
    .step1 { border-top: 3px solid #ff6b9d; }
    .step1 .num { color: #ff6b9d; }
    .step2 { border-top: 3px solid #c44dff; }
    .step2 .num { color: #c44dff; }
    .step3 { border-top: 3px solid #6c5ce7; }
    .step3 .num { color: #6c5ce7; }
    .step4 { border-top: 3px solid #00b894; }
    .step4 .num { color: #00b894; }

    .stat-card {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 10px;
        text-align: center;
    }
    .stat-number {
        font-size: 22px;
        font-weight: 700;
        color: #c44dff;
        line-height: 1;
    }
    .stat-label { font-size: 11px; color: #888; margin-top: 4px; }

    .section-header {
        font-family: 'Lexend', sans-serif !important;
        font-size: 11px !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 1.2px;
        color: #888;
        margin: 1.5rem 0 0.5rem 0;
    }

    .stButton > button[kind="primary"],
    .stDownloadButton > button {
        background: linear-gradient(135deg, #ff6b9d, #c44dff, #6c5ce7) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        font-family: 'Lexend', sans-serif !important;
        font-weight: 600 !important;
        padding: 0.75rem 2rem !important;
        font-size: 15px !important;
        width: 100%;
        letter-spacing: 0.5px;
    }
    .stButton > button[kind="primary"]:hover,
    .stDownloadButton > button:hover {
        background: linear-gradient(135deg, #e8568a, #b340e8, #5a4dd0) !important;
    }

    footer { visibility: hidden; }
    #MainMenu { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ── Header with SVG logo ────────────────────────────────────────
st.markdown("""
<div class="header-bar">
    <svg width="90" height="100" viewBox="0 0 90 100" style="margin-bottom: 6px;">
        <polygon points="45,12 10,28 45,44 80,28" fill="#ffffff" opacity="0.95"/>
        <polygon points="45,44 80,28 80,32 45,48" fill="#e0e0e0" opacity="0.7"/>
        <polygon points="45,44 10,28 10,32 45,48" fill="#f0f0f0" opacity="0.8"/>
        <rect x="44" y="12" width="2" height="8" fill="#ffffff" opacity="0.9"/>
        <rect x="43" y="8" width="4" height="5" rx="1" fill="#ffffff" opacity="0.9"/>
        <line x1="76" y1="28" x2="82" y2="42" stroke="#ffd93d" stroke-width="2" stroke-linecap="round"/>
        <circle cx="82" cy="44" r="3" fill="#ffd93d"/>
        <path d="M 33 48 Q 45 56 33 64 Q 21 72 33 80 Q 45 88 33 96" fill="none" stroke="rgba(255,255,255,0.9)" stroke-width="2.5" stroke-linecap="round"/>
        <path d="M 57 48 Q 45 56 57 64 Q 69 72 57 80 Q 45 88 57 96" fill="none" stroke="rgba(255,255,255,0.65)" stroke-width="2.5" stroke-linecap="round"/>
        <line x1="36" y1="52" x2="54" y2="52" stroke="rgba(255,255,255,0.4)" stroke-width="1.5" stroke-linecap="round"/>
        <line x1="30" y1="60" x2="60" y2="60" stroke="rgba(255,255,255,0.4)" stroke-width="1.5" stroke-linecap="round"/>
        <line x1="27" y1="68" x2="63" y2="68" stroke="rgba(255,255,255,0.4)" stroke-width="1.5" stroke-linecap="round"/>
        <line x1="30" y1="76" x2="60" y2="76" stroke="rgba(255,255,255,0.4)" stroke-width="1.5" stroke-linecap="round"/>
        <line x1="36" y1="84" x2="54" y2="84" stroke="rgba(255,255,255,0.4)" stroke-width="1.5" stroke-linecap="round"/>
        <line x1="30" y1="92" x2="60" y2="92" stroke="rgba(255,255,255,0.4)" stroke-width="1.5" stroke-linecap="round"/>
    </svg>
    <h1>CeCe</h1>
    <p>Course DNA Extraction Agent</p>
</div>
""", unsafe_allow_html=True)


# ── Intro + Steps ───────────────────────────────────────────────
st.markdown("""
<div class="intro-box">
    <p>CeCe reads your Canvas course export and extracts its complete DNA — every page, assignment, rubric, module, and grading structure — into a single <span class="highlight">Course DNA Document</span> that MeMe uses for QM consultation.</p>
    <p class="sub">CeCe extracts. She does not evaluate or judge. That's MeMe's job.</p>
</div>
<div class="step-row">
    <div class="step-card step1"><div class="num">Step 1</div><div class="title">Upload .imscc</div><div class="desc">Canvas course export</div></div>
    <div class="step-card step2"><div class="num">Step 2</div><div class="title">Add syllabus</div><div class="desc">Paste or upload (optional)</div></div>
    <div class="step-card step3"><div class="num">Step 3</div><div class="title">Extract</div><div class="desc">Generate Course DNA</div></div>
    <div class="step-card step4"><div class="num">Step 4</div><div class="title">Download</div><div class="desc">Send to MeMe</div></div>
</div>
""", unsafe_allow_html=True)


# ── Step 1: Upload ──────────────────────────────────────────────
st.markdown('<p class="section-header">Step 1 — Upload your course export</p>', unsafe_allow_html=True)

uploaded = st.file_uploader(
    "Select your Canvas .imscc export",
    type=["imscc", "zip"],
    help="Canvas course exports end in .imscc — this is a ZIP file.",
    label_visibility="collapsed",
)

if uploaded is None:
    st.info("Upload a .imscc file above to get started.")
    st.stop()

with st.expander("ℹ️ How to export your course from Canvas"):
    st.markdown("""
    1. Open your course in Canvas
    2. Go to **Settings** (bottom of the left menu)
    3. Click **Export Course Content**
    4. Select **Course** and click **Create Export**
    5. When ready, click **Download** — you'll get a `.imscc` file
    """)


# ── Step 2: Syllabus ────────────────────────────────────────────
st.markdown('<p class="section-header">Step 2 — Provide your syllabus (recommended)</p>', unsafe_allow_html=True)

syllabus_text = st.text_area(
    "Paste syllabus text",
    height=180,
    placeholder="Paste your full syllabus here — course description, learning objectives, grading breakdown, and policies...",
    label_visibility="collapsed",
)

syl_file = st.file_uploader("Or upload syllabus (.txt, .docx, .pdf)", type=["txt", "docx", "pdf"])
if syl_file is not None:
    fname = syl_file.name.lower()
    try:
        if fname.endswith(".txt"):
            syllabus_text = syl_file.read().decode("utf-8", errors="ignore")
        elif fname.endswith(".docx"):
            import zipfile as _zf
            import xml.etree.ElementTree as _ET
            with _zf.ZipFile(io.BytesIO(syl_file.read())) as dz:
                xml_bytes = dz.read("word/document.xml")
            root = _ET.fromstring(xml_bytes)
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            lines = []
            for p in root.findall(".//w:p", ns):
                text = "".join(t.text or "" for t in p.findall(".//w:t", ns)).strip()
                if text: lines.append(text)
            syllabus_text = "\n".join(lines)
        elif fname.endswith(".pdf"):
            try:
                import pdfplumber
                with pdfplumber.open(io.BytesIO(syl_file.read())) as pdf:
                    syllabus_text = "\n".join(page.extract_text() or "" for page in pdf.pages).strip()
            except ImportError:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(syl_file.read()))
                syllabus_text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if syllabus_text and syllabus_text.strip():
            st.success(f"✅ Extracted {len(syllabus_text):,} characters from {syl_file.name}")
        else:
            st.warning(f"⚠️ Could not extract text from {syl_file.name}. Please paste it above instead.")
    except Exception as e:
        st.error(f"Could not read {syl_file.name}: {e}")

if not syllabus_text or not syllabus_text.strip():
    st.warning("⚠️ No syllabus provided. MeMe will request it at the start of consultation.")


# ── Step 3: Extract ─────────────────────────────────────────────
st.markdown('<p class="section-header">Step 3 — Extract</p>', unsafe_allow_html=True)

run_button = st.button("🧬  Extract Course DNA", type="primary", use_container_width=True)

if not run_button and "last_result" not in st.session_state:
    st.stop()

file_id = f"{uploaded.name}_{uploaded.size}_{len(syllabus_text or '')}"

if run_button or st.session_state.get("last_file_id") != file_id:
    with st.spinner("Reading course content..."):
        try:
            from io import StringIO
            log_capture = StringIO()
            sys.stdout = log_capture

            file_bytes = uploaded.read()
            data = read_imscc(uploaded.name, file_bytes=file_bytes,
                              syllabus_text=(syllabus_text or "").strip())
            identity       = extract_course_identity(data)
            modules        = extract_modules(data)
            grading_groups = extract_grading_structure(data)
            rubrics        = extract_rubrics(data)
            document       = build_course_dna(data, identity, modules, grading_groups, rubrics)

            sys.stdout = sys.__stdout__
            log_output = log_capture.getvalue()

            st.session_state["last_result"] = {
                "document": document, "identity": identity, "modules": modules,
                "grading_groups": grading_groups, "rubrics": rubrics,
                "data": data, "log": log_output, "filename": uploaded.name,
            }
            st.session_state["last_file_id"] = file_id
        except Exception as e:
            sys.stdout = sys.__stdout__
            st.error(f"Extraction failed: {e}")
            with st.expander("Error details"):
                st.code(traceback.format_exc())
            st.stop()


# ── Results ─────────────────────────────────────────────────────
result = st.session_state.get("last_result")
if not result:
    st.stop()

identity = result["identity"]
modules  = result["modules"]
rubrics  = result["rubrics"]
data     = result["data"]
stats    = data.get("publish_stats", {})

st.success("✅ Extraction complete!")

st.markdown('<p class="section-header">Results</p>', unsafe_allow_html=True)

st.markdown(f"### {identity['title']} — {identity['code']}")
st.caption(f"{identity['modality']} · {identity['start_date']} to {identity['end_date']}")

# Stat cards
col1, col2, col3, col4, col5 = st.columns(5)
for col, val, label in [
    (col1, len(modules), "Modules"),
    (col2, stats.get("assign_published", 0), "Assignments"),
    (col3, stats.get("wiki_published", 0), "Pages"),
    (col4, len(rubrics), "Rubrics"),
    (col5, len(data.get("lti_tools", [])), "LTI Tools"),
]:
    with col:
        st.markdown(f'<div class="stat-card"><div class="stat-number">{val}</div>'
                    f'<div class="stat-label">{label}</div></div>', unsafe_allow_html=True)

st.markdown("")

if data.get("syllabus_text"):
    st.success(f"**Syllabus:** Included ({len(data['syllabus_text']):,} characters).")
else:
    st.warning("**Syllabus:** Not provided. MeMe will request it during consultation.")

unpub = stats.get("assign_unpublished", 0) + stats.get("wiki_unpublished", 0)
if unpub > 0:
    st.info(f"ℹ️ **{unpub} item(s)** were unpublished and excluded from the Course DNA Document.")

if not rubrics:
    st.warning("⚠️ **No rubrics found.** MeMe will flag this for QM Standard 3.3.")


# ── Step 4: Download ────────────────────────────────────────────
st.markdown('<p class="section-header">Step 4 — Download & consult with MeMe</p>', unsafe_allow_html=True)

base_name = os.path.splitext(result["filename"])[0]

st.download_button(
    label="⬇  Download Course DNA Document (.md)",
    data=result["document"].encode("utf-8"),
    file_name=f"{base_name}_dna.md",
    mime="text/markdown",
    use_container_width=True,
)

st.markdown("""
**After downloading:**
1. Open the `.md` file in any text editor
2. Select all (Ctrl+A / Cmd+A) and copy
3. Paste into your MeMe consultation (Claude, ChatGPT, or Gemini)
4. MeMe will conduct a full QM needs analysis and guide you through remediation
""")


# ── Expanders ───────────────────────────────────────────────────
with st.expander("🔍 Preview the Course DNA Document"):
    st.markdown(result["document"][:8000] + "\n\n*[truncated for preview — download for full document]*")

with st.expander("📋 Extraction log"):
    st.code(result["log"], language=None)

with st.expander("🔬 Rubric XML diagnostic"):
    raw_xml = data.get("rubrics", "")
    if not raw_xml:
        st.warning("No rubrics.xml found in the IMSCC export.")
    else:
        st.markdown(f"**Raw rubrics.xml:** {len(raw_xml):,} characters")
        import re as _re
        _clean = _re.sub(r'\sxmlns(?::\w+)?\s*=\s*["\'][^"\']*["\']', '', raw_xml)
        _clean = _re.sub(r'\s\w+:\w+\s*=\s*["\'][^"\']*["\']', '', _clean)
        _clean = _re.sub(r'<(/?)[\w]+:', r'<\1', _clean)
        try:
            import xml.etree.ElementTree as _ET
            _root = _ET.fromstring(_clean)
            st.markdown(f"**Root tag:** `{_root.tag}`")
            all_tags = sorted(set(el.tag for el in _root.iter()))
            st.markdown(f"**All tags ({len(all_tags)}):** {', '.join(all_tags)}")
            for tag in ['rubric', 'criterion', 'rating', 'criteria', 'ratings']:
                found = _root.findall(f'.//{tag}')
                st.markdown(f"- `.//{tag}`: **{len(found)}**")
        except Exception as _e:
            st.error(f"XML parse error: {_e}")
        st.markdown("**First 500 chars:**")
        st.code(raw_xml[:500], language="xml")


# ── Footer ──────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "CeCe v6.1 · Course DNA Extraction Agent · CeCe / MeMe / DeDe Suite · TOPkit / Florida SUS"
)
