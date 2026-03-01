"""
build.py — CeCe Course Builder Agent v1.0
Reads a filled Blueprint Document (.md) and generates a Canvas-importable
IMSCC file.

Usage:
    python build.py blueprint.md
    python build.py blueprint.md --output my-course.imscc
"""

import re
import os
import sys
import uuid
import zipfile
import hashlib
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────
#  ID GENERATION
#  Canvas uses 'g' + 32-char hex as identifiers throughout its XML
# ─────────────────────────────────────────────────────────────────────

def make_id(seed=None):
    """Generate a Canvas-style identifier: 'g' + 32 hex chars."""
    if seed:
        h = hashlib.md5(str(seed).encode()).hexdigest()
    else:
        h = uuid.uuid4().hex
    return f"g{h}"


def slugify(text):
    """Convert a title to a URL-safe slug for wiki page filenames."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text[:60]


# ─────────────────────────────────────────────────────────────────────
#  BLUEPRINT PARSER
# ─────────────────────────────────────────────────────────────────────

def parse_blueprint(md_text):
    """
    Parse a filled CeCe Blueprint Document into a structured dict.
    Tolerant of LLM formatting variations.
    """
    bp = {
        'course':      {},
        'clos':        [],
        'schedule':    [],
        'grading':     [],
        'modules':     [],
        'assignments': [],
        'policies':    {},
        'tools':       [],
        'build':       {},
    }

    # ── Split into top-level sections ──────────────────────────────
    # Split on ## SECTION headers
    section_pattern = re.compile(r'^## SECTION \d+[:\s]', re.MULTILINE)
    section_splits  = section_pattern.split(md_text)
    section_headers = section_pattern.findall(md_text)

    sections = {}
    for i, header in enumerate(section_headers):
        num_match = re.search(r'\d+', header)
        if num_match:
            num = int(num_match.group())
            sections[num] = section_splits[i + 1] if i + 1 < len(section_splits) else ''

    # ── Section 1: Course Identity ─────────────────────────────────
    if 1 in sections:
        bp['course'] = _parse_identity_table(sections[1])

    # ── Section 2: CLOs ────────────────────────────────────────────
    if 2 in sections:
        bp['clos'] = _parse_clos(sections[2])

    # ── Section 3: Course Schedule ────────────────────────────────
    if 3 in sections:
        bp['schedule'] = _parse_schedule(sections[3])

    # ── Section 4: Grading ─────────────────────────────────────────
    if 4 in sections:
        bp['grading'] = _parse_grading_table(sections[4])

    # ── Section 5: Modules ─────────────────────────────────────────
    if 5 in sections:
        bp['modules'] = _parse_modules(sections[5])

    # ── Section 6: Assignments ─────────────────────────────────────
    if 6 in sections:
        bp['assignments'] = _parse_assignments(sections[6])

    # ── Section 7: Policies ────────────────────────────────────────
    if 7 in sections:
        bp['policies'] = _parse_policies(sections[7])

    # ── Section 8: Tools ───────────────────────────────────────────
    if 8 in sections:
        bp['tools'] = _parse_tools_table(sections[8])

    # ── Section 10: Build instructions ────────────────────────────
    if 10 in sections:
        bp['build'] = _parse_build(sections[10])

    return bp


# ── Field extraction helpers ───────────────────────────────────────

def _field(text, label, default=''):
    """
    Extract the value after **Label:** in a block of text.
    Returns everything up to the next **bold:** field or section break.
    """
    pattern = rf'\*\*{re.escape(label)}[:\*]+\s*(.*?)(?=\n\*\*|\n##|\n---|\Z)'
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        val = match.group(1).strip()
        # Remove markdown quote markers and excess whitespace
        val = re.sub(r'^>\s*', '', val, flags=re.MULTILINE).strip()
        return val if val and val not in ('{{'+label.upper().replace(' ','_')+'}}', 'None', 'N/A') else default
    return default


def _parse_md_table(text):
    """Parse a markdown table into a list of dicts keyed by header."""
    rows   = []
    lines  = [l.strip() for l in text.strip().splitlines() if l.strip().startswith('|')]
    if len(lines) < 2:
        return rows
    headers = [h.strip() for h in lines[0].strip('|').split('|')]
    for line in lines[2:]:  # skip header and separator
        cells = [c.strip() for c in line.strip('|').split('|')]
        if len(cells) >= len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows


def _parse_identity_table(text):
    rows     = _parse_md_table(text)
    identity = {}
    for row in rows:
        field = row.get('Field', '').strip()
        value = row.get('Value', '').strip()
        if field and value and '{{' not in value:
            identity[field] = value
    return identity


def _parse_schedule(text):
    """Parse the week-by-week schedule table in Section 3."""
    rows = []
    for row in _parse_md_table(text):
        week_raw = row.get('Week', '').strip()
        if not week_raw or '---' in week_raw:
            continue
        m = re.search(r'\d+', week_raw)
        if not m:
            continue
        rows.append({
            'week':   int(m.group()),
            'topic':  row.get('Topic / Focus', row.get('Topic', '')).strip(),
            'module': row.get('Module', '').strip(),
            'due':    row.get('Due This Week', '').strip(),
            'notes':  row.get('Notes', '').strip(),
        })
    return rows


def resolve_relative_date(week_num, day_str, start_date_str):
    """
    Convert a relative date (Week N, Day) to an absolute date.
    week_num:       int  — 1-based week number
    day_str:        str  — 'Mon','Tue','Wed','Thu','Fri','Sat','Sun'
    start_date_str: str  — 'YYYY-MM-DD' of the Monday of Week 1
    Returns datetime.date or None on parse failure.
    """
    from datetime import date, timedelta
    DAY_MAP = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3,
               'fri': 4, 'sat': 5, 'sun': 6}
    try:
        start = date.fromisoformat(start_date_str)
    except (ValueError, TypeError):
        return None
    day_offset = DAY_MAP.get(day_str.strip().lower()[:3])
    if day_offset is None:
        return None
    return start + timedelta(days=(week_num - 1) * 7 + day_offset)


def resolve_all_dates(bp):
    """
    Walk every assignment and module in the blueprint and resolve
    relative dates (Week N, Day) to absolute ISO dates using the
    course start date from Section 1.
    Adds *_absolute keys alongside the original relative values.
    """
    start_date = bp['course'].get('Course Start Date', '').strip()
    if not start_date or start_date.startswith('{{'):
        return

    REL = re.compile(r'[Ww]eek\s*(\d+)[,\s]+([A-Za-z]+)')

    def resolve(val):
        m = REL.search(str(val))
        if not m:
            return ''
        r = resolve_relative_date(int(m.group(1)), m.group(2), start_date)
        return r.isoformat() if r else ''

    for a in bp.get('assignments', []):
        a['due_absolute']            = resolve(a.get('due_date', ''))
        a['available_from_absolute'] = resolve(a.get('available_from', ''))
        a['until_absolute']          = resolve(a.get('until', ''))

    for mod in bp.get('modules', []):
        mod['opens_absolute']  = resolve(mod.get('opens', ''))
        mod['closes_absolute'] = resolve(mod.get('closes', ''))


def _parse_clos(text):
    clos = []
    # Match lines like: CLO-1 | Apply | Students will...
    for line in text.splitlines():
        line = line.strip().lstrip('-•* ')
        match = re.match(
            r'(CLO-?\d+)\s*\|\s*(\w+)\s*\|\s*(.+)',
            line, re.IGNORECASE
        )
        if match:
            clos.append({
                'id':     match.group(1).strip().upper(),
                'blooms': match.group(2).strip(),
                'text':   match.group(3).strip(),
            })
    return clos


def _parse_grading_table(text):
    rows   = _parse_md_table(text)
    groups = []
    for row in rows:
        name = (row.get('Group Name') or row.get('Group') or '').strip()
        if not name or '{{' in name:
            continue
        weight_raw = (row.get('Weight (%)') or row.get('Weight') or '0').strip().replace('%','')
        try:
            weight = float(weight_raw)
        except ValueError:
            weight = 0.0
        drop_raw = (row.get('Drop Lowest N') or row.get('Drop Lowest') or '0').strip()
        try:
            drop = int(drop_raw)
        except ValueError:
            drop = 0
        groups.append({
            'name':   name,
            'weight': weight,
            'drop':   drop,
            'notes':  (row.get('Notes') or '').strip(),
        })
    return groups


def _parse_modules(text):
    """Split on ### MODULE: blocks and parse each."""
    modules = []
    # Split on module headers
    blocks = re.split(r'###\s+MODULE\s*[:：]\s*', text, flags=re.IGNORECASE)
    for block in blocks[1:]:
        # First line is "N — Title" or just "Title"
        first_line = block.splitlines()[0].strip()
        num_match  = re.match(r'(\d+)\s*[—\-–]\s*(.+)', first_line)
        if num_match:
            mod_num   = int(num_match.group(1))
            mod_title = num_match.group(2).strip()
        else:
            mod_num   = len(modules) + 1
            mod_title = first_line.strip('*').strip()

        # Extract availability window  e.g. "Opens: Week 1, Mon"
        opens_m  = re.search(r'Opens\s*:\s*(.+)',  block, re.IGNORECASE)
        closes_m = re.search(r'Closes\s*:\s*(.+)', block, re.IGNORECASE)

        mod = {
            'number':      mod_num,
            'title':       mod_title,
            'opens':       opens_m.group(1).strip()  if opens_m  else '',
            'closes':      closes_m.group(1).strip() if closes_m else '',
            'overview':    _field(block, 'Overview Text'),
            'mlos':        _parse_mlos(block),
            'assignments': _parse_list_field(block, 'Assignments in This Module'),
            'materials':   _parse_list_field(block, 'Instructional Materials'),
            'discussion':  _field(block, 'Discussion / Reflection Prompt'),
            'agent_notes': _field(block, 'Notes for DeDe') or _field(block, 'Notes for Agent'),
        }
        modules.append(mod)
    return modules


def _parse_mlos(text):
    mlos = []
    mlo_section = re.search(
        r'\*\*Module Learning Objectives[:\*]+\s*(.*?)(?=\n\*\*|\n##|\Z)',
        text, re.DOTALL | re.IGNORECASE
    )
    if not mlo_section:
        return mlos
    for line in mlo_section.group(1).splitlines():
        line = line.strip().lstrip('-•*> ')
        match = re.match(
            r'(MLO-?\d+(?:\.\d+)?)\s*\|\s*(\w+)\s*\|\s*(.+?)\s*\|\s*(CLO-[\d,\s]+)',
            line, re.IGNORECASE
        )
        if match:
            mlos.append({
                'id':     match.group(1).strip().upper(),
                'blooms': match.group(2).strip(),
                'text':   match.group(3).strip(),
                'maps_to':match.group(4).strip(),
            })
        else:
            # Try without CLO mapping
            match2 = re.match(r'(MLO-?\d+)\s*\|\s*(\w+)\s*\|\s*(.+)', line, re.IGNORECASE)
            if match2:
                mlos.append({
                    'id':     match2.group(1).strip().upper(),
                    'blooms': match2.group(2).strip(),
                    'text':   match2.group(3).strip(),
                    'maps_to':'',
                })
    return mlos


def _parse_list_field(text, label):
    """Extract a bulleted list under a **Label:** field."""
    pattern = rf'\*\*{re.escape(label)}[:\*]+\s*(.*?)(?=\n\*\*|\n##|\n---|\Z)'
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if not match:
        return []
    items = []
    for line in match.group(1).splitlines():
        line = line.strip().lstrip('-•*>0123456789.) ')
        if line and '{{' not in line and line.lower() not in ('none', 'n/a', ''):
            items.append(line)
    return items


def _parse_assignments(text):
    """Split on ### ASSIGNMENT: blocks and parse each."""
    assignments = []
    blocks = re.split(r'###\s+ASSIGNMENT\s*[:：]\s*', text, flags=re.IGNORECASE)
    for block in blocks[1:]:
        title = block.splitlines()[0].strip().strip('*')
        if not title or '{{' in title:
            continue

        # Parse rubric table
        rubric_rows = []
        rubric_match = re.search(r'\*\*Rubric[:\*]+(.*?)(?=\n\*\*Alignment|\n---|\Z)',
                                  block, re.DOTALL | re.IGNORECASE)
        if rubric_match:
            rubric_rows = _parse_md_table(rubric_match.group(1))

        assignment = {
            'title':          title,
            'module':         _field(block, 'Belongs To Module'),
            'group':          _field(block, 'Assignment Group'),
            'points':         _field(block, 'Points Possible', '0'),
            'due_date':       _field(block, 'Due'),
            'available_from': _field(block, 'Available From'),
            'until':          _field(block, 'Until'),
            # Absolute dates populated later by resolve_all_dates()
            'due_absolute':            '',
            'available_from_absolute': '',
            'until_absolute':          '',
            'sub_type':       _field(block, 'Submission Type', 'online_upload'),
            'purpose':        _field(block, 'Purpose Statement'),
            'instructions':   _field(block, 'Instructions'),
            'rubric':         rubric_rows,
            'clo_align':      _field(block, 'Maps to CLOs'),
            'mlo_align':      _field(block, 'Maps to MLOs'),
            'fink':           _field(block, "Fink's Category"),
            'integrity':      _field(block, 'Academic Integrity Notes'),
        }
        assignments.append(assignment)
    return assignments


def _parse_policies(text):
    fields = [
        'Course Description', 'Instructor Information', 'Required Materials',
        'Attendance & Participation Policy', 'Late Work Policy',
        'Academic Integrity Policy', 'Accessibility Statement',
        'Additional Policies',
    ]
    return {f: _field(text, f) for f in fields}


def _parse_visual(text):
    colors = {}
    color_table = re.search(r'\*\*Color Palette[:\*]+(.*?)(?=\n\*\*|\n---|\Z)',
                             text, re.DOTALL | re.IGNORECASE)
    if color_table:
        for row in _parse_md_table(color_table.group(1)):
            element = row.get('Element','').strip()
            hex_val = row.get('Hex Code','').strip()
            if element and hex_val and '{{' not in hex_val:
                colors[element.lower()] = hex_val

    return {
        'header_style': _field(text, 'Header Style'),
        'colors':       colors,
        'fonts':        _field(text, 'Font Preferences'),
        'banner_notes': _field(text, 'Banner / Hero Image Notes'),
        'icon_style':   _field(text, 'Icon or Graphic Style'),
        'design_notes': _field(text, 'Special Design Notes'),
    }


def _parse_tools_table(text):
    rows  = _parse_md_table(text)
    tools = []
    for row in rows:
        name = (row.get('Tool Name') or row.get('Tool') or '').strip()
        if name and '{{' not in name:
            tools.append({
                'name':     name,
                'purpose':  (row.get('Purpose') or '').strip(),
                'required': (row.get('Required or Optional') or row.get('Required or Optional') or '').strip(),
                'notes':    (row.get('Notes') or '').strip(),
            })
    return tools


def _parse_build(text):
    mode_match = re.search(r'\*\*Build Mode[:\*]+\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    mode = 'FULL BUILD'
    if mode_match:
        raw = mode_match.group(1).strip()
        if 'UPDATE' in raw.upper():
            mode = 'UPDATE'
        elif 'STYLE' in raw.upper():
            mode = 'STYLE ONLY'

    return {
        'mode':         mode,
        'preserve':     _parse_list_field(text, 'Preserve From Original'),
        'delete':       _parse_list_field(text, 'Delete From Original'),
        'special_notes':_field(text, 'Special Build Notes'),
    }


# ─────────────────────────────────────────────────────────────────────
#  HTML CONTENT GENERATOR
#  Produces styled HTML for wiki pages and assignment pages
# ─────────────────────────────────────────────────────────────────────

def _html_wrap(title, body, visual=None):
    """Wrap content in a styled HTML page. Visual styling applied by DeDe."""
    visual     = visual or {}
    primary    = visual.get('colors', {}).get('primary',    '#2c3e50')
    secondary  = visual.get('colors', {}).get('secondary',  '#3498db')
    accent     = visual.get('colors', {}).get('accent',     '#e74c3c')
    bg         = visual.get('colors', {}).get('background', '#ffffff')
    text_color = visual.get('colors', {}).get('text',       '#333333')

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8"/>
<title>{title}</title>
<style>
  body {{
    font-family: 'Segoe UI', Arial, sans-serif;
    color: {text_color};
    background: {bg};
    max-width: 860px;
    margin: 0 auto;
    padding: 0 1rem 2rem 1rem;
    line-height: 1.6;
  }}
  .page-header {{
    background: {primary};
    color: white;
    padding: 1.5rem 2rem;
    border-radius: 0 0 8px 8px;
    margin-bottom: 2rem;
  }}
  .page-header h1 {{
    margin: 0;
    font-size: 1.6rem;
    font-weight: 700;
  }}
  h2 {{ color: {primary}; border-bottom: 2px solid {secondary}; padding-bottom: 4px; }}
  h3 {{ color: {secondary}; }}
  .objective-block {{
    background: #f8f9fa;
    border-left: 4px solid {accent};
    padding: 0.75rem 1rem;
    margin: 0.5rem 0;
    border-radius: 0 6px 6px 0;
  }}
  .materials-list li {{ margin: 0.4rem 0; }}
  .info-box {{
    background: #eef6ff;
    border: 1px solid {secondary};
    border-radius: 8px;
    padding: 1rem 1.2rem;
    margin: 1rem 0;
  }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th {{ background: {primary}; color: white; padding: 8px 12px; text-align: left; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #ddd; }}
  tr:nth-child(even) td {{ background: #f9f9f9; }}
</style>
</head>
<body>
<div class="page-header"><h1>{title}</h1></div>
{body}
</body>
</html>"""


def _make_module_overview_html(mod, visual):
    """Generate the HTML for a module overview page."""
    body_parts = []

    if mod.get('overview'):
        body_parts.append(f"<p>{mod['overview']}</p>")

    if mod.get('mlos'):
        body_parts.append("<h2>Module Learning Objectives</h2>")
        body_parts.append("<p>By the end of this module, you will be able to:</p>")
        for mlo in mod['mlos']:
            body_parts.append(
                f'<div class="objective-block">'
                f'<strong>{mlo["id"]}</strong> ({mlo["blooms"]}) — {mlo["text"]}'
                f'</div>'
            )

    if mod.get('materials'):
        body_parts.append("<h2>Instructional Materials</h2><ul class='materials-list'>")
        for mat in mod['materials']:
            body_parts.append(f"<li>{mat}</li>")
        body_parts.append("</ul>")

    if mod.get('assignments'):
        body_parts.append("<h2>Assignments</h2><ul>")
        for a in mod['assignments']:
            body_parts.append(f"<li>{a}</li>")
        body_parts.append("</ul>")

    if mod.get('discussion'):
        body_parts.append(
            f'<h2>Discussion / Reflection</h2>'
            f'<div class="info-box">{mod["discussion"]}</div>'
        )

    return _html_wrap(mod['title'], '\n'.join(body_parts), visual)


def _make_assignment_html(assignment, visual):
    """Generate the HTML for an assignment instructions page."""
    body_parts = []

    # Info box: points, due, submission type
    points  = assignment.get('points', 'TBD')
    due     = assignment.get('due', 'See course schedule')
    sub     = assignment.get('sub_type', '')
    body_parts.append(
        f'<div class="info-box">'
        f'<strong>Points:</strong> {points} &nbsp;|&nbsp; '
        f'<strong>Due:</strong> {due} &nbsp;|&nbsp; '
        f'<strong>Submission:</strong> {sub}'
        f'</div>'
    )

    if assignment.get('purpose'):
        body_parts.append(f'<p><em>{assignment["purpose"]}</em></p>')

    if assignment.get('instructions'):
        body_parts.append('<h2>Instructions</h2>')
        # Convert simple newlines to paragraphs
        for para in assignment['instructions'].split('\n\n'):
            para = para.strip()
            if para:
                body_parts.append(f'<p>{para}</p>')

    if assignment.get('rubric'):
        body_parts.append('<h2>Grading Rubric</h2>')
        body_parts.append('<table>')
        if assignment['rubric']:
            headers = list(assignment['rubric'][0].keys())
            body_parts.append('<tr>' + ''.join(f'<th>{h}</th>' for h in headers) + '</tr>')
            for row in assignment['rubric']:
                body_parts.append('<tr>' + ''.join(f'<td>{v}</td>' for v in row.values()) + '</tr>')
        body_parts.append('</table>')

    if assignment.get('clo_align') or assignment.get('fink'):
        body_parts.append('<h2>Alignment</h2><ul>')
        if assignment.get('clo_align'):
            body_parts.append(f'<li><strong>Course Objectives:</strong> {assignment["clo_align"]}</li>')
        if assignment.get('mlo_align'):
            body_parts.append(f'<li><strong>Module Objectives:</strong> {assignment["mlo_align"]}</li>')
        if assignment.get('fink'):
            body_parts.append(f'<li><strong>Fink\'s Category:</strong> {assignment["fink"]}</li>')
        body_parts.append('</ul>')

    return _html_wrap(assignment['title'], '\n'.join(body_parts), visual)


def _make_syllabus_html(policies, course, visual):
    """Generate the Canvas syllabus page HTML."""
    body_parts = []

    desc = policies.get('Course Description','')
    if desc:
        body_parts.append(f'<h2>Course Description</h2><p>{desc}</p>')

    instructor = policies.get('Instructor Information','')
    if instructor:
        body_parts.append(f'<h2>Instructor Information</h2>'
                          f'<div class="info-box">{instructor}</div>')

    materials = policies.get('Required Materials','')
    if materials:
        body_parts.append(f'<h2>Required Materials</h2><p>{materials}</p>')

    for label, field in [
        ('Attendance & Participation', 'Attendance & Participation Policy'),
        ('Late Work Policy',           'Late Work Policy'),
        ('Academic Integrity',         'Academic Integrity Policy'),
        ('Accessibility Statement',    'Accessibility Statement'),
        ('Additional Policies',        'Additional Policies'),
    ]:
        val = policies.get(field,'')
        if val:
            body_parts.append(f'<h2>{label}</h2><p>{val}</p>')

    title = f"{course.get('Course Code','')} — {course.get('Course Title','')}"
    return _html_wrap(title, '\n'.join(body_parts), visual)


# ─────────────────────────────────────────────────────────────────────
#  IMSCC XML GENERATORS
# ─────────────────────────────────────────────────────────────────────

CANVAS_NS = 'http://canvas.instructure.com/xsd/cccv1p0'

def _xml_header():
    return '<?xml version="1.0" encoding="UTF-8"?>\n'


def _make_course_settings_xml(bp):
    course  = bp['course']
    title   = course.get('Course Code', 'Untitled Course')
    code    = course.get('Course Title', '')
    today   = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    cid     = make_id(title + code)

    return _xml_header() + f'''<course identifier="{cid}"
  xmlns="{CANVAS_NS}"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="{CANVAS_NS} https://canvas.instructure.com/xsd/cccv1p0.xsd">
  <title>{_xml_escape(title)}</title>
  <course_code>{_xml_escape(code)}</course_code>
  <start_at>{today}</start_at>
  <is_public>false</is_public>
  <indexed>false</indexed>
  <hide_final_grade>false</hide_final_grade>
  <storage_quota/>
</course>'''


def _make_assignment_groups_xml(bp):
    groups = bp['grading']
    lines  = [
        _xml_header(),
        f'<assignmentGroups xmlns="{CANVAS_NS}"',
        '  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        f'  xsi:schemaLocation="{CANVAS_NS} https://canvas.instructure.com/xsd/cccv1p0.xsd">',
    ]
    for i, g in enumerate(groups, 1):
        gid = make_id(g['name'])
        lines.append(f'  <assignmentGroup identifier="{gid}">')
        lines.append(f'    <title>{_xml_escape(g["name"])}</title>')
        lines.append(f'    <position>{i}</position>')
        lines.append(f'    <group_weight>{g["weight"]}</group_weight>')
        if g.get('drop', 0) > 0:
            lines.append('    <rules>')
            lines.append('      <rule>')
            lines.append('        <drop_type>drop_lowest</drop_type>')
            lines.append(f'        <drop_count>{g["drop"]}</drop_count>')
            lines.append('      </rule>')
            lines.append('    </rules>')
        lines.append('  </assignmentGroup>')
    lines.append('</assignmentGroups>')
    return '\n'.join(lines)


def _make_module_meta_xml(bp, resource_map):
    """
    Build module_meta.xml.
    resource_map: dict mapping item titles to their Canvas identifier refs
    """
    lines = [
        _xml_header(),
        f'<modules xmlns="{CANVAS_NS}"',
        '  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        f'  xsi:schemaLocation="{CANVAS_NS} https://canvas.instructure.com/xsd/cccv1p0.xsd">',
    ]

    for pos, mod in enumerate(bp['modules'], 1):
        mid = make_id(f"module_{mod['title']}")
        lines.append(f'  <module identifier="{mid}">')
        lines.append(f'    <title>{_xml_escape(mod["title"])}</title>')
        lines.append(f'    <workflow_state>active</workflow_state>')
        lines.append(f'    <position>{pos}</position>')
        lines.append(f'    <require_sequential_progress>false</require_sequential_progress>')
        lines.append(f'    <locked>false</locked>')
        lines.append(f'    <items>')

        item_pos = 1

        # Module overview page
        overview_title = f"{mod['title']} — Overview"
        overview_ref   = resource_map.get(overview_title, make_id(overview_title))
        iid = make_id(f"item_overview_{mod['title']}")
        lines += [
            f'      <item identifier="{iid}">',
            f'        <content_type>WikiPage</content_type>',
            f'        <workflow_state>active</workflow_state>',
            f'        <title>{_xml_escape(overview_title)}</title>',
            f'        <identifierref>{overview_ref}</identifierref>',
            f'        <position>{item_pos}</position>',
            f'      </item>',
        ]
        item_pos += 1

        # Assignments belonging to this module
        for assign in bp['assignments']:
            if _module_match(assign.get('module',''), mod['title'], mod['number']):
                assign_ref = resource_map.get(assign['title'], make_id(assign['title']))
                iid2 = make_id(f"item_assign_{assign['title']}")
                lines += [
                    f'      <item identifier="{iid2}">',
                    f'        <content_type>Assignment</content_type>',
                    f'        <workflow_state>active</workflow_state>',
                    f'        <title>{_xml_escape(assign["title"])}</title>',
                    f'        <identifierref>{assign_ref}</identifierref>',
                    f'        <position>{item_pos}</position>',
                    f'      </item>',
                ]
                item_pos += 1

        lines.append(f'    </items>')
        lines.append(f'  </module>')

    lines.append('</modules>')
    return '\n'.join(lines)


def _make_assignment_settings_xml(assignment, assign_id, group_id):
    """Build assignment_settings.xml for one assignment."""
    points   = assignment.get('points', '0')
    try:
        float(points)
    except (ValueError, TypeError):
        points = '0'

    sub_type = _normalize_submission_type(assignment.get('sub_type', ''))
    title    = assignment.get('title', 'Assignment')

    return _xml_header() + f'''<assignment identifier="{assign_id}"
  xmlns="{CANVAS_NS}"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="{CANVAS_NS} https://canvas.instructure.com/xsd/cccv1p0.xsd">
  <title>{_xml_escape(title)}</title>
  <workflow_state>published</workflow_state>
  <points_possible>{points}</points_possible>
  <grading_type>points</grading_type>
  <submission_types>{sub_type}</submission_types>
  <assignment_group_identifierref>{group_id}</assignment_group_identifierref>
  <peer_reviews>false</peer_reviews>
  <automatic_peer_reviews>false</automatic_peer_reviews>
  <anonymous_submissions>false</anonymous_submissions>
  <grade_group_students_individually>false</grade_group_students_individually>
</assignment>'''


def _make_rubrics_xml(bp):
    """Build rubrics.xml from all assignment rubrics in the blueprint."""
    lines = [
        _xml_header(),
        f'<rubrics xmlns="{CANVAS_NS}"',
        '  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        f'  xsi:schemaLocation="{CANVAS_NS} https://canvas.instructure.com/xsd/cccv1p0.xsd">',
    ]

    for assignment in bp['assignments']:
        if not assignment.get('rubric'):
            continue
        rid = make_id(f"rubric_{assignment['title']}")
        lines.append(f'  <rubric identifier="{rid}">')
        lines.append(f'    <title>{_xml_escape(assignment["title"])} Rubric</title>')
        lines.append(f'    <criteria>')

        for row in assignment['rubric']:
            crit_desc   = list(row.values())[0] if row else ''
            points_val  = list(row.values())[-1] if row else '0'
            try:
                float(points_val)
            except (ValueError, TypeError):
                points_val = '0'
            cid2 = make_id(f"crit_{assignment['title']}_{crit_desc}")
            lines += [
                f'      <criterion identifier="{cid2}">',
                f'        <description>{_xml_escape(crit_desc)}</description>',
                f'        <points>{points_val}</points>',
                f'      </criterion>',
            ]

        lines.append(f'    </criteria>')
        lines.append(f'  </rubric>')

    lines.append('</rubrics>')
    return '\n'.join(lines)


def _make_manifest(resources):
    """
    Build imsmanifest.xml from a list of resource dicts:
    [{'id': str, 'type': str, 'href': str}]
    """
    lines = [
        _xml_header(),
        '<manifest identifier="' + make_id('manifest') + '"',
        '  xmlns="http://www.imsglobal.org/xsd/imsccv1p3/imscp_v1p1"',
        '  xmlns:lom="http://ltsc.ieee.org/xsd/imsccv1p3/LOM/manifest"',
        '  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        '  xsi:schemaLocation="http://www.imsglobal.org/xsd/imsccv1p3/imscp_v1p1',
        '    http://www.imsglobal.org/profile/cc/ccv1p3/ccv1p3_imscp_v1p2_v1p0.xsd">',
        '  <metadata>',
        '    <schema>IMS Common Cartridge</schema>',
        '    <schemaversion>1.3.0</schemaversion>',
        '  </metadata>',
        '  <organizations/>',
        '  <resources>',
    ]

    for res in resources:
        lines.append(f'    <resource identifier="{res["id"]}" type="{res["type"]}" href="{res["href"]}">')
        lines.append(f'      <file href="{res["href"]}"/>')
        lines.append(f'    </resource>')

    lines += ['  </resources>', '</manifest>']
    return '\n'.join(lines)


# ─────────────────────────────────────────────────────────────────────
#  UTILITIES
# ─────────────────────────────────────────────────────────────────────

def _xml_escape(text):
    if not text:
        return ''
    return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&apos;'))


def _normalize_submission_type(raw):
    raw = raw.lower()
    if 'file' in raw:         return 'online_upload'
    if 'text' in raw:         return 'online_text_entry'
    if 'url' in raw:          return 'online_url'
    if 'media' in raw:        return 'media_recording'
    if 'discussion' in raw:   return 'discussion_topic'
    if 'no submission' in raw: return 'not_graded'
    return 'online_text_entry'


def _module_match(assign_module_str, mod_title, mod_number):
    """Check if an assignment's module field matches a given module."""
    if not assign_module_str:
        return False
    s = assign_module_str.lower()
    if str(mod_number) in s:
        return True
    # Check first 3 significant words of module title
    words = [w for w in mod_title.lower().split() if len(w) > 3][:3]
    return any(w in s for w in words)


def _find_group_id(group_name, groups, group_id_map):
    """Return the Canvas identifier for a grading group by name."""
    name_lower = group_name.lower()
    for g in groups:
        if g['name'].lower() in name_lower or name_lower in g['name'].lower():
            return group_id_map.get(g['name'], make_id(g['name']))
    # Fallback: return first group
    if groups:
        return group_id_map.get(groups[0]['name'], make_id(groups[0]['name']))
    return make_id('default_group')


# ─────────────────────────────────────────────────────────────────────
#  IMSCC BUILDER — main entry point
# ─────────────────────────────────────────────────────────────────────

def build_imscc(bp, output_path):
    """
    Generate a complete Canvas-importable IMSCC file from a parsed blueprint.
    """
    resources    = []   # for imsmanifest.xml
    resource_map = {}   # title → identifier (for module_meta cross-referencing)

    # Pre-build group ID map so assignments can reference groups
    group_id_map = {g['name']: make_id(g['name']) for g in bp['grading']}

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:

        # ── course_settings/ ──────────────────────────────────────
        zf.writestr('course_settings/course_settings.xml',
                    _make_course_settings_xml(bp))
        zf.writestr('course_settings/assignment_groups.xml',
                    _make_assignment_groups_xml(bp))
        zf.writestr('course_settings/rubrics.xml',
                    _make_rubrics_xml(bp))

        # Canvas export marker
        zf.writestr('course_settings/canvas_export.txt',
                    f'Generated by CeCe Course Builder v1.0\n{datetime.now().isoformat()}')

        # ── Syllabus page ─────────────────────────────────────────
        syllabus_html = _make_syllabus_html(bp['policies'], bp['course'], bp.get('visual', {}))
        zf.writestr('course_settings/syllabus.html', syllabus_html)

        # ── Module overview wiki pages ────────────────────────────
        for mod in bp['modules']:
            overview_title = f"{mod['title']} — Overview"
            slug           = slugify(overview_title)
            href           = f'wiki_content/{slug}.html'
            res_id         = make_id(f"wiki_{slug}")
            resource_map[overview_title] = res_id

            html = _make_module_overview_html(mod, bp.get('visual', {}))
            zf.writestr(href, html)
            resources.append({'id': res_id, 'type': 'webcontent', 'href': href})

        # ── Assignment pages ──────────────────────────────────────
        for assignment in bp['assignments']:
            assign_id  = make_id(f"assign_{assignment['title']}")
            folder     = assign_id
            slug       = slugify(assignment['title'])
            html_href  = f'{folder}/{slug}.html'
            xml_href   = f'{folder}/assignment_settings.xml'

            resource_map[assignment['title']] = assign_id

            # Find the grading group ID
            group_id = _find_group_id(
                assignment.get('group', ''), bp['grading'], group_id_map
            )

            # Write instruction HTML
            html = _make_assignment_html(assignment, bp.get('visual', {}))
            zf.writestr(html_href, html)

            # Write settings XML
            settings_xml = _make_assignment_settings_xml(assignment, assign_id, group_id)
            zf.writestr(xml_href, settings_xml)

            resources.append({
                'id':   assign_id,
                'type': 'associatedcontent/imscc_xmlv1p1/learning-application-resource',
                'href': html_href,
            })

        # ── module_meta.xml (needs resource_map to be complete) ───
        module_meta = _make_module_meta_xml(bp, resource_map)
        zf.writestr('course_settings/module_meta.xml', module_meta)

        # ── imsmanifest.xml ───────────────────────────────────────
        manifest = _make_manifest(resources)
        zf.writestr('imsmanifest.xml', manifest)

    return output_path


# ─────────────────────────────────────────────────────────────────────
#  VALIDATION — basic sanity checks before building
# ─────────────────────────────────────────────────────────────────────

def validate_blueprint(bp):
    """
    Returns a list of warning strings. Empty list = ready to build.
    """
    warnings = []

    if not bp['course']:
        warnings.append('SECTION 1 (Course Identity) is empty or unparseable')

    if not bp['modules']:
        warnings.append('SECTION 4 (Modules) has no modules — course will be empty')

    if not bp['assignments']:
        warnings.append('SECTION 5 (Assignments) has no assignments')

    total_weight = sum(g['weight'] for g in bp['grading'])
    if bp['grading'] and abs(total_weight - 100) > 0.5:
        warnings.append(f'SECTION 3 grading weights sum to {total_weight:.1f}% (should be 100%)')

    orphaned = []
    for a in bp['assignments']:
        matched = any(
            _module_match(a.get('module',''), m['title'], m['number'])
            for m in bp['modules']
        )
        if not matched:
            orphaned.append(a['title'])
    if orphaned:
        warnings.append(f'{len(orphaned)} assignment(s) could not be matched to a module: '
                        + ', '.join(orphaned[:3]))

    return warnings


# ─────────────────────────────────────────────────────────────────────
#  MAIN — CLI entry point
# ─────────────────────────────────────────────────────────────────────

def main():
    print('\n' + '='*60)
    print('  CeCe Course Builder v1.0')
    print('='*60)

    if len(sys.argv) < 2:
        print('\nUsage:  python build.py blueprint.md')
        print('        python build.py blueprint.md --output my-course.imscc')
        sys.exit(1)

    blueprint_path = sys.argv[1]
    if '--output' in sys.argv:
        output_path = sys.argv[sys.argv.index('--output') + 1]
    else:
        base        = os.path.splitext(os.path.basename(blueprint_path))[0]
        output_path = f'{base}_built.imscc'

    if not os.path.exists(blueprint_path):
        print(f'\n❌ Blueprint file not found: {blueprint_path}')
        sys.exit(1)

    print(f'\n📄 Reading blueprint: {blueprint_path}')
    with open(blueprint_path, 'r', encoding='utf-8') as f:
        md_text = f.read()

    print('🔍 Parsing blueprint...')
    bp = parse_blueprint(md_text)

    # Resolve all relative dates to absolute using course start date
    resolve_all_dates(bp)

    # Report what was found
    start = bp['course'].get('Course Start Date', 'not set')
    print(f'   Course:      {bp["course"].get("Course Code","?")} — '
          f'{bp["course"].get("Course Title","?")}')
    print(f'   Start Date:  {start}')
    print(f'   Schedule:    {len(bp["schedule"])} weeks')
    print(f'   CLOs:        {len(bp["clos"])}')
    print(f'   Modules:     {len(bp["modules"])}')
    print(f'   Assignments: {len(bp["assignments"])}')
    print(f'   Grading:     {len(bp["grading"])} groups')
    total_weight = sum(g['weight'] for g in bp['grading'])
    print(f'   Weight total: {total_weight:.1f}%')
    print(f'   Build mode:  {bp["build"].get("mode","FULL BUILD")}')

    # Validate
    print('\n🔎 Validating...')
    warnings = validate_blueprint(bp)
    if warnings:
        for w in warnings:
            print(f'   ⚠️  {w}')
    else:
        print('   ✅ No issues detected')

    # Build
    print(f'\n🔨 Building IMSCC...')
    build_imscc(bp, output_path)

    kb = os.path.getsize(output_path) / 1024
    print(f'\n{"="*60}')
    print(f'✨ Course file saved: {output_path}')
    print(f'   Size: {kb:.1f} KB')
    print(f'   Modules: {len(bp["modules"])} | Assignments: {len(bp["assignments"])}')
    print(f'{"="*60}')
    print('\nNext: Import this file into Canvas via Course Settings → Import.')
    print('      Select "Canvas Course Export Package" as the content type.\n')


if __name__ == '__main__':
    main()
