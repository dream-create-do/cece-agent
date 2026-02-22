"""
analyze.py — CeCe Course Analysis Agent v4
Changes from v3:
- Only analyzes PUBLISHED content (skips unpublished/draft items)
- Reports published vs unpublished counts for transparency
- Detects publish state from module item workflow_state and assignment XML

Usage:
    python analyze.py your-course.imscc
    python analyze.py your-course.imscc --output my-analysis.md
"""

import zipfile
import os
import re
import sys
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

QM_STANDARDS = {
    '1.1': 'Course Overview & Introduction present',
    '1.2': 'Learner expectations clearly stated',
    '2.1': 'Course-level objectives present and measurable',
    '2.2': 'Module-level objectives present',
    '2.3': 'Objectives use measurable action verbs',
    '3.1': 'Assessments align to stated objectives',
    '3.2': 'Variety of assessment types used',
    '4.1': 'Instructional materials align to objectives',
    '5.1': 'Learning activities promote engagement',
    '5.2': 'Learner interaction opportunities present',
    '6.1': 'Technology requirements stated',
    '7.1': 'Accessibility considerations present',
    '8.1': 'Course navigation is clear and consistent',
}

BLOOMS_VERBS = {
    'Remember':   ['define','list','recall','identify','name','label','match',
                   'memorize','recognize','repeat','reproduce','state'],
    'Understand': ['explain','summarize','classify','compare','discuss','interpret',
                   'paraphrase','predict','report','restate','review','translate'],
    'Apply':      ['use','demonstrate','solve','implement','execute','apply',
                   'calculate','complete','illustrate','modify','operate','show'],
    'Analyze':    ['differentiate','examine','organize','attribute','deconstruct',
                   'analyze','contrast','distinguish','inspect','question'],
    'Evaluate':   ['judge','critique','justify','argue','assess','appraise',
                   'defend','evaluate','prioritize','rank','recommend','support'],
    'Create':     ['design','construct','develop','formulate','produce','assemble',
                   'build','compose','create','devise','generate','plan','write'],
}


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


def detect_blooms_level(text):
    level_order = ['Remember','Understand','Apply','Analyze','Evaluate','Create']
    found = [lvl for lvl, verbs in BLOOMS_VERBS.items()
             if any(re.search(r'\b' + v + r'\b', text.lower()) for v in verbs)]
    return max(found, key=lambda l: level_order.index(l)) if found else 'Unclear'


def detect_iframe_syllabus(raw_html):
    """
    Checks if a syllabus file is just an iframe/embed rather than readable text.
    Returns (is_embed, all_external_links, plain_text)
    """
    srcs  = re.findall(r'src=["\']([^"\']+)["\']', raw_html)
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', raw_html)
    text  = strip_html(raw_html)
    external = [u for u in srcs + hrefs
                if u.startswith('http') and 'canvas' not in u.lower() and u != '#']
    is_embed = len(text) < 150
    return is_embed, external, text


def detect_lti_syllabus(course_settings_xml, lti_files, all_files, zip_handle):
    """
    Checks if the syllabus is delivered via an LTI tool (e.g. Simple Syllabus,
    Concourse, etc.) by inspecting the Canvas tab configuration and LTI resource links.
    Returns (found, tool_name, description)
    """
    # Known LTI syllabus tool identifiers and display names
    SYLLABUS_TOOLS = [
        ('simplesyllabus',  'Simple Syllabus'),
        ('simple_syllabus', 'Simple Syllabus'),
        ('concourse',       'Concourse Syllabus'),
        ('syllabi',         'Syllabi'),
        ('coursetool',      'Course Tool Syllabus'),
    ]

    # Check tab configuration in course_settings.xml for external tool names
    tab_config = re.search(r'<tab_configuration>(\[.*?\])</tab_configuration>',
                           course_settings_xml, re.DOTALL)
    if tab_config:
        config_str = tab_config.group(1).lower()
        for key, name in SYLLABUS_TOOLS:
            if key in config_str:
                return True, name, f'Detected as Canvas navigation tab via LTI'

    # Check lti_resource_links files for syllabus-related tool names
    for lti_path in lti_files:
        try:
            raw = zip_handle.read(lti_path).decode('utf-8', errors='ignore').lower()
            for key, name in SYLLABUS_TOOLS:
                if key in raw:
                    return True, name, f'Detected in LTI resource link: {lti_path}'
            # Also check for generic "syllabus" in LTI tool title
            title_m = re.search(r'<title>([^<]*syllabus[^<]*)</title>', raw, re.IGNORECASE)
            if title_m:
                tool_name = strip_html(title_m.group(1)).strip().title()
                return True, tool_name, f'Detected in LTI resource link: {lti_path}'
        except Exception:
            pass

    # Check context.xml for external tool references
    if 'course_settings/context.xml' in all_files:
        try:
            raw = zip_handle.read('course_settings/context.xml').decode('utf-8', errors='ignore').lower()
            for key, name in SYLLABUS_TOOLS:
                if key in raw:
                    return True, name, 'Detected in context.xml'
        except Exception:
            pass

    return False, None, None
    srcs  = re.findall(r'src=["\']([^"\']+)["\']', raw_html)
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', raw_html)
    text  = strip_html(raw_html)
    external = [u for u in srcs + hrefs
                if u.startswith('http') and 'canvas' not in u.lower() and u != '#']
    return len(text) < 150, external, text


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

    Strategy:
    1. Parse module items → collect {identifierref: workflow_state}
    2. Parse imsmanifest → build {identifier: href}
    3. Cross-reference: if identifierref is active → its href is published
    """
    # Step 1 — module item publish states
    item_states = {}   # identifierref → 'active' | 'unpublished'
    item_blocks = re.split(r'<item\s+identifier=[^>]+>', module_meta_xml)[1:]
    for block in item_blocks:
        ref_m   = re.search(r'<identifierref>(.+?)</identifierref>', block, re.DOTALL)
        state_m = re.search(r'<workflow_state>(.+?)</workflow_state>', block, re.DOTALL)
        if ref_m:
            ref   = ref_m.group(1).strip()
            state = state_m.group(1).strip() if state_m else 'active'
            # If same page appears in multiple modules keep 'active' if any are active
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

def read_imscc(file_path, file_bytes=None):
    """
    Accepts either:
      file_path: str  — path to a .imscc file on disk (GUI / CLI mode)
      file_bytes: bytes — in-memory content (Streamlit upload mode)
    When file_bytes is provided, file_path is used only for display.
    """
    import io
    display_name = os.path.basename(file_path) if file_path else "uploaded file"
    print(f"\n📂 Opening: {display_name}")
    zip_source = io.BytesIO(file_bytes) if file_bytes is not None else file_path

    data = {
        'file_name':          display_name,
        'all_files':          [],
        'syllabus_raw':        '',
        'syllabus_text':       '',
        'syllabus_is_embed':   False,
        'syllabus_links':      [],
        'syllabus_source':     'canvas_tab',
        'syllabus_lti_tool':   None,    # name of LTI tool if syllabus is LTI-delivered
        'course_settings':    '',
        'assignment_groups':  '',
        'module_meta':        '',
        'rubrics':            '',
        'manifest':           '',
        'wiki_full':          {},        # published content pages
        'wiki_titles':        [],        # published media pages (titles only)
        'wiki_unpublished':   [],        # unpublished — noted but not analyzed
        'assignments':        {},        # published assignments
        'assignments_unpub':  [],        # unpublished assignment names
        'assessments':        {},
        'lti_tools':          [],
        'publish_stats':      {},        # summary counts
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
        # Step 1: Check the Canvas syllabus tab file
        if 'course_settings/syllabus.html' in files:
            raw = z.read('course_settings/syllabus.html').decode('utf-8', errors='ignore')
            data['syllabus_raw'] = raw
            is_embed, links, text = detect_iframe_syllabus(raw)
            data['syllabus_is_embed'] = is_embed
            data['syllabus_links']    = links
            data['syllabus_text']     = text

        # Step 2: If Canvas tab is empty or just an embed, look for syllabus wiki pages.
        # Instructors often build the syllabus as a standalone wiki page instead of
        # using the Canvas syllabus tab. These pages may not live inside any module.
        # We search for them explicitly regardless of publish state since a syllabus
        # is always student-facing by nature.
        syllabus_tab_is_empty = len(data['syllabus_text'].strip()) < 50

        if syllabus_tab_is_empty:
            syllabus_wiki_candidates = [
                f for f in files
                if f.startswith('wiki_content/')
                and f.endswith('.html')
                and 'syllabus' in f.lower()
            ]
            # Also check for common standalone syllabus page names
            syllabus_name_patterns = ['syllabus', 'course-information',
                                      'course-policies', 'course-overview']
            for f in files:
                if (f.startswith('wiki_content/') and f.endswith('.html')
                        and f not in syllabus_wiki_candidates
                        and any(p in f.lower() for p in syllabus_name_patterns)):
                    syllabus_wiki_candidates.append(f)

            if syllabus_wiki_candidates:
                combined_syllabus = []
                for page_path in syllabus_wiki_candidates:
                    try:
                        raw   = z.read(page_path).decode('utf-8', errors='ignore')
                        clean = strip_html(raw).strip()
                        if len(clean) > 100:  # ignore near-empty pages
                            page_name = page_path.replace('wiki_content/','').replace('.html','')
                            combined_syllabus.append(f"[Source: {page_name}]\n{clean}")
                            print(f"   Syllabus wiki page found: {page_path}")
                    except Exception:
                        pass

                if combined_syllabus:
                    data['syllabus_text']     = '\n\n'.join(combined_syllabus)
                    data['syllabus_is_embed'] = False
                    data['syllabus_source']   = 'wiki_page'

        # ── LTI tools ──
        data['lti_tools'] = [f for f in files if f.startswith('lti_resource_links/')]

        # ── Check for LTI-delivered syllabus BEFORE reading the Canvas tab ──
        lti_syllabus_found, lti_tool_name, lti_description = detect_lti_syllabus(
            data['course_settings'], data['lti_tools'], files, z
        )
        if lti_syllabus_found:
            data['syllabus_lti_tool'] = lti_tool_name
            data['syllabus_source']   = 'lti_tool'
            print(f"   Syllabus: LTI tool detected — {lti_tool_name}")

        # ── Build published file set from module metadata + manifest ──
        published_hrefs, item_states, id_to_href = build_published_file_set(
            data['module_meta'], data['manifest']
        )

        # ── Wiki pages — filter by publish state ──
        wiki_files = [f for f in files
                      if f.startswith('wiki_content/') and f.endswith('.html')]
        print(f"   Wiki/content pages (total): {len(wiki_files)}")

        wiki_pub   = 0
        wiki_unpub = 0

        for page_path in wiki_files:
            page_name = page_path.replace('wiki_content/', '').replace('.html', '')

            # Determine publish state
            # A page is published if it appears as an active item in any module.
            # Pages not referenced in any module are treated as unpublished/unused.
            if page_path in published_hrefs:
                published = True
            elif not item_states:
                # Fallback: if we couldn't parse module metadata at all, include everything
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

        # ── Assignments — filter by workflow_state in assignment_settings.xml ──
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

                # Check publish state from assignment_settings.xml
                settings_path = f"{folder_id}/assignment_settings.xml"
                published     = True   # default to published if no settings found
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

                # Read instructions
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

        # ── Store publish stats for the report ──
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
#  EXTRACTORS  (unchanged from v3)
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

        # Skip unpublished modules entirely
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

                # Skip unpublished items
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
    rubrics = []
    xml = data.get('rubrics', '')
    if not xml:
        return rubrics
    for block in re.split(r'<rubric\s+identifier=[^>]+>', xml)[1:]:
        t_m   = re.search(r'<title>(.+?)</title>', block, re.DOTALL)
        title = strip_html(t_m.group(1)).strip() if t_m else 'Untitled Rubric'
        criteria = []
        for cb in re.split(r'<criterion\s+identifier=[^>]+>', block)[1:]:
            d_m = re.search(r'<description>(.+?)</description>', cb, re.DOTALL)
            p_m = re.search(r'<points>(.+?)</points>', cb, re.DOTALL)
            if d_m:
                criteria.append(f"{strip_html(d_m.group(1)).strip()} "
                                 f"({p_m.group(1).strip() if p_m else '?'} pts)")
        rubrics.append({'title': title, 'criteria': criteria})
    return rubrics


def extract_learning_objectives(data, modules):
    objectives  = []
    found_texts = set()
    priority_keys = ['objective','overview','syllabus','welcome','introduction',
                     'getting-started','the-right-stuff','activities','start-here']
    search_pages = {k: v for k, v in data.get('wiki_full', {}).items()
                    if any(p in k.lower() for p in priority_keys)}
    for mod in modules:
        mod_words = [w for w in re.split(r'[\s|]+', mod['title'].lower()) if len(w) > 3]
        for page_name, content in data.get('wiki_full', {}).items():
            if any(w in page_name.lower() for w in mod_words):
                search_pages[page_name] = content
    patterns = [
        r'(?:students\s+will|you\s+will|learners\s+will)\s+([^.!?\n]{15,200})[.!?]',
        r'by\s+the\s+end\s+of\s+(?:this\s+)?(?:module|week|course|unit)[^,]*,?\s*'
        r'(?:you\s+will\s+be\s+able\s+to|you\s+will|students\s+will)\s*:?\s*([^.!?\n]{15,200})',
        r'upon\s+completion[^,]*,\s*([^.!?\n]{15,200})[.!?]',
        r'(?:clo|slo|lo|learning\s+objective)\s*[-:#]?\s*\d*\s*[:.]\s*([^.\n]{15,200})',
    ]
    for page_name, content in search_pages.items():
        for pattern in patterns:
            for match in re.findall(pattern, content, re.IGNORECASE | re.DOTALL):
                if isinstance(match, tuple):
                    match = ' '.join(m for m in match if m)
                clean = re.sub(r'\s+', ' ', match).strip()
                if len(clean) > 20 and clean not in found_texts:
                    found_texts.add(clean)
                    objectives.append({'text': clean[:200],
                                       'blooms': detect_blooms_level(clean),
                                       'source': page_name})
    return objectives[:25]


# ─────────────────────────────────────────────────────────────
#  QM / UDL PRE-CHECK
# ─────────────────────────────────────────────────────────────

def run_qm_precheck(data, modules, grading_groups, objectives):
    results     = {}
    all_wiki    = ' '.join(data.get('wiki_full', {}).values()).lower()
    all_assign  = ' '.join(a['instructions'] for a in
                           data.get('assignments', {}).values()).lower()
    all_content = all_wiki + ' ' + all_assign

    def check(key, met_c, met_n, par_c, par_n, fail_n):
        if met_c:   results[key] = ('✅ Met', met_n)
        elif par_c: results[key] = ('⚠️ Partially Met', par_n)
        else:       results[key] = ('❌ Not Met', fail_n)

    has_welcome = any(any(w in k.lower() for w in
                          ['welcome','introduction','overview','the-right-stuff','start-here'])
                      for k in data['wiki_full'])
    has_contact = any(w in all_content for w in ['instructor','professor','office hours','email'])
    check('1.1', has_welcome and has_contact, 'Welcome/overview and instructor info detected',
          has_welcome or has_contact, 'Welcome page or contact info may be incomplete',
          'No clear overview or instructor info')

    has_expect = any(w in all_content for w in
                     ['netiquette','expectation','participation','late policy',
                      'academic integrity','community'])
    check('1.2', has_expect and len(modules)>0, 'Expectations and module structure present',
          has_expect or len(modules)>0, 'Partial expectations found',
          'Learner expectations not clearly articulated')

    n = len(objectives)
    check('2.1', n>=3, f'{n} objectives detected', n>=1,
          f'Only {n} objective(s) clearly detected',
          'No objectives detected — likely in external syllabus')

    total_mods = len(modules)
    if total_mods == 0:
        results['2.2'] = ('🔍 Needs Human Review', 'Module structure not parseable')
    else:
        obj_kw = ['objective','by the end','you will','students will','upon completion']
        mods_with_obj = 0
        for mod in modules:
            mod_words = [w for w in re.split(r'[\s|]+', mod['title'].lower()) if len(w)>3]
            mod_content = ''
            for page_name, content in data['wiki_full'].items():
                if any(w in page_name.lower() for w in mod_words):
                    mod_content += content.lower()
            if any(k in mod_content for k in obj_kw):
                mods_with_obj += 1
        pct = mods_with_obj / total_mods
        check('2.2', pct>=0.7, f'Objectives in ~{mods_with_obj}/{total_mods} modules',
              pct>0, f'Only ~{mods_with_obj}/{total_mods} modules have clear objectives',
              'Module objectives not detected')

    if not objectives:
        results['2.3'] = ('🔍 Needs Human Review', 'No objectives to evaluate')
    else:
        unclear = sum(1 for o in objectives if o['blooms']=='Unclear')
        check('2.3', unclear==0, "All objectives use Bloom's verbs",
              unclear < len(objectives)//2, f'{unclear}/{len(objectives)} lack clear verbs',
              f'{unclear}/{len(objectives)} use vague language')

    has_rubrics = len(data.get('rubrics','')) > 100
    has_assigns = len(data.get('assignments',{})) > 0
    check('3.1', has_rubrics and has_assigns, 'Assignments and rubrics both present',
          has_assigns, 'Assignments found but rubrics minimal', 'Limited assessment data')

    types = []
    if any(w in all_assign for w in ['discussion','respond','reply','post']): types.append('Discussion')
    if data.get('assessments'): types.append('Quiz/Assessment')
    if any(w in all_assign for w in ['essay','paper','write','reflection','journal']): types.append('Written/Reflective')
    if any(w in all_assign for w in ['project','present','create','design','build','produce']): types.append('Project/Creative')
    if any(w in all_assign for w in ['peer','classmate']): types.append('Peer Activity')
    check('3.2', len(types)>=3, f'Types: {", ".join(types)}',
          len(types)==2, f'Only: {", ".join(types)}', 'Very limited variety')

    mc = len(data.get('wiki_titles',[]))
    cc = len(data.get('wiki_full',{}))
    check('4.1', mc>0 and cc>0, f'{mc} media items and {cc} content pages',
          cc>0, 'Content pages found but media may be limited', 'Material alignment unclear')

    has_disc   = any(w in all_content for w in ['discussion','respond','reply'])
    has_refl   = any(w in all_content for w in ['reflect','journal'])
    has_active = any(w in all_content for w in ['create','analyze','design','solve','apply','build'])
    ac = sum([has_disc, has_refl, has_active])
    check('5.1', ac>=3, 'Discussion, reflection, and active tasks all detected',
          ac==2, "Some active learning present",
          'Limited active learning detected')

    has_peer = any(w in all_content for w in ['peer','classmate','group','team','collaborate'])
    has_inst = any(w in all_content for w in ['instructor','professor','office hours','feedback'])
    check('5.2', has_peer and has_inst, 'Peer and instructor interaction both present',
          has_peer or has_inst, 'Some interaction present',
          'No clear interaction opportunities')

    has_tech = any(w in all_content for w in
                   ['browser','technology','computer','internet','tool','canvas','login','access'])
    results['6.1'] = ('✅ Met','Technology references found') if has_tech else \
                     ('⚠️ Partially Met','Technology requirements may not be clearly stated')

    has_a11y = any(w in all_content for w in
                   ['accessibility','ada','accommodation','disability','caption','alt text','508'])
    results['7.1'] = ('✅ Met','Accessibility language detected') if has_a11y else \
                     ('⚠️ Partially Met','Accessibility statements may be missing')

    has_start = any(any(w in k.lower() for w in
                        ['start-here','getting-started','the-right-stuff','module-1'])
                    for k in data['wiki_full'])
    check('8.1', len(modules)>0 and has_start, f'{len(modules)} published modules with start page',
          len(modules)>0, 'Modules found but "Start Here" page may be missing',
          'Course navigation unclear')

    return results


def run_udl_precheck(data):
    results     = {}
    all_content = (' '.join(data.get('wiki_full',{}).values()) + ' ' +
                   ' '.join(a['instructions'] for a in
                            data.get('assignments',{}).values())).lower()
    media_titles = ' '.join(data.get('wiki_titles',[])).lower()

    has_video   = any(w in media_titles for w in ['video','youtube','playposit'])
    has_reading = any(w in all_content   for w in ['read','article','chapter','text'])
    has_audio   = any(w in media_titles  for w in ['podcast','audio'])
    has_visual  = any(w in all_content   for w in ['infographic','diagram','image','chart'])
    rc = sum([has_video, has_reading, has_audio, has_visual])
    results['representation'] = (
        ('✅ Met', f'video={has_video}, reading={has_reading}, audio={has_audio}, visual={has_visual}') if rc>=3
        else ('⚠️ Partially Met', f'Only {rc} representation formats') if rc==2
        else ('❌ Not Met', 'Limited content format variety')
    )

    has_choice    = any(w in all_content for w in ['choose','select','option','your choice'])
    has_relevance = any(w in all_content for w in ['real-world','your experience','community'])
    has_challenge = any(w in all_content for w in ['challenge','stretch','advanced','extension'])
    ec = sum([has_choice, has_relevance, has_challenge])
    results['engagement'] = (
        ('✅ Met', 'Choice, relevance, and/or challenge detected') if ec>=2
        else ('⚠️ Partially Met', 'Some engagement strategies') if ec==1
        else ('❌ Not Met', 'Limited engagement strategies')
    )

    has_written  = any(w in all_content for w in ['essay','paper','write','journal','response'])
    has_verbal   = any(w in all_content for w in ['present','speech','record','video','oral'])
    has_visual_e = any(w in all_content for w in ['infographic','poster','create','design','build'])
    has_collab   = any(w in all_content for w in ['group','team','peer','collaborate'])
    ae = sum([has_written, has_verbal, has_visual_e, has_collab])
    results['action_expression'] = (
        ('✅ Met', f'written={has_written}, verbal={has_verbal}, visual={has_visual_e}, collab={has_collab}') if ae>=3
        else ('⚠️ Partially Met', 'Some expression variety') if ae==2
        else ('❌ Not Met', 'Limited ways to demonstrate learning')
    )
    return results


def calculate_health_score(qm_results):
    met     = sum(1 for v in qm_results.values() if v[0].startswith('✅'))
    partial = sum(1 for v in qm_results.values() if v[0].startswith('⚠️'))
    not_met = sum(1 for v in qm_results.values() if v[0].startswith('❌'))
    review  = sum(1 for v in qm_results.values() if v[0].startswith('🔍'))
    total   = len(qm_results)
    if met >= total*0.75 and not_met==0:
        rec = 'PASS — This course is in strong shape. Targeted refinements only.'
    elif not_met<=2 and met>=total*0.5:
        rec = 'REVIEW — Good foundation with targeted areas to improve.'
    else:
        rec = 'REDESIGN — Significant alignment and design work recommended.'
    return met, partial, not_met, review, rec


# ─────────────────────────────────────────────────────────────
#  DOCUMENT BUILDER
# ─────────────────────────────────────────────────────────────

def build_analysis_document(data, identity, modules, grading_groups,
                             objectives, qm_results, udl_results,
                             rubrics, qm_counts):
    met, partial, not_met, review_ct, recommendation = qm_counts
    today = datetime.now().strftime('%Y-%m-%d %H:%M')
    stats = data.get('publish_stats', {})
    L = []

    # ── Header ──
    L += [
        '# CeCe Course Analysis Report',
        '> Generated by the CeCe Course Agent | Handoff Document v4.0',
        '> **This report covers published content only.** Unpublished/draft items are noted but not analyzed.',
        '> Paste this entire document into your LLM to begin your CeCe consultation.',
        '', '---', '',
        '## SECTION 1: COURSE IDENTITY', '',
        '| Field | Value |', '|-------|-------|',
        f'| Course Code    | {identity["title"]} |',
        f'| Course Title   | {identity["code"]} |',
        f'| Delivery Mode  | {identity["modality"]} |',
        f'| Start Date     | {identity["start_date"]} |',
        f'| End Date       | {identity["end_date"]} |',
        f'| Published Modules | {len(modules)} |',
        f'| Weeks Detected | {sum(len(m["weeks_in_module"]) for m in modules)} |',
        f'| Published Pages   | {stats.get("wiki_published",0)} (of {stats.get("wiki_published",0)+stats.get("wiki_unpublished",0)} total) |',
        f'| Published Assignments | {stats.get("assign_published",0)} (of {stats.get("assign_published",0)+stats.get("assign_unpublished",0)} total) |',
        f'| Published Quizzes | {stats.get("assess_published",0)} |',
        f'| LTI Tools      | {len(data["lti_tools"])} |',
        f'| Generated      | {today} |',
        '', '---',
    ]

    # ── Section 2: QM Pre-check ──
    L += [
        '', '## SECTION 2: AUTOMATED QM / UDL PRE-CHECK',
        '> *Based on published content only.*', '',
        '### 2A — Quality Matters (QM 7th Edition)', '',
        '| Standard | Description | Status | Notes |',
        '|----------|-------------|--------|-------|',
    ]
    for sid, desc in QM_STANDARDS.items():
        s, n = qm_results.get(sid, ('🔍 Needs Human Review', ''))
        L.append(f'| {sid} | {desc} | {s} | {n} |')

    L += [
        '', '**Key:** ✅ Met | ⚠️ Partially Met | ❌ Not Met | 🔍 Needs Human Review',
        '', '### 2B — UDL Summary', '',
        '| Principle | Status | Notes |', '|-----------|--------|-------|',
    ]
    for key, label in [('representation','Multiple Means of Representation'),
                       ('engagement','Multiple Means of Engagement'),
                       ('action_expression','Multiple Means of Action & Expression')]:
        s, n = udl_results.get(key, ('🔍 Needs Human Review',''))
        L.append(f'| {label} | {s} | {n} |')

    L += [
        '', '### 2C — Health Score', '',
        f'- **Met:** {met} / {len(QM_STANDARDS)}',
        f'- **Partially Met:** {partial} / {len(QM_STANDARDS)}',
        f'- **Not Met:** {not_met} / {len(QM_STANDARDS)}',
        f'- **Needs Review:** {review_ct} / {len(QM_STANDARDS)}',
        f'- **Recommendation:** {recommendation}',
        '', '---',
    ]

    # ── Section 3: Publish Status Summary ──
    L += [
        '', '## SECTION 3: PUBLISH STATUS SUMMARY',
        '> Items below were detected but excluded from analysis.', '',
        '### Unpublished / Draft Content', '',
        f'- **Wiki pages skipped:** {stats.get("wiki_unpublished", 0)}',
        f'- **Assignments skipped:** {stats.get("assign_unpublished", 0)}',
    ]
    if data.get('assignments_unpub'):
        L.append('')
        L.append('**Unpublished assignments (not analyzed):**')
        for name in data['assignments_unpub']:
            L.append(f'  - {name} *(unpublished)*')
    if data.get('wiki_unpublished'):
        L.append('')
        L.append('**Unpublished pages (not analyzed):**')
        for name in data['wiki_unpublished'][:30]:  # cap at 30 to keep doc readable
            L.append(f'  - {name} *(unpublished)*')
        if len(data['wiki_unpublished']) > 30:
            L.append(f'  - ... and {len(data["wiki_unpublished"])-30} more')
    L += ['', '---']

    # ── Section 4: Syllabus ──
    syllabus_source  = data.get('syllabus_source', 'canvas_tab')
    lti_tool_name    = data.get('syllabus_lti_tool')
    L += ['', '## SECTION 4: SYLLABUS', '']

    if lti_tool_name:
        L += [
            f'> ⚠️ **Agent Note:** The syllabus is delivered via **{lti_tool_name}**, '
            f'a third-party LTI tool integrated into Canvas navigation.',
            '> LTI tool content is hosted on the tool provider\'s platform and is not',
            '> exported inside the IMSCC file. The agent cannot read it.',
            '',
            f'**What this means for your consultation:**',
            f'CeCe will ask you to share the syllabus content from {lti_tool_name} '
            f'early in the session.',
            '',
            f'**How to get your syllabus content:**',
            f'1. Open your Canvas course',
            f'2. Click **{lti_tool_name}** in the course navigation menu',
            f'3. Select all the text (Ctrl+A / Cmd+A) and copy it',
            f'4. Paste it into the chat when CeCe asks',
        ]
    elif data['syllabus_is_embed']:
        L += [
            '> ⚠️ **Agent Note:** The syllabus is hosted externally and cannot be read.',
            '> Links found:', '',
        ]
        for link in data['syllabus_links']:
            L.append(f'- {link}')
        L += [
            '',
            'CeCe will ask you to share syllabus content early in the session.',
        ]
    elif data['syllabus_text']:
        if syllabus_source == 'wiki_page':
            L.append('> ℹ️ **Agent Note:** Canvas syllabus tab was empty. '
                     'Content recovered from a syllabus wiki page.')
            L.append('')
        L.append(data['syllabus_text'])
    else:
        L += [
            '*No syllabus content found in the Canvas tab or any wiki page.*',
            '*CeCe will ask the instructor to share it during consultation.*',
        ]
    L += ['', '---']

    # ── Section 5: Learning Objectives ──
    L += [
        '', '## SECTION 5: LEARNING OBJECTIVES DETECTED',
        '> Auto-detected from published pages only. CeCe will evaluate and refine.', '',
    ]
    if objectives:
        L += ['| # | Source Page | Objective | Bloom\'s Level |',
              '|---|-------------|-----------|--------------|']
        for i, obj in enumerate(objectives, 1):
            L.append(f'| {i} | {obj["source"][:40]} | {obj["text"][:140].replace("|","-")} | {obj["blooms"]} |')
    else:
        L.append('*No objectives auto-detected. Likely in external syllabus. CeCe will address this.*')
    L += ['', '---']

    # ── Section 6: Grading Structure ──
    L += ['', '## SECTION 6: GRADING STRUCTURE', '',
          '| # | Group Name | Weight |', '|---|-----------|--------|']
    total_weight = 0.0
    for g in grading_groups:
        try: total_weight += float(g['weight'])
        except ValueError: pass
        L.append(f'| {g["position"]} | {g["name"]} | {g["weight"]}% |')
    if grading_groups:
        L.append(f'| | **TOTAL** | **{total_weight:.1f}%** |')
        if abs(total_weight - 100) > 1:
            L.append(f'\n> ⚠️ Weights sum to {total_weight:.1f}% — CeCe will address this.')
    else:
        L.append('*Not found — CeCe will ask.*')
    L += ['', '---']

    # ── Section 7: Module & Week Structure ──
    L += ['', '## SECTION 7: MODULE & WEEK STRUCTURE',
          '> Published modules and items only.', '']
    if modules:
        L += ['### Overview', '',
              '| Module | Title | Weeks Inside | Published Items |',
              '|--------|-------|-------------|----------------|']
        for mod in modules:
            weeks_str = ', '.join(mod['weeks_in_module']) if mod['weeks_in_module'] else 'No week labels'
            L.append(f'| {mod["position"]} | {mod["title"]} | {weeks_str} | {len(mod["items"])} |')
        L.append('')
        for mod in modules:
            L.append(f'### Module {mod["position"]}: {mod["title"]}')
            if mod['weeks_in_module']:
                L.append(f'**Weeks:** {", ".join(mod["weeks_in_module"])}')
            L.append('')
            if mod['items']:
                current_week = None
                for item in mod['items']:
                    if item.get('is_week_header'):
                        L.append(f'#### 📅 {item["title"]}')
                        current_week = item['week']
                    else:
                        indent = '  ' if current_week else ''
                        L.append(f'{indent}- **{item["title"]}** *(type: {item["type"]})*')
            else:
                L.append('*No published items.*')
            mod_words = [w for w in re.split(r'[\s|]+', mod['title'].lower()) if len(w)>3]
            for page_name, content in data['wiki_full'].items():
                if any(w in page_name.lower() for w in mod_words):
                    L += ['', f'**Overview page — `{page_name}`:**', '', content[:500], '']
                    break
            L.append('')
    else:
        L.append('*No published modules found.*')
    L.append('---')

    # ── Section 8: Assignment Inventory ──
    L += ['', '## SECTION 8: ASSIGNMENT INVENTORY',
          '> Published assignments only.', '']
    if data['assignments']:
        L += ['### Summary', '',
              '| Assignment | Points | Due Date | Submission Type |',
              '|-----------|--------|----------|----------------|']
        for name, det in data['assignments'].items():
            L.append(f'| {name} | {det["points"]} | {det["due_date"]} | {det["sub_type"]} |')
        L += ['', '### Full Instructions', '']
        for name, det in data['assignments'].items():
            L += [
                f'#### {name}',
                f'**Points:** {det["points"]} | **Due:** {det["due_date"]} | **Submission:** {det["sub_type"]}',
                '', det['instructions'], '',
            ]
    else:
        L.append('*No published assignments found.*')
    L += ['', '---']

    # ── Section 9: Assessments ──
    L += ['', '## SECTION 9: ASSESSMENTS / QUIZZES',
          '> Published assessments only.', '']
    if data['assessments']:
        for name, content in data['assessments'].items():
            L += [f'### {name}', '', content, '']
    else:
        L.append('*No published assessments found.*')
    L += ['', '---']

    # ── Section 10: Rubrics ──
    L += ['', '## SECTION 10: RUBRICS', '']
    if rubrics:
        for r in rubrics:
            L.append(f'### {r["title"]}')
            for c in r['criteria']:
                L.append(f'- {c}')
            L.append('')
    else:
        L.append('*No rubrics found. CeCe will recommend adding them.*')
    L += ['', '---']

    # ── Section 11: Materials (titles only) ──
    L += ['', '## SECTION 11: INSTRUCTIONAL MATERIALS',
          '> Published media pages — titles only.', '']
    if data['wiki_titles']:
        for t in sorted(data['wiki_titles']):
            L.append(f'- {t}')
    else:
        L.append('*No media/resource pages identified.*')
    L += ['', '---']

    # ── Section 12: All Published Course Page Content ──
    L += ['', '## SECTION 12: COURSE PAGE CONTENT',
          '> Full text of published module and course pages.', '']
    for page_name, content in data['wiki_full'].items():
        L += [f'### {page_name}', '', content, '']
    L += ['', '---']

    # ── Section 13: Agent Flags ──
    L += ['', '## SECTION 13: AGENT FLAGS', '']
    flags = []
    if data.get('syllabus_lti_tool'):
        flags.append(f'⚠️ Syllabus is in {data["syllabus_lti_tool"]} (LTI tool) — CeCe must ask instructor to paste it')
    elif data['syllabus_is_embed']:
        flags.append('⚠️ Syllabus is external — CeCe should ask for content early')
    elif not data['syllabus_text']:
        flags.append('⚠️ No syllabus found anywhere — CeCe must ask instructor')
    elif data.get('syllabus_source') == 'wiki_page':
        flags.append('ℹ️ Syllabus found in wiki page (not Canvas syllabus tab) — included in analysis')
    if not objectives:
        flags.append('⚠️ No objectives auto-detected — likely in external syllabus')
    if not grading_groups:
        flags.append('⚠️ Grading structure not found')
    elif abs(total_weight - 100) > 1:
        flags.append(f'⚠️ Grading weights sum to {total_weight:.1f}%')
    if not rubrics:
        flags.append('⚠️ No rubrics found — CeCe will recommend adding them')
    if len(modules) == 0:
        flags.append('⚠️ No published modules found')
    if stats.get('assign_unpublished', 0) > 0:
        flags.append(f'ℹ️ {stats["assign_unpublished"]} unpublished assignment(s) excluded from analysis')
    if stats.get('wiki_unpublished', 0) > 0:
        flags.append(f'ℹ️ {stats["wiki_unpublished"]} unpublished page(s) excluded from analysis')
    if not_met >= 4:
        flags.append('🔴 Multiple QM standards not met — full redesign recommended')
    for flag in flags:
        L.append(flag)
    if not flags:
        L.append('✅ No critical flags.')
    L += ['', '---']

    # ── CeCe Prompt ──
    L += [
        '', '## ─── CECE CONSULTATION PROMPT ───',
        '> Copy this entire document plus the prompt below into your LLM.', '',
        '```',
        'You are CeCe — a warm, expert instructional design consultant grounded in',
        "L. Dee Fink's Designing Courses for Significant Learning, the Quality Matters",
        '7th Edition Rubric, and Universal Design for Learning principles.',
        '',
        'Review the course analysis above.',
        '- Section 2: Automated QM/UDL pre-check (published content only)',
        '- Section 3: Publish status — lists any unpublished/draft items that were excluded',
        '- Section 13: Specific agent flags',
        '',
        'IMPORTANT CONTEXT:',
        '- This report covers PUBLISHED content only. Unpublished items are noted in Section 3.',
        ('- The syllabus is in ' + data['syllabus_lti_tool'] +
         ' (LTI tool) — ask the instructor to paste it into the chat early.'
         if data.get('syllabus_lti_tool')
         else '- The syllabus is an external embed — ask the instructor to share it early.'
         if data['syllabus_is_embed']
         else '- Syllabus was found in a wiki page and is included in Section 4.'
         if data.get('syllabus_source') == 'wiki_page'
         else '- No syllabus was found — ask the instructor to share it early.'
         if not data['syllabus_text']
         else '- Syllabus content is included in Section 4.'),
        f'- {len(modules)} published modules containing '
        f'{sum(len(m["weeks_in_module"]) for m in modules)} detected weeks.',
        '  Weeks live inside modules, not as separate top-level modules.',
        '',
        'Begin with your warm orientation message, then your QM/UDL health check.',
        f'Agent recommendation: {recommendation}',
        '',
        'When consultation is complete, produce the Course Blueprint Document',
        'following the BLUEPRINT_DOCUMENT_TEMPLATE structure exactly.',
        '```',
        '',
        '---',
        f'*CeCe Course Analysis Report v4.0 — Generated {today}*',
    ]

    return '\n'.join(L)


# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────

def main():
    print('\n' + '='*60)
    print('  CeCe Course Analysis Agent v4')
    print('='*60)

    if len(sys.argv) < 2:
        print('\nUsage:  python analyze.py your-course.imscc')
        print('        python analyze.py your-course.imscc --output my-analysis.md')
        sys.exit(1)

    imscc_path = sys.argv[1]
    if '--output' in sys.argv:
        output_path = sys.argv[sys.argv.index('--output') + 1]
    else:
        base        = os.path.splitext(os.path.basename(imscc_path))[0]
        output_path = f'{base}_analysis.md'

    print('\n📖 Reading course content...')
    data = read_imscc(imscc_path)

    print('\n🔍 Extracting course structure...')
    identity       = extract_course_identity(data)
    modules        = extract_modules(data)
    grading_groups = extract_grading_structure(data)
    rubrics        = extract_rubrics(data)
    objectives     = extract_learning_objectives(data, modules)
    stats          = data['publish_stats']

    print(f'   Course:      {identity["title"]} — {identity["code"]}')
    print(f'   Modules:     {len(modules)} published '
          f'({sum(len(m["weeks_in_module"]) for m in modules)} weeks detected)')
    for mod in modules:
        wk = ', '.join(mod["weeks_in_module"]) if mod["weeks_in_module"] else 'no week labels'
        print(f'              Module {mod["position"]}: {mod["title"][:50]} [{wk}]')
    print(f'   Grading:     {len(grading_groups)} groups')
    print(f'   Objectives:  {len(objectives)} detected')
    print(f'   Rubrics:     {len(rubrics)}')
    print(f'   Assignments: {stats.get("assign_published",0)} published | '
          f'{stats.get("assign_unpublished",0)} unpublished (skipped)')
    if data['assignments']:
        for name, det in data['assignments'].items():
            print(f'              ✅ {name[:50]} | {det["points"]} pts | Due: {det["due_date"]}')
    if data['assignments_unpub']:
        for name in data['assignments_unpub']:
            print(f'              ⬜ {name[:50]} (unpublished — not analyzed)')
    print(f'   Wiki pages:  {stats.get("wiki_published",0)} published | '
          f'{stats.get("wiki_unpublished",0)} unpublished (skipped)')
    if data.get('syllabus_lti_tool'):
        print(f'   Syllabus:    ⚠️ LTI tool ({data["syllabus_lti_tool"]}) — cannot be read by agent')
    elif data['syllabus_is_embed']:
        print(f'   Syllabus:    External embed ({len(data["syllabus_links"])} links)')
        for lnk in data['syllabus_links']:
            print(f'              {lnk[:80]}')
    elif data.get('syllabus_source') == 'wiki_page':
        print(f'   Syllabus:    Found in wiki page ({len(data["syllabus_text"])} characters)')
    elif data['syllabus_text']:
        print(f'   Syllabus:    Canvas tab ({len(data["syllabus_text"])} characters)')
    else:
        print(f'   Syllabus:    ⚠️ Not found — CeCe will ask instructor')

    print('\n✅ Running QM/UDL pre-check...')
    qm_results  = run_qm_precheck(data, modules, grading_groups, objectives)
    udl_results = run_udl_precheck(data)
    qm_counts   = calculate_health_score(qm_results)
    met, partial, not_met, review_ct, recommendation = qm_counts
    print(f'   Met: {met} | Partial: {partial} | Not Met: {not_met} | Review: {review_ct}')
    print(f'   Recommendation: {recommendation}')

    print('\n📝 Building Analysis Document...')
    document = build_analysis_document(
        data, identity, modules, grading_groups,
        objectives, qm_results, udl_results, rubrics, qm_counts
    )

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(document)

    kb     = os.path.getsize(output_path) / 1024
    tokens = len(document) // 4
    print(f'\n{"="*60}')
    print(f'✨ Saved: {output_path}')
    print(f'   Size: {kb:.1f} KB | Tokens: ~{tokens:,}')
    print(f'   QM:   {recommendation.split("—")[0].strip()}')
    print(f'{"="*60}')
    print('\nNext: Paste the .md file into your LLM to start the CeCe session.\n')


if __name__ == '__main__':
    main()
