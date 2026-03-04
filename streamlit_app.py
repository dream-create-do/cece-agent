"""
streamlit_app.py — CeCe Course Extraction Agent v5
Web interface for extracting Canvas course content into a Course Dossier.
"""

import streamlit as st
import io
import os
import sys
import traceback

# ── Page config (must be first Streamlit call) ──────────────────
st.set_page_config(
    page_title="CeCe Course Extraction Agent",
    page_icon="🎓",
    layout="centered",
)

# ── Import the extraction engine ────────────────────────────────
try:
    from analyze import (
        read_imscc,
        extract_course_identity,
        extract_modules,
        extract_grading_structure,
        extract_rubrics,
        build_course_dossier,
    )
except ImportError as e:
    st.error(f"Could not load analyze.py: {e}")
    st.stop()


# ── Styles ──────────────────────────────────────────────────────
st.markdown("""
<style>
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
    .section-header {
        font-size: 0.85rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #888;
        margin: 1.5rem 0 0.5rem 0;
    }
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
    footer { visibility: hidden; }
    #MainMenu { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ── Header ──────────────────────────────────────────────────────
st.markdown("""
<div class="header-bar">
    <h1>🎓 CeCe</h1>
    <p>Course Extraction Agent &nbsp;·&nbsp; Generates a Course Dossier for MeMe</p>
</div>
""", unsafe_allow_html=True)


# ── Intro ────────────────────────────────────────────────────────
st.markdown("""
Upload your Canvas course export and CeCe will extract every piece of published 
content — pages, assignments, rubrics, modules, grading structure, and more — 
into a **Course Dossier** that MeMe uses for QM consultation.

CeCe extracts. MeMe analyzes.
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


# ── Step 1: Course file ─────────────────────────────────────────
st.markdown('<p class="section-header">Step 1 — Upload your course export</p>',
            unsafe_allow_html=True)

uploaded = st.file_uploader(
    label="Select your Canvas .imscc export",
    type=["imscc", "zip"],
    help="Canvas course exports end in .imscc — this is a ZIP file containing your course content.",
    label_visibility="collapsed",
)

if uploaded is None:
    st.info("Upload a .imscc file above to get started.")
    st.stop()

# ── Step 2: Syllabus ────────────────────────────────────────────
st.markdown('<p class="section-header">Step 2 — Provide your syllabus (optional but recommended)</p>',
            unsafe_allow_html=True)

st.markdown(
    "MeMe needs your syllabus to evaluate QM Standards 1 and 2 accurately. "
    "Paste the full text below, or upload a file."
)

syllabus_text = st.text_area(
    label="Paste syllabus text",
    height=200,
    placeholder=(
        "Paste your full syllabus here — course description, learning objectives, "
        "grading breakdown, and policies...\n\n"
        "Tip: If your syllabus is in a .docx or PDF, open it, select all (Ctrl+A), "
        "and paste the text here."
    ),
    label_visibility="collapsed",
)

syl_file = st.file_uploader(
    label="Or upload your syllabus (.txt, .docx, or .pdf)",
    type=["txt", "docx", "pdf"],
    help="Upload your syllabus file. Plain text and Word docs give the best results.",
)
if syl_file is not None:
    fname = syl_file.name.lower()
    try:
        if fname.endswith(".txt"):
            syllabus_text = syl_file.read().decode("utf-8", errors="ignore")

        elif fname.endswith(".docx"):
            import io, zipfile as _zf
            import xml.etree.ElementTree as _ET
            with _zf.ZipFile(io.BytesIO(syl_file.read())) as dz:
                xml_bytes = dz.read("word/document.xml")
            root = _ET.fromstring(xml_bytes)
            ns   = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            paras = root.findall(".//w:p", ns)
            lines = []
            for p in paras:
                text = "".join(t.text or "" for t in p.findall(".//w:t", ns)).strip()
                if text:
                    lines.append(text)
            syllabus_text = "\n".join(lines)

        elif fname.endswith(".pdf"):
            try:
                import io
                import pdfplumber
                with pdfplumber.open(io.BytesIO(syl_file.read())) as pdf:
                    pages = [page.extract_text() or "" for page in pdf.pages]
                syllabus_text = "\n".join(pages).strip()
            except ImportError:
                import io
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(syl_file.read()))
                syllabus_text = "\n".join(
                    page.extract_text() or "" for page in reader.pages
                ).strip()

        if syllabus_text and syllabus_text.strip():
            st.success(f"✅ Extracted {len(syllabus_text):,} characters from {syl_file.name}")
        else:
            st.warning(
                f"⚠️ Could not extract readable text from {syl_file.name}. "
                "This sometimes happens with scanned PDFs. "
                "Please paste your syllabus text in the box above instead."
            )
    except Exception as e:
        st.error(f"Could not read {syl_file.name}: {e}. Please paste your syllabus text above.")

if not syllabus_text or not syllabus_text.strip():
    st.warning(
        "⚠️ No syllabus provided. MeMe will request it at the start of consultation."
    )

# ── Step 3: Run ─────────────────────────────────────────────────
st.markdown('<p class="section-header">Step 3 — Extract</p>',
            unsafe_allow_html=True)

run_button = st.button("▶  Extract Course Content", type="primary", use_container_width=True)

if not run_button and "last_result" not in st.session_state:
    st.stop()

# Run (or use cached result if file/syllabus hasn't changed)
file_id = f"{uploaded.name}_{uploaded.size}_{len(syllabus_text or '')}"

if run_button or st.session_state.get("last_file_id") != file_id:

    with st.spinner("Reading course content..."):
        try:
            from io import StringIO
            log_capture = StringIO()
            sys.stdout = log_capture

            file_bytes = uploaded.read()

            data = read_imscc(
                uploaded.name,
                file_bytes=file_bytes,
                syllabus_text=(syllabus_text or "").strip(),
            )

            identity       = extract_course_identity(data)
            modules        = extract_modules(data)
            grading_groups = extract_grading_structure(data)
            rubrics        = extract_rubrics(data)

            document = build_course_dossier(
                data, identity, modules, grading_groups, rubrics
            )

            sys.stdout = sys.__stdout__
            log_output = log_capture.getvalue()

            # Cache result
            st.session_state["last_result"] = {
                "document":       document,
                "identity":       identity,
                "modules":        modules,
                "grading_groups": grading_groups,
                "rubrics":        rubrics,
                "data":           data,
                "log":            log_output,
                "filename":       uploaded.name,
            }
            st.session_state["last_file_id"] = file_id

        except Exception as e:
            sys.stdout = sys.__stdout__
            st.error(f"Extraction failed: {e}")
            with st.expander("Error details"):
                st.code(traceback.format_exc())
            st.stop()


# ── Display results ─────────────────────────────────────────────
result = st.session_state.get("last_result")
if not result:
    st.stop()

identity = result["identity"]
modules  = result["modules"]
rubrics  = result["rubrics"]
data     = result["data"]
stats    = data.get("publish_stats", {})

st.success("✅ Extraction complete!")

st.markdown('<p class="section-header">Course Summary</p>', unsafe_allow_html=True)

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
    st.markdown(f'<div class="stat-card"><div class="stat-number">'
                f'{stats.get("wiki_published", 0)}</div>'
                f'<div class="stat-label">Pages</div></div>', unsafe_allow_html=True)
with col4:
    st.markdown(f'<div class="stat-card"><div class="stat-number">'
                f'{len(rubrics)}</div>'
                f'<div class="stat-label">Rubrics</div></div>', unsafe_allow_html=True)
with col5:
    st.markdown(f'<div class="stat-card"><div class="stat-number">'
                f'{len(data.get("lti_tools", []))}</div>'
                f'<div class="stat-label">LTI Tools</div></div>', unsafe_allow_html=True)

st.markdown("")

# ── Status notes ──
if data.get("syllabus_text"):
    st.success(f"**Syllabus:** Included ({len(data['syllabus_text']):,} characters).")
else:
    st.warning("**Syllabus:** Not provided. MeMe will request it during consultation.")

unpub_assign = stats.get("assign_unpublished", 0)
unpub_pages  = stats.get("wiki_unpublished",   0)
if unpub_assign > 0 or unpub_pages > 0:
    st.info(f"ℹ️ **{unpub_pages} page(s)** and **{unpub_assign} assignment(s)** were "
            f"unpublished and excluded from the dossier.")

if not rubrics:
    st.warning("⚠️ **No rubrics found** in the export. This is a significant gap for "
               "QM Standard 3.3. MeMe will flag this during consultation.")

# ── Download ─────────────────────────────────────────────────────
st.markdown('<p class="section-header">Step 4 — Download & consult with MeMe</p>',
            unsafe_allow_html=True)

base_name     = os.path.splitext(result["filename"])[0]
download_name = f"{base_name}_dossier.md"

st.download_button(
    label="⬇  Download Course Dossier (.md)",
    data=result["document"].encode("utf-8"),
    file_name=download_name,
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


# ── Preview ─────────────────────────────────────────────────────
with st.expander("🔍 Preview the course dossier"):
    st.markdown(result["document"][:8000] + "\n\n*[truncated for preview — download for full document]*")

with st.expander("📋 Extraction log"):
    st.code(result["log"], language=None)

with st.expander("🔬 Rubric XML Diagnostic"):
    raw_rubric_xml = data.get("rubrics", "")
    if not raw_rubric_xml:
        st.warning("No `course_settings/rubrics.xml` found in the IMSCC export.")
    else:
        st.markdown(f"**Raw rubrics.xml:** {len(raw_rubric_xml):,} characters")

        # Show what ElementTree actually sees
        import xml.etree.ElementTree as _ET
        try:
            _root = _ET.fromstring(raw_rubric_xml)
            st.markdown(f"**Root tag:** `{_root.tag}`")
            st.markdown(f"**Root attribs:** `{_root.attrib}`")

            # Show all direct children of root
            children = list(_root)
            st.markdown(f"**Direct children of root ({len(children)}):**")
            for i, child in enumerate(children[:10]):
                child_children = list(child)
                st.markdown(f"- `<{child.tag}>` — {len(child_children)} sub-elements, attribs: `{child.attrib}`")

            # Try finding rubric at various depths
            st.markdown("**Searching for `<rubric>` elements:**")
            r1 = _root.findall('rubric')
            r2 = _root.findall('.//rubric')
            r3 = _root.findall('.//{*}rubric')  # wildcard namespace
            st.markdown(f"- `findall('rubric')`: {len(r1)}")
            st.markdown(f"- `findall('.//rubric')`: {len(r2)}")
            st.markdown(f"- `findall('.//" + "{*}" + "rubric')` (wildcard ns): {len(r3)}")

            # Show first 500 chars of raw XML
            st.markdown("**First 500 chars of raw XML:**")
            st.code(raw_rubric_xml[:500], language="xml")

            # If we found rubrics with wildcard, show the namespace
            if r3 and not r2:
                st.warning(f"Rubrics found with namespace wildcard! First rubric tag: `{r3[0].tag}`")

        except Exception as _e:
            st.error(f"XML parse error: {_e}")
            st.code(raw_rubric_xml[:1000], language="xml")


# ── Footer ──────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "CeCe Course Extraction Agent v5 · Part of the CeCe / MeMe / DeDe "
    "Instructional Design Suite · Developed for TOPkit / Florida SUS"
)
