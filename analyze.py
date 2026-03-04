"""
analyze.py — CeCe Course Extraction Agent v5.0
================================================

CeCe is a *court reporter*, not a judge. She reads Canvas IMSCC exports,
extracts every piece of course content, organizes it faithfully, and
presents it as a Course Dossier for MeMe to analyze.

CeCe does NOT:
  - Evaluate QM standards (that's MeMe's job)
  - Tag objectives with Bloom's levels (that's MeMe's job)
  - Build alignment matrices (that's MeMe's job)
  - Judge UDL compliance (that's MeMe's job)
  - Make recommendations (that's MeMe's job)

CeCe DOES:
  - Extract ALL published content pages (full text)
  - Extract ALL published assignments (instructions, points, due dates, submission type)
  - Extract module structure with items and week labels
  - Extract grading groups with weights
  - Extract FULL rubric detail (criteria + every rating level with descriptions)
  - Extract quiz/assessment content
  - Detect LTI/external tool integrations
  - Organize everything into a clean, numbered-section document
  - Append a condensed QM 7th Edition reference so MeMe has it regardless of platform
"""

import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime


# ─────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────

MEDIA_KEYWORDS = [
    'video-', 'podcast-', 'webpage-', 'netflix-', 'movie-',
    'trigger-warning', 'youtube', 'playposit', 'voicethread',
    'zoom-', 'canvas-student', 'canvas-overview', 'recommended-browsers',
    'technical-', 'chrome-', 'navigate-canvas', 'honorlock',
    'respondus', 'turnitin', 'how-to-', 'update-your', 'global-navigation',
    'accessibility-', 'fiu-resources', 'note-for-support',
    'faculty-guided', 'proctored', 'sample-rubric', 'spot-survey',
    'working-in-teams', 'getting-started-with-group', 'embedding-',
    'directions-on-submitting', 'how-do-i-', 'student-guide',
    'canvas-student-guide', 'submitting-an-assignment', 'submitting-a-',
    'recording-a-', 'uploading-a-', 'downloading-', 'installing-'
]


# ─────────────────────────────────────────────────────────────
#  UTILITY
# ─────────────────────────────────────────────────────────────

def strip_html(html_content):
    html_content = re.sub(r'<(script|style)[^>]*>.*?</(script|style)>',
                          '', html_content, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', html_content)
    for entity, char in [('&nbsp;',' '),('&amp;','&'),('&lt;','<'),
                          ('&gt;','>'),('&quot;','"'),('&#39;',"'")]:
        text = text.replace(entity, char)
    return re.sub(r'\s+', ' ', text).strip()


def is_media_page(page_name):
    return any(k in page_name.lower() for k in MEDIA_KEYWORDS)


def clean_assignment_name(folder_id, file_name):
    name = file_name.replace('.html','').replace('-|-',' | ').replace('-',' ')
    return ' '.join(w.capitalize() for w in name.split())


def format_due_date(iso_string):
    if not iso_string:
        return 'Not set'
    try:
        dt = datetime.strptime(iso_string[:19], '%Y-%m-%dT%H:%M:%S')
        return dt.strftime('%m/%d/%Y %I:%M %p')
    except Exception:
        return iso_string


def is_published_state(workflow_state):
    """
    Canvas workflow states:
      active / published   → published (visible to students)
      unpublished / draft  → not visible to students
    """
    return workflow_state.lower().strip() in ('active', 'published', '')


# ─────────────────────────────────────────────────────────────
#  PUBLISH STATE RESOLVER
# ─────────────────────────────────────────────────────────────

def build_published_file_set(module_meta_xml, manifest_xml):
    """
    Returns a set of file hrefs (e.g. 'wiki_content/page-name.html')
    that are published (workflow_state = active) in at least one module.
    """
    # Step 1 — module item publish states
    item_states = {}
    item_blocks = re.split(r'<item\s+identifier=[^>]+>', module_meta_xml)[1:]
    for block in item_blocks:
        ref_m   = re.search(r'<identifierref>(.+?)</identifierref>', block, re.DOTALL)
        state_m = re.search(r'<workflow_state>(.+?)</workflow_state>', block, re.DOTALL)
        if ref_m:
            ref   = ref_m.group(1).strip()
            state = state_m.group(1).strip() if state_m else 'active'
            if ref not in item_states or is_published_state(state):
                item_states[ref] = state

    # Step 2 — manifest identifier → file href
    id_to_href = {}
    resource_blocks = re.split(r'<resource\s', manifest_xml)[1:]
    for block in resource_blocks:
        id_m   = re.search(r'identifier=["\']([^"\']+)["\']', block)
        href_m = re.search(r'href=["\']([^"\']+)["\']', block)
        if id_m and href_m:
            id_to_href[id_m.group(1)] = href_m.group(1)

    # Step 3 — build published set
    published_hrefs = set()
    for ref, state in item_states.items():
        if is_published_state(state) and ref in id_to_href:
            published_hrefs.add(id_to_href[ref])

    return published_hrefs, item_states, id_to_href


# ─────────────────────────────────────────────────────────────
#  IMSCC READER
# ─────────────────────────────────────────────────────────────

def read_imscc(file_path, file_bytes=None, syllabus_text=''):
    """
    Accepts either:
      file_path: str    — path to a .imscc file on disk (CLI mode)
      file_bytes: bytes — in-memory content (Streamlit upload mode)
      syllabus_text: str — full syllabus text provided directly by the user
    When file_bytes is provided, file_path is used only for display.
    """
    import io
    display_name = os.path.basename(file_path) if file_path else "uploaded file"
    print(f"\n📂 Opening: {display_name}")
    zip_source = io.BytesIO(file_bytes) if file_bytes is not None else file_path

    data = {
        'file_name':          display_name,
        'all_files':          [],
        'syllabus_text':       '',
        'course_settings':    '',
        'assignment_groups':  '',
        'module_meta':        '',
        'rubrics':            '',
        'manifest':           '',
        'wiki_full':          {},
        'wiki_titles':        [],
        'wiki_unpublished':   [],
        'assignments':        {},
        'assignments_unpub':  [],
        'assessments':        {},
        'lti_tools':          [],
        'publish_stats':      {},
    }

    with zipfile.ZipFile(zip_source, 'r') as z:
        data['all_files'] = z.namelist()
        files = data['all_files']
        print(f"   Total files in package: {len(files)}")

        # ── Settings files ──
        for path, key in [
            ('course_settings/course_settings.xml',   'course_settings'),
            ('course_settings/assignment_groups.xml', 'assignment_groups'),
            ('course_settings/module_meta.xml',       'module_meta'),
            ('course_settings/rubrics.xml',           'rubrics'),
            ('imsmanifest.xml',                       'manifest'),
        ]:
            if path in files:
                data[key] = z.read(path).decode('utf-8', errors='ignore')

        # ── Syllabus ──
        if syllabus_text:
            data['syllabus_text'] = syllabus_text.strip()
            print(f'   Syllabus: {len(syllabus_text):,} chars provided by user')
        else:
            print('   Syllabus: not provided — will be requested by MeMe')

        # ── Build published file set ──
        published_hrefs, item_states, id_to_href = build_published_file_set(
            data['module_meta'], data['manifest']
        )

        # ── LTI / External Tools (from manifest) ──
        for block in re.split(r'<resource\s', data['manifest'])[1:]:
            type_m = re.search(r'type=["\']([^"\']+)["\']', block)
            if type_m and ('basiclti' in type_m.group(1).lower()
                           or 'imsbasiclti' in type_m.group(1).lower()):
                title_m = re.search(r'<title>(.+?)</title>', block, re.DOTALL)
                url_m   = re.search(r'<blti:launch_url>(.+?)</blti:launch_url>',
                                    block, re.DOTALL)
                tool_name = strip_html(title_m.group(1)).strip() if title_m else 'Unknown LTI Tool'
                tool_url  = url_m.group(1).strip() if url_m else ''
                data['lti_tools'].append({'name': tool_name, 'url': tool_url})

        # Also check for LTI links in standalone XML files
        for f in files:
            if 'basiclti' in f.lower() or 'blti' in f.lower():
                try:
                    xml = z.read(f).decode('utf-8', errors='ignore')
                    title_m = re.search(r'<blti:title>(.+?)</blti:title>', xml, re.DOTALL)
                    url_m   = re.search(r'<blti:launch_url>(.+?)</blti:launch_url>',
                                        xml, re.DOTALL)
                    if title_m:
                        name = strip_html(title_m.group(1)).strip()
                        url  = url_m.group(1).strip() if url_m else ''
                        # Avoid duplicates
                        if not any(t['name'] == name for t in data['lti_tools']):
                            data['lti_tools'].append({'name': name, 'url': url})
                except Exception:
                    pass

        if data['lti_tools']:
            print(f"   LTI tools detected: {len(data['lti_tools'])}")

        # ── Wiki pages — filter by publish state ──
        wiki_files = [f for f in files
                      if f.startswith('wiki_content/') and f.endswith('.html')]
        print(f"   Wiki/content pages (total): {len(wiki_files)}")

        wiki_pub   = 0
        wiki_unpub = 0

        for page_path in wiki_files:
            page_name = page_path.replace('wiki_content/', '').replace('.html', '')

            if page_path in published_hrefs:
                published = True
            elif not item_states:
                published = True
            else:
                published = False

            if not published:
                wiki_unpub += 1
                data['wiki_unpublished'].append(page_name)
                continue

            wiki_pub += 1
            if is_media_page(page_name):
                data['wiki_titles'].append(page_name)
            else:
                try:
                    raw   = z.read(page_path).decode('utf-8', errors='ignore')
                    clean = strip_html(raw).strip()
                    if clean:
                        data['wiki_full'][page_name] = clean
                except Exception:
                    data['wiki_full'][page_name] = '[could not read]'

        print(f"   Wiki pages published: {wiki_pub} | unpublished/unused: {wiki_unpub}")

        # ── Assignments ──
        assign_html_files = [
            f for f in files
            if f.endswith('.html')
            and not f.startswith('wiki_content/')
            and not f.startswith('web_resources/')
            and 'syllabus' not in f.lower()
            and '/' in f
        ]

        assign_pub   = 0
        assign_unpub = 0

        for assign_path in assign_html_files:
            try:
                parts     = assign_path.split('/')
                folder_id = parts[0]
                file_name = parts[-1]

                settings_path = f"{folder_id}/assignment_settings.xml"
                published     = True
                due_date      = 'Not set'
                points        = 'Not specified'
                sub_type      = 'Not specified'
                clean_name    = clean_assignment_name(folder_id, file_name)

                if settings_path in files:
                    xml = z.read(settings_path).decode('utf-8', errors='ignore')

                    state_m  = re.search(r'<workflow_state>(.+?)</workflow_state>', xml, re.DOTALL)
                    due_m    = re.search(r'<due_at>(.+?)</due_at>', xml, re.DOTALL)
                    pts_m    = re.search(r'<points_possible>(.+?)</points_possible>', xml, re.DOTALL)
                    sub_m    = re.search(r'<submission_types>(.+?)</submission_types>', xml, re.DOTALL)
                    title_m  = re.search(r'<title>(.+?)</title>', xml, re.DOTALL)

                    if state_m:
                        published = is_published_state(state_m.group(1))
                    if due_m:
                        due_date = format_due_date(due_m.group(1).strip())
                    if pts_m:
                        points = pts_m.group(1).strip()
                    if sub_m:
                        sub_type = strip_html(sub_m.group(1)).strip()
                    if title_m:
                        clean_name = strip_html(title_m.group(1)).strip()

                if not published:
                    assign_unpub += 1
                    data['assignments_unpub'].append(clean_name)
                    continue

                raw_html     = z.read(assign_path).decode('utf-8', errors='ignore')
                instructions = strip_html(raw_html).strip()

                if instructions:
                    assign_pub += 1
                    data['assignments'][clean_name] = {
                        'instructions': instructions,
                        'due_date':     due_date,
                        'points':       points,
                        'sub_type':     sub_type,
                        'folder_id':    folder_id,
                    }

            except Exception:
                pass

        print(f"   Assignments published: {assign_pub} | unpublished: {assign_unpub}")

        # ── Assessments/quizzes ──
        assess_files = [f for f in files if 'assessment_qti.xml' in f]
        assess_pub   = 0
        assess_unpub = 0

        for assess_path in assess_files[:15]:
            try:
                folder_id     = assess_path.split('/')[0]
                settings_path = f"{folder_id}/assessment_meta.xml"
                published     = True

                if settings_path in files:
                    xml     = z.read(settings_path).decode('utf-8', errors='ignore')
                    state_m = re.search(r'<workflow_state>(.+?)</workflow_state>', xml, re.DOTALL)
                    if state_m:
                        published = is_published_state(state_m.group(1))

                if not published:
                    assess_unpub += 1
                    continue

                raw   = z.read(assess_path).decode('utf-8', errors='ignore')
                clean = strip_html(raw).strip()
                name  = assess_path.split('/')[-2]
                if clean:
                    assess_pub += 1
                    data['assessments'][name] = clean[:2000]

            except Exception:
                pass

        print(f"   Assessments published: {assess_pub} | unpublished: {assess_unpub}")

        # ── Publish stats ──
        data['publish_stats'] = {
            'wiki_published':       wiki_pub,
            'wiki_unpublished':     wiki_unpub,
            'assign_published':     assign_pub,
            'assign_unpublished':   assign_unpub,
            'assess_published':     assess_pub,
            'assess_unpublished':   assess_unpub,
        }

    return data


# ─────────────────────────────────────────────────────────────
#  EXTRACTORS
# ─────────────────────────────────────────────────────────────

def extract_course_identity(data):
    identity = {'title':'Unknown','code':'Unknown',
                'modality':'Unknown','start_date':'Unknown','end_date':'Unknown'}
    settings = data.get('course_settings', '')
    if not settings:
        return identity
    for tag, key in [('title','title'),('course_code','code'),
                     ('start_at','start_date'),('conclude_at','end_date')]:
        m = re.search(rf'<{tag}>(.+?)</{tag}>', settings, re.DOTALL)
        if m:
            val = strip_html(m.group(1)).strip()
            identity[key] = val[:10] if key in ('start_date','end_date') else val
    combined = (' '.join(data.get('wiki_full',{}).values()) +
                data.get('syllabus_text','')).lower()
    if 'online' in combined:
        identity['modality'] = 'Online'
    elif 'hybrid' in combined:
        identity['modality'] = 'Hybrid'
    elif 'face-to-face' in combined or 'in-person' in combined:
        identity['modality'] = 'Face-to-Face'
    return identity


def extract_modules(data):
    """Parse modules, detect weeks within them, filter to published items only."""
    modules = []
    meta = data.get('module_meta', '')
    if not meta:
        return modules

    module_blocks = re.split(r'<module\s+identifier=[^>]+>', meta)[1:]

    for block in module_blocks:
        title_m = re.search(r'<title>(.+?)</title>', block, re.DOTALL)
        pos_m   = re.search(r'<position>(.+?)</position>', block, re.DOTALL)
        state_m = re.search(r'<workflow_state>(.+?)</workflow_state>', block, re.DOTALL)

        mod_title = strip_html(title_m.group(1)).strip() if title_m else 'Untitled Module'
        pos       = pos_m.group(1).strip()               if pos_m   else '?'
        state     = state_m.group(1).strip()              if state_m else 'active'

        if not is_published_state(state):
            continue

        items_section = re.search(r'<items>(.*?)</items>', block, re.DOTALL)
        items        = []
        current_week = None

        if items_section:
            item_blocks = re.split(r'<item\s+identifier=[^>]+>', items_section.group(1))[1:]
            for item_block in item_blocks:
                t_m     = re.search(r'<title>(.+?)</title>', item_block, re.DOTALL)
                ct_m    = re.search(r'<content_type>(.+?)</content_type>', item_block, re.DOTALL)
                istate_m = re.search(r'<workflow_state>(.+?)</workflow_state>', item_block, re.DOTALL)

                if not t_m:
                    continue

                item_title  = strip_html(t_m.group(1)).strip()
                item_type   = strip_html(ct_m.group(1)).strip() if ct_m else ''
                item_state  = istate_m.group(1).strip() if istate_m else 'active'

                if not is_published_state(item_state):
                    continue

                week_match = re.match(
                    r'week\s+(\d+)\s*(?:[|:—\-]\s*(.+))?',
                    item_title, re.IGNORECASE
                )
                if week_match:
                    week_num   = week_match.group(1)
                    week_label = week_match.group(2).strip() if week_match.group(2) else ''
                    current_week = f"Week {week_num}" + (f" — {week_label}" if week_label else '')
                    items.append({'title': item_title, 'type': item_type,
                                  'is_week_header': True, 'week': current_week,
                                  'published': True})
                else:
                    items.append({'title': item_title, 'type': item_type,
                                  'is_week_header': False, 'week': current_week,
                                  'published': True})

        weeks_in_module = sorted(
            set(i['week'] for i in items if i.get('week') and i.get('is_week_header')),
            key=lambda w: int(re.search(r'\d+', w).group()) if re.search(r'\d+', w) else 0
        )

        modules.append({
            'title':           mod_title,
            'position':        pos,
            'state':           state,
            'items':           items,
            'weeks_in_module': weeks_in_module,
        })

    return modules


def extract_grading_structure(data):
    groups = []
    xml = data.get('assignment_groups', '')
    if not xml:
        return groups
    for block in re.split(r'<assignmentGroup\s+identifier=[^>]+>', xml)[1:]:
        t_m = re.search(r'<title>(.+?)</title>', block, re.DOTALL)
        w_m = re.search(r'<group_weight>(.+?)</group_weight>', block, re.DOTALL)
        p_m = re.search(r'<position>(.+?)</position>', block, re.DOTALL)
        name = strip_html(t_m.group(1)).strip() if t_m else 'Unnamed'
        pos  = p_m.group(1).strip()              if p_m else '?'
        try:
            weight = f"{float(w_m.group(1).strip()):.1f}" if w_m else '0.0'
        except ValueError:
            weight = w_m.group(1).strip() if w_m else '0.0'
        groups.append({'name': name, 'weight': weight, 'position': pos})
    groups.sort(key=lambda g: int(g['position']) if g['position'].isdigit() else 99)
    return groups


def extract_rubrics(data):
    """
    Deep rubric extraction from Canvas rubrics.xml using proper XML parsing.

    Canvas XML structure (confirmed from live export diagnostic):
      <rubrics>
        <rubric>
          <title>Rubric Name</title>
          <points_possible>100.0</points_possible>
          <criteria>
            <criterion>
              <description>Criterion Name</description>
              <long_description>Detailed criterion description</long_description>
              <points>25.0</points>
              <ratings>
                <rating>
                  <description>Rating Level Name</description>
                  <long_description>What this level looks like</long_description>
                  <points>25.0</points>
                </rating>
              </ratings>
            </criterion>
          </criteria>
        </rubric>
      </rubrics>
    """
    rubrics = []
    xml = data.get('rubrics', '')
    if not xml:
        print("   Rubrics: rubrics.xml not found or empty")
        return rubrics

    print(f"   Rubrics: raw XML is {len(xml):,} chars")

    # ── Parse with ElementTree (robust, handles any whitespace/formatting) ──
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        print(f"   Rubrics: XML parse error: {e}")
        print(f"   Rubrics: first 300 chars: {xml[:300]}")
        return rubrics

    # Handle both cases: root IS <rubrics> or root contains <rubrics>
    if root.tag == 'rubrics':
        rubric_elements = root.findall('rubric')
    else:
        rubric_elements = root.findall('.//rubric')

    print(f"   Rubrics: found {len(rubric_elements)} <rubric> element(s)")

    for rubric_el in rubric_elements:
        title = (rubric_el.findtext('title') or 'Untitled Rubric').strip()
        points = (rubric_el.findtext('points_possible') or '').strip()

        criteria = []
        criteria_el = rubric_el.find('criteria')
        if criteria_el is not None:
            for crit_el in criteria_el.findall('criterion'):
                crit_name = (crit_el.findtext('description') or 'Unnamed').strip()
                crit_desc = (crit_el.findtext('long_description') or '').strip()
                crit_pts  = (crit_el.findtext('points') or '?').strip()

                ratings = []
                ratings_el = crit_el.find('ratings')
                if ratings_el is not None:
                    for rat_el in ratings_el.findall('rating'):
                        r_name = (rat_el.findtext('description') or '').strip()
                        r_desc = (rat_el.findtext('long_description') or '').strip()
                        r_pts  = (rat_el.findtext('points') or '').strip()
                        if r_name or r_desc:
                            ratings.append({
                                'name': r_name,
                                'description': r_desc,
                                'points': r_pts,
                            })

                criteria.append({
                    'name': crit_name,
                    'description': crit_desc,
                    'points': crit_pts,
                    'ratings': ratings,
                })

        rubrics.append({
            'title': title,
            'points': points,
            'criteria': criteria,
        })

    total_criteria = sum(len(r['criteria']) for r in rubrics)
    total_ratings = sum(len(c['ratings']) for r in rubrics for c in r['criteria'])
    print(f"   Rubrics: extracted {len(rubrics)} rubric(s), "
          f"{total_criteria} criteria, {total_ratings} rating levels")

    return rubrics



# ─────────────────────────────────────────────────────────────
#  DOCUMENT BUILDER
# ─────────────────────────────────────────────────────────────

def build_course_dossier(data, identity, modules, grading_groups, rubrics):
    """
    Build the Course Dossier — a complete, faithful extraction of the
    Canvas course content organized for MeMe's QM consultation.

    No analysis. No judgments. Just data.
    """
    today = datetime.now().strftime('%Y-%m-%d')
    stats = data.get('publish_stats', {})
    syl_text = data.get('syllabus_text', '')

    L = [
        '# CeCe Course Dossier',
        f'> Extracted {today} from `{data["file_name"]}`',
        '> This document contains the complete published content of the Canvas course.',
        '> It is organized for MeMe to conduct a QM 7th Edition needs analysis.',
        '> CeCe does not evaluate — she extracts. All analysis is performed by MeMe.',
        '',
        '---',
    ]

    # ── Section 1: Course Identity ──
    L += [
        '', '## SECTION 1: COURSE IDENTITY', '',
        '| Field | Value |', '|-------|-------|',
        f'| Course Title | {identity["title"]} |',
        f'| Course Code  | {identity["code"]} |',
        f'| Delivery Mode | {identity["modality"]} |',
        f'| Start Date | {identity["start_date"]} |',
        f'| End Date   | {identity["end_date"]} |',
        f'| Published Modules | {len(modules)} |',
        f'| Published Content Pages | {stats.get("wiki_published",0)} |',
        f'| Published Assignments | {stats.get("assign_published",0)} |',
        f'| Published Quizzes | {stats.get("assess_published",0)} |',
        f'| LTI / External Tools | {len(data["lti_tools"])} |',
        f'| Unpublished Pages | {stats.get("wiki_unpublished",0)} |',
        f'| Unpublished Assignments | {stats.get("assign_unpublished",0)} |',
        f'| Syllabus Provided | {"Yes (" + str(len(syl_text)) + " chars)" if syl_text else "No"} |',
        f'| Generated | {today} |',
        '', '---',
    ]

    # ── Section 2: Publish Status Detail ──
    L += [
        '', '## SECTION 2: PUBLISH STATUS',
        '> Items below were detected in the export but are NOT included in this dossier.',
        '> They were either unpublished or not linked in any published module.', '',
    ]
    if data['wiki_unpublished']:
        L.append('**Unpublished Pages:**')
        for p in sorted(data['wiki_unpublished']):
            L.append(f'- {p}')
        L.append('')
    if data['assignments_unpub']:
        L.append('**Unpublished Assignments:**')
        for a in data['assignments_unpub']:
            L.append(f'- {a}')
        L.append('')
    if not data['wiki_unpublished'] and not data['assignments_unpub']:
        L.append('*All detected content is published.*')
    L += ['', '---']

    # ── Section 3: Syllabus ──
    L += [
        '', '## SECTION 3: SYLLABUS',
        '> Instructor-provided syllabus text. MeMe uses this as a comparison',
        '> tool against course content — the course is the authority.', '',
    ]
    if syl_text:
        L += [syl_text, '']
    else:
        L += [
            '*Syllabus was not provided with this dossier.*',
            '*MeMe should request the syllabus from the instructor before*',
            '*evaluating GS 1 and GS 2 standards.*',
            '',
        ]
    L += ['---']

    # ── Section 4: Module & Week Structure ──
    L += [
        '', '## SECTION 4: MODULE & WEEK STRUCTURE',
        '> Every published module with its items, organized as they appear in Canvas.',
        '> Week headers (if present) are noted.', '',
    ]
    if not modules:
        L.append('*No published modules found.*')
    else:
        for i, mod in enumerate(modules, 1):
            weeks = mod.get('weeks_in_module', [])
            week_note = f' ({", ".join(weeks)})' if weeks else ''
            L += [f'### Module {i}: {mod["title"]}{week_note}', '']

            if mod['items']:
                L += ['| # | Item | Type | Week |', '|---|------|------|------|']
                for j, item in enumerate(mod['items'], 1):
                    itype = item.get('type', '').replace('WikiPage', 'Page') \
                                                 .replace('Assignment', 'Assignment') \
                                                 .replace('DiscussionTopic', 'Discussion') \
                                                 .replace('Quizzes::Quiz', 'Quiz') \
                                                 .replace('ContextModuleSubHeader', 'Header') \
                                                 .replace('ExternalUrl', 'External Link') \
                                                 .replace('ContextExternalTool', 'LTI Tool')
                    week = item.get('week', '') or ''
                    title = item['title'].replace('|', '/')
                    L.append(f'| {j} | {title} | {itype} | {week} |')
                L.append('')
            else:
                L.append('*No items in this module.*')
                L.append('')
    L += ['---']

    # ── Section 5: Grading Structure ──
    L += [
        '', '## SECTION 5: GRADING STRUCTURE',
        '> Assignment groups and their percentage weights as configured in Canvas.', '',
    ]
    if not grading_groups:
        L.append('*No grading structure found in the export.*')
    else:
        L += ['| Group Name | Weight (%) |', '|------------|-----------|']
        total_weight = 0.0
        for g in grading_groups:
            L.append(f'| {g["name"]} | {g["weight"]}% |')
            try:
                total_weight += float(g['weight'])
            except ValueError:
                pass
        L += [
            f'| **Total** | **{total_weight:.1f}%** |', '',
        ]
        if abs(total_weight - 100) > 1:
            L.append(f'*Note: Weights sum to {total_weight:.1f}%, not 100%.*')
    L += ['', '---']

    # ── Section 6: Assignment Inventory ──
    L += [
        '', '## SECTION 6: ASSIGNMENT INVENTORY',
        '> Every published assignment with its full instructions, points, due date,',
        '> and submission type. This is the primary data MeMe uses for GS 3 evaluation.', '',
    ]
    if not data['assignments']:
        L.append('*No published assignments found.*')
    else:
        for name, det in data['assignments'].items():
            L += [
                f'### {name}', '',
                f'**Points:** {det["points"]} | **Due:** {det["due_date"]} | **Submission:** {det["sub_type"]}',
                '',
                '**Instructions:**',
                det['instructions'],
                '', '---', '',
            ]
    L += ['---']

    # ── Section 7: Assessments / Quizzes ──
    L += [
        '', '## SECTION 7: ASSESSMENTS / QUIZZES',
        '> Quiz and assessment content extracted from QTI XML.', '',
    ]
    if not data['assessments']:
        L.append('*No published assessments/quizzes found.*')
    else:
        for name, content in data['assessments'].items():
            L += [f'### {name}', '', content, '', '---', '']
    L += ['---']

    # ── Section 8: Rubrics (FULL DETAIL) ──
    L += [
        '', '## SECTION 8: RUBRICS',
        '> Complete rubric extraction including every criterion and every rating level.',
        '> MeMe uses this to evaluate QM Standard 3.3 (specific evaluation criteria).', '',
    ]
    if not rubrics:
        L.append('*No rubrics found in the export. This is a significant gap for QM Standard 3.3.*')
    else:
        for rub in rubrics:
            pts_note = f' ({rub["points"]} pts total)' if rub.get('points') else ''
            L += [f'### {rub["title"]}{pts_note}', '']

            for crit in rub['criteria']:
                crit_desc = f' — {crit["description"]}' if crit.get('description') else ''
                L.append(f'**Criterion: {crit["name"]}** ({crit["points"]} pts){crit_desc}')
                L.append('')

                if crit['ratings']:
                    L += ['| Rating | Points | Description |',
                          '|--------|--------|-------------|']
                    for rating in crit['ratings']:
                        desc = rating['description'].replace('|', '/').replace('\n', ' ')
                        L.append(f'| {rating["name"]} | {rating["points"]} | {desc} |')
                    L.append('')
                else:
                    L.append('*No rating levels defined for this criterion.*')
                    L.append('')

            L += ['---', '']
    L += ['---']

    # ── Section 9: Instructional Materials ──
    L += [
        '', '## SECTION 9: INSTRUCTIONAL MATERIALS',
        '> Published media and resource page titles.', '',
    ]
    if data['wiki_titles']:
        for t in sorted(data['wiki_titles']):
            L.append(f'- {t}')
    else:
        L.append('*No media/resource pages identified.*')
    L += ['', '---']

    # ── Section 10: LTI Tools & External Integrations ──
    L += [
        '', '## SECTION 10: LTI TOOLS & EXTERNAL INTEGRATIONS',
        '> External tools detected in the course export.', '',
    ]
    if data['lti_tools']:
        L += ['| Tool Name | Launch URL |', '|-----------|-----------|']
        for tool in data['lti_tools']:
            L.append(f'| {tool["name"]} | {tool.get("url", "N/A")} |')
    else:
        L.append('*No LTI tools detected. External tools may still exist as links in page content.*')
    L += ['', '---']

    # ── Section 11: Full Course Page Content ──
    L += [
        '', '## SECTION 11: COURSE PAGE CONTENT',
        '> Full text of every published content page.',
        '> MeMe reads this to evaluate nearly every QM standard.', '',
    ]
    for page_name, content in data['wiki_full'].items():
        L += [f'### {page_name}', '', content, '', '---', '']
    L += ['---']

    # ── Section 12: Notes for MeMe ──
    L += [
        '', '## SECTION 12: NOTES FOR MEME', '',
    ]
    notes = []
    if not syl_text:
        notes.append('The syllabus was not provided. Request it from the instructor before '
                      'evaluating GS 1 and GS 2 standards.')
    else:
        notes.append(f'Syllabus provided ({len(syl_text):,} characters) — see Section 3.')
    if not rubrics:
        notes.append('No rubrics were found in the export. This is a critical gap '
                      'for QM Standard 3.3. Ask the instructor if rubrics exist outside Canvas.')
    else:
        total_criteria = sum(len(r['criteria']) for r in rubrics)
        total_with_ratings = sum(
            1 for r in rubrics for c in r['criteria'] if c['ratings']
        )
        notes.append(f'{len(rubrics)} rubric(s) extracted with {total_criteria} total criteria. '
                      f'{total_with_ratings} criteria have detailed rating levels.')
    if len(modules) == 0:
        notes.append('No published modules found. The course may be in draft state.')
    unpub_assign = stats.get('assign_unpublished', 0)
    unpub_pages  = stats.get('wiki_unpublished', 0)
    if unpub_assign > 0 or unpub_pages > 0:
        notes.append(f'{unpub_pages} page(s) and {unpub_assign} assignment(s) were '
                      f'unpublished and excluded from this dossier.')
    if not data['assignments']:
        notes.append('No published assignments found.')
    if not data['assessments']:
        notes.append('No quizzes/assessments found.')
    for note in notes:
        L.append(f'- {note}')
    L += ['', '---']

    # ── Appendix: QM 7th Edition Reference ──
    L += [
        '', '## APPENDIX: QM 7TH EDITION RUBRIC REFERENCE',
        '> Condensed reference for all 44 Specific Review Standards.',
        '> MeMe uses this to evaluate the course regardless of which AI platform is used.',
        '> Weight: Essential (3 pts) = required for certification;',
        '> Very Important (2 pts) = strongly recommended; Important (1 pt) = recommended.', '',
    ]
    L += _qm_reference_appendix()

    L += [
        '', '---',
        f'*CeCe Course Dossier v5.0 — Generated {today}*',
    ]

    return '\n'.join(L)


def _qm_reference_appendix():
    """Condensed QM 7th Edition reference with all 44 standards."""
    L = []

    standards = [
        ('### GS 1: Course Overview and Introduction (16 pts)', [
            ('1.1', 'Essential (3)', 'Instructions make clear how to get started and where to find various course components.'),
            ('1.2', 'Essential (3)', 'Learners are introduced to the purpose and structure of the course.'),
            ('1.3', 'Very Important (2)', 'Communication guidelines for the course are clearly stated.'),
            ('1.4', 'Very Important (2)', 'Course and institutional policies with which the learner is expected to comply are clearly stated.'),
            ('1.5', 'Very Important (2)', 'Minimum technology requirements and digital skills are clearly stated.'),
            ('1.6', 'Important (1)', 'Technical and digital skills expected of the learner are clearly stated.'),
            ('1.7', 'Important (1)', 'Required knowledge and/or competencies are clearly stated.'),
            ('1.8', 'Important (1)', 'The self-introduction by the instructor is professional and available online.'),
            ('1.9', 'Important (1)', 'Learners have the opportunity to introduce themselves.'),
        ]),
        ('### GS 2: Learning Objectives — Competencies (15 pts, ALL Essential)', [
            ('2.1', 'Essential (3)', 'The course-level learning objectives describe outcomes that are measurable.'),
            ('2.2', 'Essential (3)', 'The module/unit-level learning objectives describe outcomes that are measurable.'),
            ('2.3', 'Essential (3)', 'Learning objectives are clearly stated and consistent throughout the course.'),
            ('2.4', 'Essential (3)', 'The relationship between objectives and learning activities is clearly stated.'),
            ('2.5', 'Essential (3)', 'The learning objectives are suited to the level of the course.'),
        ]),
        ('### GS 3: Assessment and Measurement (14 pts)', [
            ('3.1', 'Essential (3)', 'The assessments measure the stated learning objectives.'),
            ('3.2', 'Essential (3)', 'The course grading policy is stated clearly.'),
            ('3.3', 'Essential (3)', 'Specific and descriptive criteria are provided for the evaluation of learners\' work.'),
            ('3.4', 'Very Important (2)', 'The course provides multiple opportunities to track learning progress.'),
            ('3.5', 'Very Important (2)', 'The types of assessments selected measure the stated objectives and are sequenced and varied.'),
            ('3.6', 'Important (1)', 'The course assessments provide guidance on academic integrity.'),
        ]),
        ('### GS 4: Instructional Materials (12 pts)', [
            ('4.1', 'Essential (3)', 'The instructional materials contribute to the achievement of the stated learning objectives.'),
            ('4.2', 'Essential (3)', 'The relationship between the use of instructional materials and the learning activities is clearly explained.'),
            ('4.3', 'Very Important (2)', 'The course models academic integrity through proper citations and references.'),
            ('4.4', 'Very Important (2)', 'The instructional materials represent current thinking in the discipline.'),
            ('4.5', 'Very Important (2)', 'A variety of instructional materials is used in the course.'),
        ]),
        ('### GS 5: Learning Activities and Learner Interaction (11 pts)', [
            ('5.1', 'Essential (3)', 'The learning activities promote the achievement of the stated learning objectives.'),
            ('5.2', 'Essential (3)', 'Learning activities provide opportunities for interaction that support active learning.'),
            ('5.3', 'Essential (3)', 'The instructor\'s plan for classroom response time and feedback is clearly stated.'),
            ('5.4', 'Very Important (2)', 'The requirements for learner interaction are clearly articulated.'),
        ]),
        ('### GS 6: Course Technology (7 pts)', [
            ('6.1', 'Essential (3)', 'The tools used in the course support the learning objectives.'),
            ('6.2', 'Very Important (2)', 'Course tools promote learner engagement and active learning.'),
            ('6.3', 'Important (1)', 'A variety of technology tools are used in the course.'),
            ('6.4', 'Important (1)', 'The course provides learners with information on protecting their data and privacy.'),
        ]),
        ('### GS 7: Learner Support (10 pts)', [
            ('7.1', 'Essential (3)', 'The course instructions articulate or link to the institution\'s technical support.'),
            ('7.2', 'Essential (3)', 'Course instructions articulate or link to the institution\'s accessibility policies and services.'),
            ('7.3', 'Essential (3)', 'Course instructions articulate or link to the institution\'s academic support services.'),
            ('7.4', 'Important (1)', 'Course instructions articulate or link to the institution\'s student services.'),
        ]),
        ('### GS 8: Accessibility and Usability (16 pts)', [
            ('8.1', 'Essential (3)', 'Course navigation facilitates ease of use.'),
            ('8.2', 'Essential (3)', 'The course design facilitates readability and usability.'),
            ('8.3', 'Essential (3)', 'Text in the course is accessible.'),
            ('8.4', 'Very Important (2)', 'Images in the course are accessible.'),
            ('8.5', 'Very Important (2)', 'Video and audio content in the course are accessible.'),
            ('8.6', 'Very Important (2)', 'Multimedia in the course is accessible.'),
            ('8.7', 'Important (1)', 'Vendor accessibility information is provided.'),
        ]),
    ]

    for header, stds in standards:
        L += [header, '',
              '| SRS | Weight | Standard |', '|-----|--------|----------|']
        for sid, weight, text in stds:
            L.append(f'| {sid} | {weight} | {text} |')
        L += ['', '']

    L += [
        '**Scoring:** A course must meet ALL Essential (3-point) standards and',
        'achieve at least 85% of total possible points (86 of 101) to be QM-certified.',
        'No Essential standard may be scored as Not Met.',
        '',
    ]

    return L


# ─────────────────────────────────────────────────────────────
#  MAIN (CLI mode)
# ─────────────────────────────────────────────────────────────

def main():
    print('\n' + '='*60)
    print('  CeCe Course Extraction Agent v5')
    print('='*60)

    if len(sys.argv) < 2:
        print('\nUsage:  python analyze.py your-course.imscc')
        print('        python analyze.py your-course.imscc --output my-dossier.md')
        sys.exit(1)

    imscc_path = sys.argv[1]
    if not os.path.exists(imscc_path):
        print(f'\n❌  File not found: {imscc_path}')
        sys.exit(1)

    # Optional syllabus from --syllabus flag
    syl_text = ''
    if '--syllabus' in sys.argv:
        idx = sys.argv.index('--syllabus') + 1
        if idx < len(sys.argv):
            syl_path = sys.argv[idx]
            if os.path.exists(syl_path):
                with open(syl_path, 'r', encoding='utf-8', errors='ignore') as f:
                    syl_text = f.read()
                print(f'Syllabus loaded: {syl_path} ({len(syl_text):,} chars)')

    data     = read_imscc(imscc_path, syllabus_text=syl_text)
    identity = extract_course_identity(data)
    modules  = extract_modules(data)
    grading  = extract_grading_structure(data)
    rubrics  = extract_rubrics(data)
    document = build_course_dossier(data, identity, modules, grading, rubrics)

    # Determine output path
    if '--output' in sys.argv:
        idx = sys.argv.index('--output') + 1
        out_path = sys.argv[idx] if idx < len(sys.argv) else None
    else:
        base = os.path.splitext(os.path.basename(imscc_path))[0]
        out_path = f'{base}_dossier.md'

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(document)

    print(f'\n✅ Course Dossier saved to: {out_path}')
    print(f'   Total length: {len(document):,} characters')
    print(f'\nNext step: Paste this dossier into MeMe for QM consultation.')


if __name__ == '__main__':
    main()
