"""
analyze.py — CeCe Course DNA Extraction Agent v6.1
====================================================
CeCe reads Canvas IMSCC exports and extracts the complete course DNA
into a Course DNA Document for MeMe's QM consultation.

v6.1: Preserves HTML metadata (headings, links, images/alt text,
accessibility flags) in Sections 6 and 11 for MeMe's GS 7.x and 8.x evaluation.

CeCe extracts. She does not evaluate or judge. That's MeMe's job.
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


def extract_html_metadata(raw_html):
    """
    Extract structured metadata from raw HTML that MeMe needs for QM evaluation.
    Returns a dict with headings, links, images, and accessibility observations.
    """
    meta = {
        'headings': [],   # [(level, text)]
        'links': [],      # [(text, url)]
        'images': [],     # [(alt_text, src_snippet)]
        'has_tables': False,
        'accessibility_notes': [],
    }

    if not raw_html:
        return meta

    # Extract headings with level
    for m in re.finditer(r'<h([1-6])[^>]*>(.*?)</h\1>', raw_html, re.DOTALL | re.IGNORECASE):
        level = int(m.group(1))
        text = strip_html(m.group(2)).strip()
        if text:
            meta['headings'].append((level, text))

    # Extract links with URL and display text
    for m in re.finditer(r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', raw_html, re.DOTALL | re.IGNORECASE):
        url = m.group(1).strip()
        text = strip_html(m.group(2)).strip()
        if url and not url.startswith('#') and not url.startswith('javascript:'):
            display = text if text else '[no link text]'
            meta['links'].append((display, url))

    # Extract images with alt text
    for m in re.finditer(r'<img\s[^>]*?(?:alt=["\']([^"\']*)["\'])?[^>]*?(?:src=["\']([^"\']+)["\'])?[^>]*?/?>', raw_html, re.IGNORECASE):
        alt = m.group(1) if m.group(1) is not None else None
        src = m.group(2) or ''
        # Also try reverse order (src before alt)
        if alt is None:
            alt_m = re.search(r'alt=["\']([^"\']*)["\']', m.group(0), re.IGNORECASE)
            alt = alt_m.group(1) if alt_m else None
        src_snippet = src.split('/')[-1][:40] if src else '[unknown]'

        if alt is None:
            meta['images'].append(('[MISSING ALT TEXT]', src_snippet))
            meta['accessibility_notes'].append(f'Image missing alt text: {src_snippet}')
        elif alt.strip() == '':
            meta['images'].append(('[decorative — empty alt]', src_snippet))
        else:
            meta['images'].append((alt.strip(), src_snippet))

    # Check for tables
    if '<table' in raw_html.lower():
        meta['has_tables'] = True

    # Check heading hierarchy
    if meta['headings']:
        levels = [h[0] for h in meta['headings']]
        for i in range(1, len(levels)):
            if levels[i] > levels[i-1] + 1:
                meta['accessibility_notes'].append(
                    f'Heading level skipped: h{levels[i-1]} → h{levels[i]} ("{meta["headings"][i][1][:30]}")')

    # Check for non-descriptive link text
    bad_link_texts = {'click here', 'here', 'link', 'read more', 'more', 'this'}
    for text, url in meta['links']:
        if text.lower().strip() in bad_link_texts:
            meta['accessibility_notes'].append(f'Non-descriptive link text: "{text}" → {url[:60]}')

    return meta


def format_metadata_block(meta):
    """Format extracted metadata into a readable markdown block for the DNA document."""
    lines = []

    if meta['headings']:
        lines.append('**Heading Structure:**')
        for level, text in meta['headings']:
            indent = '  ' * (level - 1)
            lines.append(f'{indent}- h{level}: {text}')
        lines.append('')

    if meta['links']:
        lines.append(f'**Links ({len(meta["links"])}):**')
        for text, url in meta['links']:
            url_short = url[:80] + ('...' if len(url) > 80 else '')
            lines.append(f'- [{text}]({url_short})')
        lines.append('')

    if meta['images']:
        lines.append(f'**Images ({len(meta["images"])}):**')
        for alt, src in meta['images']:
            lines.append(f'- Alt: "{alt}" — {src}')
        lines.append('')

    if meta['has_tables']:
        lines.append('**Contains tables:** Yes')
        lines.append('')

    if meta['accessibility_notes']:
        lines.append('**⚠️ Accessibility Flags:**')
        for note in meta['accessibility_notes']:
            lines.append(f'- {note}')
        lines.append('')

    return '\n'.join(lines) if lines else ''


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
    return workflow_state.lower().strip() in ('active', 'published', '')


# ─────────────────────────────────────────────────────────────
#  PUBLISH STATE RESOLVER
# ─────────────────────────────────────────────────────────────

def build_published_file_set(module_meta_xml, manifest_xml):
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

    id_to_href = {}
    resource_blocks = re.split(r'<resource\s', manifest_xml)[1:]
    for block in resource_blocks:
        id_m   = re.search(r'identifier=["\']([^"\']+)["\']', block)
        href_m = re.search(r'href=["\']([^"\']+)["\']', block)
        if id_m and href_m:
            id_to_href[id_m.group(1)] = href_m.group(1)

    published_hrefs = set()
    for ref, state in item_states.items():
        if is_published_state(state) and ref in id_to_href:
            published_hrefs.add(id_to_href[ref])

    return published_hrefs, item_states, id_to_href


# ─────────────────────────────────────────────────────────────
#  IMSCC READER
# ─────────────────────────────────────────────────────────────

def read_imscc(file_path, file_bytes=None, syllabus_text=''):
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
        'wiki_full':          {},    # page_name → plain text
        'wiki_raw':           {},    # page_name → raw HTML (for metadata extraction)
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

        for path, key in [
            ('course_settings/course_settings.xml',   'course_settings'),
            ('course_settings/assignment_groups.xml', 'assignment_groups'),
            ('course_settings/module_meta.xml',       'module_meta'),
            ('course_settings/rubrics.xml',           'rubrics'),
            ('imsmanifest.xml',                       'manifest'),
        ]:
            if path in files:
                data[key] = z.read(path).decode('utf-8', errors='ignore')

        if syllabus_text:
            data['syllabus_text'] = syllabus_text.strip()
            print(f'   Syllabus: {len(syllabus_text):,} chars provided by user')
        else:
            print('   Syllabus: not provided — will be requested by MeMe')

        published_hrefs, item_states, id_to_href = build_published_file_set(
            data['module_meta'], data['manifest']
        )

        # LTI tools from manifest
        for block in re.split(r'<resource\s', data['manifest'])[1:]:
            type_m = re.search(r'type=["\']([^"\']+)["\']', block)
            if type_m and ('basiclti' in type_m.group(1).lower()
                           or 'imsbasiclti' in type_m.group(1).lower()):
                title_m = re.search(r'<title>(.+?)</title>', block, re.DOTALL)
                url_m   = re.search(r'<blti:launch_url>(.+?)</blti:launch_url>', block, re.DOTALL)
                tool_name = strip_html(title_m.group(1)).strip() if title_m else 'Unknown LTI Tool'
                tool_url  = url_m.group(1).strip() if url_m else ''
                data['lti_tools'].append({'name': tool_name, 'url': tool_url})

        # LTI from standalone files
        for f in files:
            if 'basiclti' in f.lower() or 'blti' in f.lower():
                try:
                    xml = z.read(f).decode('utf-8', errors='ignore')
                    title_m = re.search(r'<blti:title>(.+?)</blti:title>', xml, re.DOTALL)
                    url_m   = re.search(r'<blti:launch_url>(.+?)</blti:launch_url>', xml, re.DOTALL)
                    if title_m:
                        name = strip_html(title_m.group(1)).strip()
                        url  = url_m.group(1).strip() if url_m else ''
                        if not any(t['name'] == name for t in data['lti_tools']):
                            data['lti_tools'].append({'name': name, 'url': url})
                except Exception:
                    pass

        if data['lti_tools']:
            print(f"   LTI tools detected: {len(data['lti_tools'])}")

        # Wiki pages
        wiki_files = [f for f in files if f.startswith('wiki_content/') and f.endswith('.html')]
        wiki_pub = wiki_unpub = 0

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
                        data['wiki_raw'][page_name] = raw
                except Exception:
                    data['wiki_full'][page_name] = '[could not read]'

        print(f"   Wiki pages published: {wiki_pub} | unpublished/unused: {wiki_unpub}")

        # Assignments
        assign_html_files = [
            f for f in files
            if f.endswith('.html') and not f.startswith('wiki_content/')
            and not f.startswith('web_resources/') and 'syllabus' not in f.lower() and '/' in f
        ]
        assign_pub = assign_unpub = 0

        for assign_path in assign_html_files:
            try:
                parts     = assign_path.split('/')
                folder_id = parts[0]
                file_name = parts[-1]
                settings_path = f"{folder_id}/assignment_settings.xml"
                published = True
                due_date = 'Not set'
                points = 'Not specified'
                sub_type = 'Not specified'
                clean_name = clean_assignment_name(folder_id, file_name)

                if settings_path in files:
                    xml = z.read(settings_path).decode('utf-8', errors='ignore')
                    state_m  = re.search(r'<workflow_state>(.+?)</workflow_state>', xml, re.DOTALL)
                    due_m    = re.search(r'<due_at>(.+?)</due_at>', xml, re.DOTALL)
                    pts_m    = re.search(r'<points_possible>(.+?)</points_possible>', xml, re.DOTALL)
                    sub_m    = re.search(r'<submission_types>(.+?)</submission_types>', xml, re.DOTALL)
                    title_m  = re.search(r'<title>(.+?)</title>', xml, re.DOTALL)
                    if state_m: published = is_published_state(state_m.group(1))
                    if due_m:   due_date = format_due_date(due_m.group(1).strip())
                    if pts_m:   points = pts_m.group(1).strip()
                    if sub_m:   sub_type = strip_html(sub_m.group(1)).strip()
                    if title_m: clean_name = strip_html(title_m.group(1)).strip()

                if not published:
                    assign_unpub += 1
                    data['assignments_unpub'].append(clean_name)
                    continue

                raw_html     = z.read(assign_path).decode('utf-8', errors='ignore')
                instructions = strip_html(raw_html).strip()
                if instructions:
                    assign_pub += 1
                    data['assignments'][clean_name] = {
                        'instructions': instructions, 'due_date': due_date,
                        'points': points, 'sub_type': sub_type, 'folder_id': folder_id,
                        'instructions_raw': raw_html,
                    }
            except Exception:
                pass

        print(f"   Assignments published: {assign_pub} | unpublished: {assign_unpub}")

        # Assessments
        assess_files = [f for f in files if 'assessment_qti.xml' in f]
        assess_pub = assess_unpub = 0
        for assess_path in assess_files[:15]:
            try:
                folder_id     = assess_path.split('/')[0]
                settings_path = f"{folder_id}/assessment_meta.xml"
                published     = True
                if settings_path in files:
                    xml     = z.read(settings_path).decode('utf-8', errors='ignore')
                    state_m = re.search(r'<workflow_state>(.+?)</workflow_state>', xml, re.DOTALL)
                    if state_m: published = is_published_state(state_m.group(1))
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

        data['publish_stats'] = {
            'wiki_published': wiki_pub, 'wiki_unpublished': wiki_unpub,
            'assign_published': assign_pub, 'assign_unpublished': assign_unpub,
            'assess_published': assess_pub, 'assess_unpublished': assess_unpub,
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
    combined = (' '.join(data.get('wiki_full',{}).values()) + data.get('syllabus_text','')).lower()
    if 'online' in combined: identity['modality'] = 'Online'
    elif 'hybrid' in combined: identity['modality'] = 'Hybrid'
    elif 'face-to-face' in combined or 'in-person' in combined: identity['modality'] = 'Face-to-Face'
    return identity


def extract_modules(data):
    modules = []
    meta = data.get('module_meta', '')
    if not meta:
        return modules
    for block in re.split(r'<module\s+identifier=[^>]+>', meta)[1:]:
        title_m = re.search(r'<title>(.+?)</title>', block, re.DOTALL)
        pos_m   = re.search(r'<position>(.+?)</position>', block, re.DOTALL)
        state_m = re.search(r'<workflow_state>(.+?)</workflow_state>', block, re.DOTALL)
        mod_title = strip_html(title_m.group(1)).strip() if title_m else 'Untitled Module'
        state     = state_m.group(1).strip() if state_m else 'active'
        if not is_published_state(state):
            continue
        items_section = re.search(r'<items>(.*?)</items>', block, re.DOTALL)
        items = []
        current_week = None
        if items_section:
            for item_block in re.split(r'<item\s+identifier=[^>]+>', items_section.group(1))[1:]:
                t_m      = re.search(r'<title>(.+?)</title>', item_block, re.DOTALL)
                ct_m     = re.search(r'<content_type>(.+?)</content_type>', item_block, re.DOTALL)
                istate_m = re.search(r'<workflow_state>(.+?)</workflow_state>', item_block, re.DOTALL)
                if not t_m: continue
                item_title = strip_html(t_m.group(1)).strip()
                item_type  = strip_html(ct_m.group(1)).strip() if ct_m else ''
                item_state = istate_m.group(1).strip() if istate_m else 'active'
                if not is_published_state(item_state): continue
                week_match = re.match(r'week\s+(\d+)\s*(?:[|:—\-]\s*(.+))?', item_title, re.IGNORECASE)
                if week_match:
                    wn = week_match.group(1)
                    wl = week_match.group(2).strip() if week_match.group(2) else ''
                    current_week = f"Week {wn}" + (f" — {wl}" if wl else '')
                    items.append({'title': item_title, 'type': item_type,
                                  'is_week_header': True, 'week': current_week, 'published': True})
                else:
                    items.append({'title': item_title, 'type': item_type,
                                  'is_week_header': False, 'week': current_week, 'published': True})
        weeks_in_module = sorted(
            set(i['week'] for i in items if i.get('week') and i.get('is_week_header')),
            key=lambda w: int(re.search(r'\d+', w).group()) if re.search(r'\d+', w) else 0)
        modules.append({
            'title': mod_title, 'position': pos_m.group(1).strip() if pos_m else '?',
            'state': state, 'items': items, 'weeks_in_module': weeks_in_module,
        })
    return modules


def extract_grading_structure(data):
    groups = []
    xml = data.get('assignment_groups', '')
    if not xml: return groups
    for block in re.split(r'<assignmentGroup\s+identifier=[^>]+>', xml)[1:]:
        t_m = re.search(r'<title>(.+?)</title>', block, re.DOTALL)
        w_m = re.search(r'<group_weight>(.+?)</group_weight>', block, re.DOTALL)
        p_m = re.search(r'<position>(.+?)</position>', block, re.DOTALL)
        name = strip_html(t_m.group(1)).strip() if t_m else 'Unnamed'
        pos  = p_m.group(1).strip() if p_m else '?'
        try: weight = f"{float(w_m.group(1).strip()):.1f}" if w_m else '0.0'
        except ValueError: weight = w_m.group(1).strip() if w_m else '0.0'
        groups.append({'name': name, 'weight': weight, 'position': pos})
    groups.sort(key=lambda g: int(g['position']) if g['position'].isdigit() else 99)
    return groups


def extract_rubrics(data):
    """Deep rubric extraction using XML parser with namespace stripping."""
    rubrics = []
    xml = data.get('rubrics', '')
    if not xml:
        print("   Rubrics: rubrics.xml not found or empty")
        return rubrics

    print(f"   Rubrics: raw XML is {len(xml):,} chars")

    # Strip namespaces
    clean_xml = re.sub(r'\sxmlns(?::\w+)?\s*=\s*["\'][^"\']*["\']', '', xml)
    clean_xml = re.sub(r'<(/?)[\w]+:', r'<\1', clean_xml)
    clean_xml = re.sub(r'\s\w+:\w+\s*=\s*["\'][^"\']*["\']', '', clean_xml)

    # Try ET parsing
    try:
        root = ET.fromstring(clean_xml)
    except ET.ParseError:
        print("   Rubrics: XML parse error, falling back to regex")
        return _extract_rubrics_regex(clean_xml)

    print(f"   Rubrics: root tag = '{root.tag}'")

    if root.tag == 'rubrics':
        rubric_elements = root.findall('rubric')
    else:
        rubric_elements = root.findall('.//rubric')

    # Fallback deep scan
    if not rubric_elements:
        for el in root.iter():
            if el.tag.lower().endswith('rubric') and el.tag != root.tag:
                rubric_elements.append(el)

    if not rubric_elements:
        print("   Rubrics: ET found nothing, falling back to regex")
        return _extract_rubrics_regex(clean_xml)

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
                            ratings.append({'name': r_name, 'description': r_desc, 'points': r_pts})
                criteria.append({'name': crit_name, 'description': crit_desc,
                                 'points': crit_pts, 'ratings': ratings})
        rubrics.append({'title': title, 'points': points, 'criteria': criteria})

    total_criteria = sum(len(r['criteria']) for r in rubrics)
    total_ratings = sum(len(c['ratings']) for r in rubrics for c in r['criteria'])
    print(f"   Rubrics: extracted {len(rubrics)} rubric(s), {total_criteria} criteria, {total_ratings} rating levels")
    return rubrics


def _extract_rubrics_regex(xml):
    """Regex fallback for rubric extraction."""
    rubrics = []
    for block in re.findall(r'<rubric>(.*?)</rubric>', xml, re.DOTALL):
        t_m = re.search(r'<title>(.*?)</title>', block, re.DOTALL)
        title = strip_html(t_m.group(1)).strip() if t_m else 'Untitled'
        pp_m = re.search(r'<points_possible>(.*?)</points_possible>', block, re.DOTALL)
        criteria = []
        criteria_m = re.search(r'<criteria>(.*?)</criteria>', block, re.DOTALL)
        if criteria_m:
            for cb in re.findall(r'<criterion>(.*?)</criterion>', criteria_m.group(1), re.DOTALL):
                desc_m = re.search(r'<description>(.*?)</description>', cb, re.DOTALL)
                long_m = re.search(r'<long_description>(.*?)</long_description>', cb, re.DOTALL)
                pts_m  = re.search(r'<points>(.*?)</points>', cb, re.DOTALL)
                ratings = []
                ratings_m = re.search(r'<ratings>(.*?)</ratings>', cb, re.DOTALL)
                if ratings_m:
                    for rb in re.findall(r'<rating>(.*?)</rating>', ratings_m.group(1), re.DOTALL):
                        r_d = re.search(r'<description>(.*?)</description>', rb, re.DOTALL)
                        r_l = re.search(r'<long_description>(.*?)</long_description>', rb, re.DOTALL)
                        r_p = re.search(r'<points>(.*?)</points>', rb, re.DOTALL)
                        r_name = strip_html(r_d.group(1)).strip() if r_d else ''
                        if r_name:
                            ratings.append({'name': r_name,
                                'description': strip_html(r_l.group(1)).strip() if r_l else '',
                                'points': r_p.group(1).strip() if r_p else ''})
                criteria.append({
                    'name': strip_html(desc_m.group(1)).strip() if desc_m else 'Unnamed',
                    'description': strip_html(long_m.group(1)).strip() if long_m else '',
                    'points': pts_m.group(1).strip() if pts_m else '?',
                    'ratings': ratings})
        rubrics.append({'title': title, 'points': pp_m.group(1).strip() if pp_m else '', 'criteria': criteria})
    print(f"   Rubrics (regex): extracted {len(rubrics)} rubric(s)")
    return rubrics


# ─────────────────────────────────────────────────────────────
#  DOCUMENT BUILDER
# ─────────────────────────────────────────────────────────────

def build_course_dna(data, identity, modules, grading_groups, rubrics):
    today = datetime.now().strftime('%Y-%m-%d')
    stats = data.get('publish_stats', {})
    syl_text = data.get('syllabus_text', '')

    L = [
        '# CeCe Course DNA Document',
        f'> Extracted {today} from `{data["file_name"]}`',
        '> This document contains the complete published content of the Canvas course.',
        '> It is organized for MeMe to conduct a QM 7th Edition needs analysis.',
        '> CeCe does not evaluate — she extracts. All analysis is performed by MeMe.',
        '', '---',
    ]

    # Section 1: Course Identity
    L += ['', '## SECTION 1: COURSE IDENTITY', '',
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
        f'| Generated | {today} |', '', '---']

    # Section 2: Publish Status
    L += ['', '## SECTION 2: PUBLISH STATUS',
        '> Items below were detected but are NOT included in this document.', '']
    if data['wiki_unpublished']:
        L.append('**Unpublished Pages:**')
        for p in sorted(data['wiki_unpublished']): L.append(f'- {p}')
        L.append('')
    if data['assignments_unpub']:
        L.append('**Unpublished Assignments:**')
        for a in data['assignments_unpub']: L.append(f'- {a}')
        L.append('')
    if not data['wiki_unpublished'] and not data['assignments_unpub']:
        L.append('*All detected content is published.*')
    L += ['', '---']

    # Section 3: Syllabus
    L += ['', '## SECTION 3: SYLLABUS', '']
    if syl_text:
        L += [syl_text, '']
    else:
        L += ['*Syllabus was not provided. MeMe should request it from the instructor.*', '']
    L += ['---']

    # Section 4: Module Structure
    L += ['', '## SECTION 4: MODULE & WEEK STRUCTURE', '']
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
                    itype = item.get('type', '').replace('WikiPage', 'Page').replace('DiscussionTopic', 'Discussion').replace('Quizzes::Quiz', 'Quiz').replace('ContextModuleSubHeader', 'Header').replace('ExternalUrl', 'External Link').replace('ContextExternalTool', 'LTI Tool')
                    L.append(f'| {j} | {item["title"].replace("|","/")} | {itype} | {item.get("week","") or ""} |')
                L.append('')
    L += ['---']

    # Section 5: Grading Structure
    L += ['', '## SECTION 5: GRADING STRUCTURE', '']
    if not grading_groups:
        L.append('*No grading structure found.*')
    else:
        L += ['| Group Name | Weight (%) |', '|------------|-----------|']
        total_weight = 0.0
        for g in grading_groups:
            L.append(f'| {g["name"]} | {g["weight"]}% |')
            try: total_weight += float(g['weight'])
            except ValueError: pass
        L += [f'| **Total** | **{total_weight:.1f}%** |', '']
        if abs(total_weight - 100) > 1:
            L.append(f'*Note: Weights sum to {total_weight:.1f}%, not 100%.*')
    L += ['', '---']

    # Section 6: Assignment Inventory
    L += ['', '## SECTION 6: ASSIGNMENT INVENTORY', '']
    if not data['assignments']:
        L.append('*No published assignments found.*')
    else:
        for name, det in data['assignments'].items():
            L += [f'### {name}', '',
                f'**Points:** {det["points"]} | **Due:** {det["due_date"]} | **Submission:** {det["sub_type"]}', '']
            # Add metadata block if raw HTML is available
            raw_html = det.get('instructions_raw', '')
            if raw_html:
                meta = extract_html_metadata(raw_html)
                meta_block = format_metadata_block(meta)
                if meta_block:
                    L += [meta_block]
            L += ['**Instructions:**', det['instructions'], '', '---', '']
    L += ['---']

    # Section 7: Assessments
    L += ['', '## SECTION 7: ASSESSMENTS / QUIZZES', '']
    if not data['assessments']:
        L.append('*No published assessments found.*')
    else:
        for name, content in data['assessments'].items():
            L += [f'### {name}', '', content, '', '---', '']
    L += ['---']

    # Section 8: Rubrics
    L += ['', '## SECTION 8: RUBRICS', '']
    if not rubrics:
        L.append('*No rubrics found. This is a significant gap for QM Standard 3.3.*')
    else:
        for rub in rubrics:
            pts_note = f' ({rub["points"]} pts total)' if rub.get('points') else ''
            L += [f'### {rub["title"]}{pts_note}', '']
            for crit in rub['criteria']:
                crit_desc = f' — {crit["description"]}' if crit.get('description') else ''
                L.append(f'**Criterion: {crit["name"]}** ({crit["points"]} pts){crit_desc}')
                L.append('')
                if crit['ratings']:
                    L += ['| Rating | Points | Description |', '|--------|--------|-------------|']
                    for rating in crit['ratings']:
                        desc = rating['description'].replace('|', '/').replace('\n', ' ')
                        L.append(f'| {rating["name"]} | {rating["points"]} | {desc} |')
                    L.append('')
                else:
                    L.append('*No rating levels defined.*')
                    L.append('')
            L += ['---', '']
    L += ['---']

    # Section 9: Materials
    L += ['', '## SECTION 9: INSTRUCTIONAL MATERIALS', '']
    if data['wiki_titles']:
        for t in sorted(data['wiki_titles']): L.append(f'- {t}')
    else:
        L.append('*No media/resource pages identified.*')
    L += ['', '---']

    # Section 10: LTI Tools
    L += ['', '## SECTION 10: LTI TOOLS & EXTERNAL INTEGRATIONS', '']
    if data['lti_tools']:
        L += ['| Tool Name | Launch URL |', '|-----------|-----------|']
        for tool in data['lti_tools']:
            L.append(f'| {tool["name"]} | {tool.get("url", "N/A")} |')
    else:
        L.append('*No LTI tools detected.*')
    L += ['', '---']

    # Section 11: Full Page Content
    L += ['', '## SECTION 11: COURSE PAGE CONTENT',
        '> Each page includes an HTML metadata block (headings, links, images, accessibility flags)',
        '> followed by the plain text content. MeMe uses metadata for QM 7.x and 8.x evaluation.', '']
    for page_name, content in data['wiki_full'].items():
        L += [f'### {page_name}', '']
        # Add metadata block if raw HTML is available
        raw_html = data.get('wiki_raw', {}).get(page_name, '')
        if raw_html:
            meta = extract_html_metadata(raw_html)
            meta_block = format_metadata_block(meta)
            if meta_block:
                L += [meta_block]
        L += ['**Page Content:**', '', content, '', '---', '']
    L += ['---']

    # Section 12: Notes for MeMe
    L += ['', '## SECTION 12: NOTES FOR MEME', '']
    notes = []
    if not syl_text:
        notes.append('Syllabus not provided. Request it before evaluating GS 1 and GS 2.')
    if not rubrics:
        notes.append('No rubrics found. Critical gap for QM Standard 3.3.')
    else:
        tc = sum(len(r['criteria']) for r in rubrics)
        tr = sum(1 for r in rubrics for c in r['criteria'] if c['ratings'])
        notes.append(f'{len(rubrics)} rubric(s), {tc} criteria, {tr} with detailed ratings.')
    if not modules:
        notes.append('No published modules found.')
    up = stats.get('assign_unpublished', 0) + stats.get('wiki_unpublished', 0)
    if up > 0:
        notes.append(f'{up} item(s) were unpublished and excluded.')

    # Aggregate accessibility flags from all pages
    all_a11y_flags = []
    total_images = 0
    missing_alt = 0
    total_links = 0
    bad_link_text = 0
    heading_skips = 0

    for page_name in data.get('wiki_raw', {}):
        meta = extract_html_metadata(data['wiki_raw'][page_name])
        total_images += len(meta['images'])
        missing_alt += sum(1 for alt, _ in meta['images'] if 'MISSING' in alt)
        total_links += len(meta['links'])
        bad_link_text += sum(1 for n in meta['accessibility_notes'] if 'Non-descriptive link' in n)
        heading_skips += sum(1 for n in meta['accessibility_notes'] if 'Heading level skipped' in n)

    for det in data['assignments'].values():
        raw = det.get('instructions_raw', '')
        if raw:
            meta = extract_html_metadata(raw)
            total_images += len(meta['images'])
            missing_alt += sum(1 for alt, _ in meta['images'] if 'MISSING' in alt)

    notes.append(f'HTML metadata extracted for {len(data.get("wiki_raw", {}))} pages and {len(data["assignments"])} assignments.')
    if total_images > 0:
        notes.append(f'Images: {total_images} total, {missing_alt} missing alt text (QM 8.4).')
    if bad_link_text > 0:
        notes.append(f'Non-descriptive link text found {bad_link_text} time(s) (QM 8.3).')
    if heading_skips > 0:
        notes.append(f'Heading hierarchy skipped {heading_skips} time(s) (QM 8.2).')

    for note in notes:
        L.append(f'- {note}')
    L += ['', '---']

    # Appendix: QM Reference
    L += ['', '## APPENDIX: QM 7TH EDITION RUBRIC REFERENCE', '']
    L += _qm_reference_appendix()
    L += ['', '---', f'*CeCe Course DNA Document v6.1 — Generated {today}*']

    return '\n'.join(L)


def _qm_reference_appendix():
    L = []
    standards = [
        ('### GS 1: Course Overview and Introduction (16 pts)', [
            ('1.1','Essential (3)','Instructions make clear how to get started'),
            ('1.2','Essential (3)','Learners introduced to purpose and structure'),
            ('1.3','Very Important (2)','Communication guidelines clearly stated'),
            ('1.4','Very Important (2)','Course and institutional policies clearly stated'),
            ('1.5','Very Important (2)','Minimum technology requirements stated'),
            ('1.6','Important (1)','Digital skills expected of learner stated'),
            ('1.7','Important (1)','Required knowledge/competencies stated'),
            ('1.8','Important (1)','Instructor self-introduction available'),
            ('1.9','Important (1)','Learners can introduce themselves'),
        ]),
        ('### GS 2: Learning Objectives (15 pts, ALL Essential)', [
            ('2.1','Essential (3)','Course-level objectives are measurable'),
            ('2.2','Essential (3)','Module-level objectives are measurable'),
            ('2.3','Essential (3)','Objectives clearly stated and consistent'),
            ('2.4','Essential (3)','Relationship between objectives and activities stated'),
            ('2.5','Essential (3)','Objectives suited to course level'),
        ]),
        ('### GS 3: Assessment and Measurement (14 pts)', [
            ('3.1','Essential (3)','Assessments measure stated objectives'),
            ('3.2','Essential (3)','Grading policy stated clearly'),
            ('3.3','Essential (3)','Specific evaluation criteria provided'),
            ('3.4','Very Important (2)','Multiple opportunities to track progress'),
            ('3.5','Very Important (2)','Assessments sequenced and varied'),
            ('3.6','Important (1)','Academic integrity guidance in assessments'),
        ]),
        ('### GS 4: Instructional Materials (12 pts)', [
            ('4.1','Essential (3)','Materials contribute to objectives'),
            ('4.2','Essential (3)','Relationship between materials and activities explained'),
            ('4.3','Very Important (2)','Course models academic integrity'),
            ('4.4','Very Important (2)','Materials represent current thinking'),
            ('4.5','Very Important (2)','Variety of instructional materials'),
        ]),
        ('### GS 5: Learning Activities and Interaction (11 pts)', [
            ('5.1','Essential (3)','Activities promote achievement of objectives'),
            ('5.2','Essential (3)','Interaction opportunities support active learning'),
            ('5.3','Essential (3)','Instructor feedback plan clearly stated'),
            ('5.4','Very Important (2)','Learner interaction requirements articulated'),
        ]),
        ('### GS 6: Course Technology (7 pts)', [
            ('6.1','Essential (3)','Tools support learning objectives'),
            ('6.2','Very Important (2)','Tools promote engagement'),
            ('6.3','Important (1)','Variety of technology tools'),
            ('6.4','Important (1)','Data privacy information provided'),
        ]),
        ('### GS 7: Learner Support (10 pts)', [
            ('7.1','Essential (3)','Technical support instructions'),
            ('7.2','Essential (3)','Accessibility policies and services'),
            ('7.3','Essential (3)','Academic support services'),
            ('7.4','Important (1)','Student services'),
        ]),
        ('### GS 8: Accessibility and Usability (16 pts)', [
            ('8.1','Essential (3)','Navigation facilitates ease of use'),
            ('8.2','Essential (3)','Design facilitates readability'),
            ('8.3','Essential (3)','Text is accessible'),
            ('8.4','Very Important (2)','Images are accessible'),
            ('8.5','Very Important (2)','Video and audio accessible'),
            ('8.6','Very Important (2)','Multimedia is accessible'),
            ('8.7','Important (1)','Vendor accessibility info provided'),
        ]),
    ]
    for header, stds in standards:
        L += [header, '', '| SRS | Weight | Standard |', '|-----|--------|----------|']
        for sid, weight, text in stds:
            L.append(f'| {sid} | {weight} | {text} |')
        L += ['', '']
    L += ['**Scoring:** All Essential standards must be Met. 85% of total points (86/101) required.', '']
    return L


# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────

def main():
    print('\n' + '='*60)
    print('  CeCe Course DNA Extraction Agent v6.1')
    print('='*60)
    if len(sys.argv) < 2:
        print('\nUsage:  python analyze.py your-course.imscc')
        sys.exit(1)
    imscc_path = sys.argv[1]
    if not os.path.exists(imscc_path):
        print(f'\n❌ File not found: {imscc_path}')
        sys.exit(1)
    syl_text = ''
    if '--syllabus' in sys.argv:
        idx = sys.argv.index('--syllabus') + 1
        if idx < len(sys.argv) and os.path.exists(sys.argv[idx]):
            with open(sys.argv[idx], 'r', encoding='utf-8', errors='ignore') as f:
                syl_text = f.read()

    data     = read_imscc(imscc_path, syllabus_text=syl_text)
    identity = extract_course_identity(data)
    modules  = extract_modules(data)
    grading  = extract_grading_structure(data)
    rubrics  = extract_rubrics(data)
    document = build_course_dna(data, identity, modules, grading, rubrics)

    base = os.path.splitext(os.path.basename(imscc_path))[0]
    out_path = f'{base}_dna.md'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(document)
    print(f'\n✅ Course DNA Document saved to: {out_path}')
    print(f'   Length: {len(document):,} characters')


if __name__ == '__main__':
    main()
