"""
llm_analysis.py — CeCe's LLM-Powered Analysis Engine
=====================================================

Adds genuine pedagogical reasoning to CeCe's mechanical extraction.
Makes targeted API calls to Claude (Anthropic) to evaluate the course
against the full QM Higher Education Rubric (7th Edition) and UDL framework.

Architecture:
  - 8 focused calls (one per QM General Standard) with data slicing
  - 1 UDL synthesis call
  - 1 executive summary / needs assessment call
  - Model routing: Sonnet for complex judgment, Haiku for presence/absence

Cost optimization:
  - Each call receives ONLY the data slice relevant to its standards
  - Rubric annotations are condensed to essential reviewer guidance
  - Haiku used where keyword-level analysis suffices
  - Estimated total: ~$0.15-0.40 per course analysis

Usage:
  from llm_analysis import run_llm_analysis
  results = run_llm_analysis(api_key, data, modules, objectives,
                              grading_groups, rubrics, identity)
"""

import json
import time
import traceback

# ── Model Configuration ──────────────────────────────────────────
# Sonnet for standards requiring deep pedagogical judgment
# Haiku for standards that are more about presence/absence of information
MODEL_SONNET = "claude-sonnet-4-5-20250929"
MODEL_HAIKU  = "claude-haiku-4-5-20251001"

# Which model to use per General Standard
GS_MODEL_MAP = {
    1: MODEL_HAIKU,    # Course Overview — mostly presence checks
    2: MODEL_SONNET,   # Learning Objectives — needs deep judgment
    3: MODEL_SONNET,   # Assessment & Measurement — alignment analysis
    4: MODEL_SONNET,   # Instructional Materials — quality judgment
    5: MODEL_SONNET,   # Learning Activities — pedagogical reasoning
    6: MODEL_HAIKU,    # Course Technology — mostly presence checks
    7: MODEL_HAIKU,    # Learner Support — mostly presence checks
    8: MODEL_HAIKU,    # Accessibility — pattern-based checks
}

MAX_TOKENS_PER_CALL = 2000
MAX_TOKENS_SUMMARY  = 3000


# ══════════════════════════════════════════════════════════════════
# QM RUBRIC DATA — Condensed for LLM Prompts
# ══════════════════════════════════════════════════════════════════
# Each standard includes: id, points, weight, standard text, and
# condensed reviewer guidance distilled from the 7th Edition annotations.

QM_STANDARDS = {
    # ── GS 1: Course Overview and Introduction ────────────────
    1: {
        "name": "Course Overview and Introduction",
        "standards": [
            {
                "id": "1.1", "points": 3, "weight": "Essential",
                "text": "Instructions make clear how to get started and where to find various course components.",
                "guidance": "Look for: a Start Here / Read Me First page, clear first-step directions, general course overview, navigational instructions encouraging exploration. Reviewer should experience what learners encounter on first visit."
            },
            {
                "id": "1.2", "points": 3, "weight": "Essential",
                "text": "Learners are introduced to the purpose and structure of the course.",
                "guidance": "Look for BOTH purpose (why this course matters, its place in the curriculum/discipline) AND structure (schedule, modality explanation, activity types, how learning is assessed). Both must be present to mark Met."
            },
            {
                "id": "1.3", "points": 2, "weight": "Very Important",
                "text": "Communication guidelines for the course are clearly stated.",
                "guidance": "Look for: expected response times, netiquette/community guidelines, communication channels (email, LMS messaging, discussion boards), tone expectations. Sometimes called 'community guidelines.'"
            },
            {
                "id": "1.4", "points": 2, "weight": "Very Important",
                "text": "Course and institutional policies with which the learner is expected to comply are clearly stated.",
                "guidance": "Look for: academic integrity policy, late work policy, attendance/participation expectations, disability/accommodation statement, grade dispute process. May reference institutional handbook."
            },
            {
                "id": "1.5", "points": 2, "weight": "Very Important",
                "text": "Minimum technology requirements and digital skills are clearly stated.",
                "guidance": "Look for: required hardware/software, browser requirements, internet needs, any specialized tools (e.g., specific software, webcam, microphone). 'Technology' covers a wide range."
            },
            {
                "id": "1.6", "points": 1, "weight": "Important",
                "text": "Technical and digital skills expected of the learner are clearly stated.",
                "guidance": "Look for: what technical skills learners need (file management, word processing, LMS navigation, video conferencing). Distinct from 1.5 — this is about skills, not equipment."
            },
            {
                "id": "1.7", "points": 1, "weight": "Important",
                "text": "Required knowledge and/or competencies are clearly stated.",
                "guidance": "Look for: prerequisites, prior knowledge assumptions, foundational skills expected. Helps learners self-assess readiness."
            },
            {
                "id": "1.8", "points": 1, "weight": "Important",
                "text": "The self-introduction by the instructor is professional and available online.",
                "guidance": "Look for: instructor bio, teaching philosophy, contact info, office hours, photo or video introduction. Should establish instructor presence and approachability."
            },
            {
                "id": "1.9", "points": 1, "weight": "Important",
                "text": "Learners have the opportunity to introduce themselves.",
                "guidance": "Look for: introductory discussion, icebreaker activity, student profile assignment. Builds community and belonging."
            },
        ]
    },

    # ── GS 2: Learning Objectives (Competencies) ─────────────
    2: {
        "name": "Learning Objectives (Competencies)",
        "standards": [
            {
                "id": "2.1", "points": 3, "weight": "Essential",
                "text": "The course-level learning objectives describe outcomes that are measurable.",
                "guidance": "ALIGNMENT standard. Measurable = uses specific, observable Bloom's taxonomy action verbs (analyze, create, evaluate, apply — NOT understand, know, learn, appreciate, be aware of). Objectives must describe what learners will be ABLE TO DO upon completion. Vague verbs like 'understand' or 'know' are NOT measurable."
            },
            {
                "id": "2.2", "points": 3, "weight": "Essential",
                "text": "The module/unit-level learning objectives describe outcomes that are measurable.",
                "guidance": "ALIGNMENT standard. Same measurability requirements as 2.1 but at the module level. Each module should have its own objectives. Module objectives should map to course-level objectives. Check that EVERY module has clearly stated, measurable objectives."
            },
            {
                "id": "2.3", "points": 3, "weight": "Essential",
                "text": "Learning objectives are clearly stated and consistent throughout the course.",
                "guidance": "Objectives should appear in multiple places consistently (syllabus, module introductions, assignment descriptions). Language should not contradict between locations. Check for consistent use of terms and alignment between where objectives are stated."
            },
            {
                "id": "2.4", "points": 3, "weight": "Essential",
                "text": "The relationship between objectives and learning activities is clearly stated.",
                "guidance": "ALIGNMENT standard. Learners should see HOW activities connect to objectives. Look for explicit alignment statements, mapping tables, or explanations within modules that connect activities to specific objectives."
            },
            {
                "id": "2.5", "points": 3, "weight": "Essential",
                "text": "The learning objectives are suited to the level of the course.",
                "guidance": "Bloom's taxonomy levels should match course level. Introductory courses: Remember, Understand, Apply. Upper-division: Analyze, Evaluate, Create. Graduate: predominantly higher-order. Check that the cognitive demand matches the catalog description and student level."
            },
        ]
    },

    # ── GS 3: Assessment and Measurement ──────────────────────
    3: {
        "name": "Assessment and Measurement",
        "standards": [
            {
                "id": "3.1", "points": 3, "weight": "Essential",
                "text": "The assessments measure the stated learning objectives.",
                "guidance": "ALIGNMENT standard. Each assessment should clearly connect to specific objectives. Check: Do quiz questions test what objectives claim? Do assignments require the exact skills stated in objectives? A speech objective needs a speech assessment, not a written essay."
            },
            {
                "id": "3.2", "points": 3, "weight": "Essential",
                "text": "The course grading policy is stated clearly.",
                "guidance": "Look for: grading scale, category weights, point distribution, how final grades are calculated. Should be unambiguous — learners should be able to calculate their own grade at any point."
            },
            {
                "id": "3.3", "points": 3, "weight": "Essential",
                "text": "Specific and descriptive criteria are provided for the evaluation of learners' work.",
                "guidance": "Look for: rubrics, grading criteria, checklists, or detailed descriptions of what constitutes excellent/good/poor work. Criteria should be specific enough that learners know exactly what is expected BEFORE submitting. Generic criteria like 'good grammar' are insufficient."
            },
            {
                "id": "3.4", "points": 2, "weight": "Very Important",
                "text": "The course provides multiple opportunities to track learning progress.",
                "guidance": "Look for: formative assessments (self-checks, practice quizzes, drafts, peer review), not just summative. Learners should receive feedback BEFORE high-stakes assessments. Multiple low-stakes checkpoints throughout."
            },
            {
                "id": "3.5", "points": 2, "weight": "Very Important",
                "text": "The types of assessments selected measure the stated learning objectives and are sequenced and varied.",
                "guidance": "Look for: variety (discussions, papers, projects, quizzes, presentations, portfolios). Assessments should be scaffolded — building in complexity. Not all the same type. Sequence should support progressive skill development."
            },
            {
                "id": "3.6", "points": 1, "weight": "Important",
                "text": "The course assessments provide guidance on academic integrity.",
                "guidance": "Look for: academic honesty expectations in assessment descriptions, plagiarism policy reminders, honor code references, citation expectations, guidance on collaboration vs. individual work."
            },
        ]
    },

    # ── GS 4: Instructional Materials ─────────────────────────
    4: {
        "name": "Instructional Materials",
        "standards": [
            {
                "id": "4.1", "points": 3, "weight": "Essential",
                "text": "The instructional materials contribute to the achievement of the stated learning objectives.",
                "guidance": "ALIGNMENT standard. Materials (readings, videos, lectures, resources) should directly support what objectives ask learners to do. Check: Are materials chosen because they help learners meet objectives, or do they seem disconnected?"
            },
            {
                "id": "4.2", "points": 3, "weight": "Essential",
                "text": "The relationship between the use of instructional materials and the learning activities is clearly explained.",
                "guidance": "Learners should understand WHY they are reading/watching/doing each thing. Look for: explicit connections between materials and activities (e.g., 'Read Chapter 3, then use those concepts in the discussion')."
            },
            {
                "id": "4.3", "points": 2, "weight": "Very Important",
                "text": "The course models academic integrity through proper citations and references.",
                "guidance": "The course itself should model proper citation practices. Look for: references on content pages, properly cited images/videos, source attribution for external content. The course should practice what it preaches."
            },
            {
                "id": "4.4", "points": 2, "weight": "Very Important",
                "text": "The instructional materials represent current thinking in the discipline.",
                "guidance": "Look for: recent publication dates, current edition textbooks, up-to-date resources. Note outdated materials, broken links, or references to superseded standards/practices."
            },
            {
                "id": "4.5", "points": 2, "weight": "Very Important",
                "text": "A variety of instructional materials is used in the course.",
                "guidance": "Look for: mix of text, video, audio, interactive content, simulations, case studies, primary sources. Over-reliance on a single format (e.g., all text readings) is insufficient. Variety supports diverse learning preferences."
            },
        ]
    },

    # ── GS 5: Learning Activities and Learner Interaction ─────
    5: {
        "name": "Learning Activities and Learner Interaction",
        "standards": [
            {
                "id": "5.1", "points": 3, "weight": "Essential",
                "text": "The learning activities promote the achievement of the stated learning objectives.",
                "guidance": "ALIGNMENT standard. Activities (discussions, labs, practice problems, projects) should directly build skills stated in objectives. Check: Do activities give learners practice doing what objectives describe? Activities should be active, not passive."
            },
            {
                "id": "5.2", "points": 3, "weight": "Essential",
                "text": "Learning activities provide opportunities for interaction that support active learning.",
                "guidance": "Three types of interaction: learner-content (engaging with materials), learner-learner (peer discussion, collaboration, peer review), and learner-instructor (feedback, Q&A, office hours). Look for all three types. Passive reading alone is insufficient."
            },
            {
                "id": "5.3", "points": 3, "weight": "Essential",
                "text": "The instructor's plan for classroom response time and feedback is clearly stated.",
                "guidance": "Look for: response time commitments (e.g., 'I will respond to emails within 24 hours'), grading turnaround time, discussion participation expectations from instructor, feedback approach. Learners should know when to expect instructor engagement."
            },
            {
                "id": "5.4", "points": 2, "weight": "Very Important",
                "text": "The requirements for learner interaction are clearly articulated.",
                "guidance": "Look for: specific participation requirements (frequency, quality expectations for discussion posts), collaboration guidelines, group work expectations. Learners should know exactly what 'participation' means and how it is evaluated."
            },
        ]
    },

    # ── GS 6: Course Technology ───────────────────────────────
    6: {
        "name": "Course Technology",
        "standards": [
            {
                "id": "6.1", "points": 3, "weight": "Essential",
                "text": "The tools used in the course support the learning objectives.",
                "guidance": "ALIGNMENT standard. Technology choices should serve learning goals, not be technology for its own sake. Each tool should have a clear pedagogical purpose connected to objectives."
            },
            {
                "id": "6.2", "points": 2, "weight": "Very Important",
                "text": "Course tools promote learner engagement and active learning.",
                "guidance": "Look for: interactive tools (discussion boards, collaboration platforms, simulations, polling), not just passive content delivery. Tools should enable learners to actively engage with content and each other."
            },
            {
                "id": "6.3", "points": 1, "weight": "Important",
                "text": "A variety of technology tools are used in the course.",
                "guidance": "Look for: multiple tools beyond just the LMS (video, collaboration tools, subject-specific software, multimedia creation tools). Over-reliance on a single tool limits engagement."
            },
            {
                "id": "6.4", "points": 1, "weight": "Important",
                "text": "The course provides learners with information on protecting their data and privacy.",
                "guidance": "Look for: privacy notices for third-party tools, FERPA considerations, guidance on what personal info is shared, data protection practices."
            },
        ]
    },

    # ── GS 7: Learner Support ─────────────────────────────────
    7: {
        "name": "Learner Support",
        "standards": [
            {
                "id": "7.1", "points": 3, "weight": "Essential",
                "text": "The course instructions articulate or link to the institution's technical support.",
                "guidance": "Look for: help desk contact info, LMS support resources, how to report technical problems. Links should be functional and current. Support information may vary by institution."
            },
            {
                "id": "7.2", "points": 3, "weight": "Essential",
                "text": "Course instructions articulate or link to the institution's accessibility policies and services.",
                "guidance": "Look for: disability services contact, accommodation request process, accessibility statement, ADA/Section 508 references. Must be more than a generic statement — should tell learners HOW to get help."
            },
            {
                "id": "7.3", "points": 3, "weight": "Essential",
                "text": "Course instructions articulate or link to the institution's academic support services.",
                "guidance": "Look for: tutoring center, writing center, library resources, academic advising. Links should be specific and current. Learners should know where to go for academic help beyond the instructor."
            },
            {
                "id": "7.4", "points": 1, "weight": "Important",
                "text": "Course instructions articulate or link to the institution's student services.",
                "guidance": "Look for: counseling services, financial aid, registrar, student success/retention resources. Broader than academic support — covers whole-student needs."
            },
        ]
    },

    # ── GS 8: Accessibility and Usability ─────────────────────
    8: {
        "name": "Accessibility and Usability",
        "standards": [
            {
                "id": "8.1", "points": 3, "weight": "Essential",
                "text": "Course navigation facilitates ease of use.",
                "guidance": "Look for: consistent layout across modules, logical sequencing, clear labels, intuitive menu structure. Learners should be able to find content without confusion. Consistent module structure is key."
            },
            {
                "id": "8.2", "points": 3, "weight": "Essential",
                "text": "The course design facilitates readability and usability.",
                "guidance": "Look for: readable fonts, adequate contrast, consistent formatting, appropriate use of headings, white space, chunked content. Long walls of text are problematic. Mobile-friendly considerations."
            },
            {
                "id": "8.3", "points": 3, "weight": "Essential",
                "text": "Text in the course is accessible.",
                "guidance": "Look for: proper heading hierarchy (H1, H2, H3 not just bold text), meaningful link text (not 'click here'), lists formatted as actual lists, tables with headers. Content should work with screen readers."
            },
            {
                "id": "8.4", "points": 2, "weight": "Very Important",
                "text": "Images in the course are accessible.",
                "guidance": "Look for: alt text on all meaningful images, decorative images marked appropriately, complex images with long descriptions. Images should not be the sole means of conveying information."
            },
            {
                "id": "8.5", "points": 2, "weight": "Very Important",
                "text": "Video and audio content in the course are accessible.",
                "guidance": "Look for: closed captions on videos, transcripts for audio, audio descriptions for visual-only content. Auto-generated captions alone may be insufficient if not reviewed for accuracy."
            },
            {
                "id": "8.6", "points": 2, "weight": "Very Important",
                "text": "Multimedia in the course is accessible.",
                "guidance": "Look for: accessible interactive elements, keyboard navigability of embedded content, alternatives for multimedia that requires specific plugins. Check that third-party content is accessible."
            },
            {
                "id": "8.7", "points": 1, "weight": "Important",
                "text": "Vendor accessibility information is provided.",
                "guidance": "Look for: VPAT or accessibility documentation links for third-party tools, publisher accessibility statements, information about known accessibility issues with required tools."
            },
        ]
    },
}


# ══════════════════════════════════════════════════════════════════
# DATA SLICING — Extract relevant data for each GS call
# ══════════════════════════════════════════════════════════════════

def _slice_for_gs1(data, modules, identity, **kw):
    """GS 1: Course Overview — needs welcome pages, syllabus excerpt, identity."""
    wiki = data.get('wiki_full', {})
    # Find welcome/overview/start-here pages
    overview_pages = {}
    overview_keys = ['welcome', 'introduction', 'overview', 'start-here',
                     'getting-started', 'the-right-stuff', 'syllabus',
                     'about', 'instructor', 'course-info', 'policies',
                     'technology', 'tech-req', 'netiquette', 'support']
    for page_name, content in wiki.items():
        if any(k in page_name.lower() for k in overview_keys):
            # Truncate long pages to save tokens
            overview_pages[page_name] = content[:3000]

    # If we didn't find many, include the first few pages
    if len(overview_pages) < 3:
        for page_name, content in list(wiki.items())[:5]:
            if page_name not in overview_pages:
                overview_pages[page_name] = content[:2000]

    syl_excerpt = data.get('syllabus_text', '')[:4000]

    return {
        "course_identity": identity,
        "module_count": len(modules),
        "module_titles": [m['title'] for m in modules[:15]],
        "overview_pages": overview_pages,
        "syllabus_excerpt": syl_excerpt if syl_excerpt else "(No syllabus provided)",
        "lti_tools": data.get('lti_tools', []),
    }


def _slice_for_gs2(data, modules, objectives, **kw):
    """GS 2: Learning Objectives — needs CLOs, MLOs, Bloom's, alignment."""
    clos = [o for o in objectives if o.get('obj_type') == 'CLO']
    mlos = [o for o in objectives if o.get('obj_type') == 'MLO']
    unknown = [o for o in objectives if o.get('obj_type') == 'unknown']

    # Format for readability
    def fmt_obj(obj_list):
        return [{"text": o['text'], "blooms": o['blooms'],
                 "source": o['source'], "module": o.get('module_num')}
                for o in obj_list]

    return {
        "course_level_objectives": fmt_obj(clos),
        "module_level_objectives": fmt_obj(mlos),
        "unclassified_objectives": fmt_obj(unknown),
        "total_modules": len(modules),
        "modules_with_objectives": len(set(
            o.get('module_num') for o in mlos if o.get('module_num')
        )),
        "module_titles": [m['title'] for m in modules],
    }


def _slice_for_gs3(data, modules, objectives, grading_groups, rubrics, **kw):
    """GS 3: Assessment — needs assignments, rubrics, grading, objectives."""
    assignments = data.get('assignments', {})
    assign_summary = []
    for name, det in list(assignments.items())[:30]:
        assign_summary.append({
            "name": name,
            "instructions_excerpt": det.get('instructions', '')[:500],
            "points": det.get('points', ''),
            "submission_type": det.get('sub_type', ''),
            "due_date": det.get('due_date', ''),
        })

    clos = [{"text": o['text'], "blooms": o['blooms']}
            for o in objectives if o.get('obj_type') == 'CLO']
    mlos = [{"text": o['text'], "blooms": o['blooms'],
             "module": o.get('module_num')}
            for o in objectives if o.get('obj_type') == 'MLO']

    return {
        "assignments": assign_summary,
        "grading_structure": grading_groups,
        "rubrics_excerpt": rubrics[:4000] if rubrics else "(No rubrics detected)",
        "course_objectives": clos,
        "module_objectives": mlos,
        "quiz_count": len(data.get('assessments', {})),
    }


def _slice_for_gs4(data, modules, **kw):
    """GS 4: Instructional Materials — needs content inventory + samples."""
    wiki = data.get('wiki_full', {})
    media_titles = data.get('wiki_titles', [])

    # Content page inventory with excerpts
    content_samples = {}
    for page_name, content in list(wiki.items())[:20]:
        content_samples[page_name] = content[:1500]

    return {
        "content_page_names": list(wiki.keys()),
        "content_samples": content_samples,
        "media_titles": media_titles[:30],
        "lti_tools": data.get('lti_tools', []),
        "total_content_pages": len(wiki),
        "total_media_items": len(media_titles),
    }


def _slice_for_gs5(data, modules, objectives, **kw):
    """GS 5: Learning Activities — needs activities, discussions, interaction."""
    wiki = data.get('wiki_full', {})
    assignments = data.get('assignments', {})

    # Find discussion-type content
    discussions = {}
    activities = {}
    for name, det in assignments.items():
        instr = det.get('instructions', '')
        if any(w in name.lower() or w in instr.lower()
               for w in ['discussion', 'respond', 'reply', 'post', 'forum']):
            discussions[name] = instr[:800]
        elif any(w in name.lower() or w in instr.lower()
                 for w in ['activity', 'practice', 'exercise', 'lab', 'project',
                           'collaborate', 'group', 'peer', 'team']):
            activities[name] = instr[:800]

    # Find interaction-related wiki pages
    interaction_pages = {}
    for page_name, content in wiki.items():
        if any(k in page_name.lower() for k in
               ['discussion', 'interact', 'office', 'feedback', 'communi',
                'participat', 'collaborat', 'group']):
            interaction_pages[page_name] = content[:1500]

    mlos = [{"text": o['text'], "blooms": o['blooms'],
             "module": o.get('module_num')}
            for o in objectives if o.get('obj_type') == 'MLO']

    return {
        "discussions": discussions,
        "activities": activities,
        "interaction_pages": interaction_pages,
        "module_objectives": mlos,
        "total_assignments": len(assignments),
    }


def _slice_for_gs6(data, **kw):
    """GS 6: Course Technology — needs tools, tech references."""
    wiki = data.get('wiki_full', {})

    # Find technology-related pages
    tech_pages = {}
    for page_name, content in wiki.items():
        if any(k in page_name.lower() for k in
               ['technolog', 'tool', 'software', 'resource', 'tech-req',
                'digital', 'privacy', 'data']):
            tech_pages[page_name] = content[:2000]

    return {
        "lti_tools": data.get('lti_tools', []),
        "tech_pages": tech_pages,
        "media_titles": data.get('wiki_titles', [])[:20],
    }


def _slice_for_gs7(data, **kw):
    """GS 7: Learner Support — needs support/policy pages."""
    wiki = data.get('wiki_full', {})

    support_pages = {}
    for page_name, content in wiki.items():
        if any(k in page_name.lower() for k in
               ['support', 'resource', 'accessibility', 'accommodat',
                'disability', 'tutor', 'writing', 'library', 'counsel',
                'help', 'student-service', 'ada', 'section-508',
                'technical', 'tech-support', 'helpdesk']):
            support_pages[page_name] = content[:2000]

    # Also check syllabus for support info
    syl = data.get('syllabus_text', '')
    syl_support = ''
    for keyword in ['support', 'accessibility', 'disability', 'tutor',
                    'writing center', 'library', 'counseling', 'technical']:
        idx = syl.lower().find(keyword)
        if idx >= 0:
            start = max(0, idx - 100)
            end = min(len(syl), idx + 500)
            syl_support += syl[start:end] + '\n...\n'

    return {
        "support_pages": support_pages,
        "syllabus_support_excerpts": syl_support[:3000] if syl_support else "(No support content found in syllabus)",
    }


def _slice_for_gs8(data, modules, **kw):
    """GS 8: Accessibility — needs navigation structure, content format info."""
    wiki = data.get('wiki_full', {})

    # Sample content for accessibility analysis (check formatting/structure)
    content_samples = {}
    for page_name, content in list(wiki.items())[:10]:
        # Keep HTML-ish content for accessibility checking
        content_samples[page_name] = content[:2000]

    return {
        "module_count": len(modules),
        "module_titles": [m['title'] for m in modules],
        "module_structures": [
            {"title": m['title'],
             "item_count": len(m.get('items', [])),
             "items": [item.get('title', '') for item in m.get('items', [])][:10]}
            for m in modules[:10]
        ],
        "content_page_names": list(wiki.keys()),
        "content_samples": content_samples,
        "media_titles": data.get('wiki_titles', [])[:20],
        "total_pages": len(wiki),
    }


# Map GS number → slice function
GS_SLICE_MAP = {
    1: _slice_for_gs1,
    2: _slice_for_gs2,
    3: _slice_for_gs3,
    4: _slice_for_gs4,
    5: _slice_for_gs5,
    6: _slice_for_gs6,
    7: _slice_for_gs7,
    8: _slice_for_gs8,
}


# ══════════════════════════════════════════════════════════════════
# PROMPT TEMPLATES
# ══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are a Quality Matters (QM) certified peer reviewer evaluating an online course using the QM Higher Education Rubric, 7th Edition. You are thorough, evidence-based, and constructive.

Your task: Evaluate the provided course data against a specific set of QM standards. For each standard, determine whether it is Met, Partially Met, or Not Met based on the evidence available.

IMPORTANT RULES:
- Base your evaluation ONLY on the evidence provided. Do not assume content exists if it is not shown.
- Be specific — cite exact page names, assignment titles, or content excerpts as evidence.
- If evidence is insufficient to evaluate a standard, say so and mark it "Needs Review."
- Be constructive in recommendations — suggest specific, actionable improvements.
- Consider that some content may exist in the course but not be captured in the extract (e.g., embedded videos, external links). Note this uncertainty when relevant.

Respond in valid JSON with this structure:
{
  "evaluations": [
    {
      "standard_id": "X.Y",
      "status": "Met | Partially Met | Not Met | Needs Review",
      "confidence": "High | Medium | Low",
      "evidence": "Specific evidence from the course data supporting your evaluation",
      "gaps": "What is missing or insufficient (empty string if Met)",
      "recommendation": "Specific, actionable recommendation (empty string if Met)"
    }
  ],
  "general_standard_summary": "2-3 sentence overall assessment of this General Standard area"
}"""


def _build_gs_prompt(gs_number, data_slice):
    """Build the user prompt for a specific General Standard evaluation."""
    gs = QM_STANDARDS[gs_number]
    standards_text = ""
    for s in gs['standards']:
        standards_text += (
            f"\n### Standard {s['id']} ({s['weight']}, {s['points']} pts)\n"
            f"**Requirement:** {s['text']}\n"
            f"**Reviewer Guidance:** {s['guidance']}\n"
        )

    data_json = json.dumps(data_slice, indent=2, default=str)

    # Truncate data if it's very large to stay within token budget
    if len(data_json) > 20000:
        data_json = data_json[:20000] + "\n... (truncated for length)"

    return f"""## Evaluate General Standard {gs_number}: {gs['name']}

### Standards to Evaluate
{standards_text}

### Extracted Course Data
```json
{data_json}
```

Evaluate each standard listed above. Return your evaluation as valid JSON following the structure specified in your instructions."""


# ══════════════════════════════════════════════════════════════════
# UDL ANALYSIS PROMPT
# ══════════════════════════════════════════════════════════════════

UDL_SYSTEM_PROMPT = """You are an expert in Universal Design for Learning (UDL) evaluating an online course. UDL is based on three principles:

1. MULTIPLE MEANS OF REPRESENTATION (the "what" of learning)
   - Present information in multiple formats (text, video, audio, visual)
   - Provide options for perception, language, and comprehension
   - Offer alternatives for auditory and visual information

2. MULTIPLE MEANS OF ACTION & EXPRESSION (the "how" of learning)
   - Allow learners to demonstrate knowledge in varied ways
   - Support planning, strategy development, and self-monitoring
   - Provide options for physical action and expression

3. MULTIPLE MEANS OF ENGAGEMENT (the "why" of learning)
   - Offer choices and autonomy in learning
   - Connect to learner interests and real-world relevance
   - Support self-regulation, motivation, and sustained effort

Respond in valid JSON:
{
  "representation": {
    "status": "Strong | Adequate | Needs Improvement",
    "formats_found": ["list of content formats detected"],
    "strengths": "what the course does well",
    "gaps": "what is missing",
    "recommendations": ["specific actionable recommendations"]
  },
  "action_expression": {
    "status": "Strong | Adequate | Needs Improvement",
    "assessment_types_found": ["list of assessment/expression types"],
    "strengths": "what the course does well",
    "gaps": "what is missing",
    "recommendations": ["specific actionable recommendations"]
  },
  "engagement": {
    "status": "Strong | Adequate | Needs Improvement",
    "engagement_strategies_found": ["list of strategies detected"],
    "strengths": "what the course does well",
    "gaps": "what is missing",
    "recommendations": ["specific actionable recommendations"]
  },
  "overall_udl_summary": "2-3 sentence overall UDL assessment"
}"""


def _build_udl_prompt(data, modules, objectives):
    """Build the UDL analysis prompt with relevant data."""
    wiki = data.get('wiki_full', {})
    assignments = data.get('assignments', {})

    # Content format inventory
    content_names = list(wiki.keys())
    media_titles = data.get('wiki_titles', [])

    # Assignment types summary
    assign_types = []
    for name, det in list(assignments.items())[:25]:
        assign_types.append({
            "name": name,
            "type": det.get('sub_type', 'unknown'),
            "instructions_excerpt": det.get('instructions', '')[:300],
        })

    data_slice = {
        "content_page_names": content_names[:30],
        "media_titles": media_titles[:25],
        "assignments": assign_types,
        "module_titles": [m['title'] for m in modules],
        "lti_tools": data.get('lti_tools', []),
        "total_pages": len(wiki),
        "total_assignments": len(assignments),
    }

    data_json = json.dumps(data_slice, indent=2, default=str)
    if len(data_json) > 15000:
        data_json = data_json[:15000] + "\n... (truncated)"

    return f"""## Evaluate this online course against the UDL framework

### Extracted Course Data
```json
{data_json}
```

Analyze the course data for evidence of each UDL principle. Return your evaluation as valid JSON following the structure specified in your instructions."""


# ══════════════════════════════════════════════════════════════════
# EXECUTIVE SUMMARY / NEEDS ASSESSMENT PROMPT
# ══════════════════════════════════════════════════════════════════

SUMMARY_SYSTEM_PROMPT = """You are an experienced instructional designer writing an executive summary and needs assessment for a faculty member whose online course has just been evaluated against the Quality Matters (QM) Higher Education Rubric (7th Edition) and the Universal Design for Learning (UDL) framework.

Your tone should be collegial, constructive, and direct — like a supportive QM peer reviewer. Assume the instructor cares about quality but may not be familiar with QM terminology. Use plain language and explain any jargon.

Write in clear prose paragraphs, NOT bullet points. Use markdown formatting with ## headers for sections.

Structure your response as:

## Executive Summary
A 3-4 sentence high-level overview of the course's alignment with QM and UDL. State the overall picture clearly.

## Key Strengths
What the course does well — be specific with evidence. This should encourage the instructor.

## Priority Recommendations
The 3-5 MOST impactful changes the instructor should make, ordered by importance. For each, explain: what needs to change, why it matters for student learning, and a concrete suggestion for how to do it. Focus on Essential (3-point) standards first.

## Detailed Needs Assessment
Walk through each General Standard area (GS 1-8) with a brief assessment. Highlight any standards marked Not Met or Partially Met, and note what the course needs.

## UDL Assessment
Summarize the UDL findings — what's working and what could be improved for accessibility and inclusive design.

## Recommended Next Steps
A prioritized action plan: what to do first, second, third. Be realistic about effort level."""


def _build_summary_prompt(gs_results, udl_result, identity):
    """Build the executive summary prompt from all evaluation results."""
    # Compile all standard evaluations
    all_evaluations = []
    gs_summaries = []
    for gs_num in sorted(gs_results.keys()):
        result = gs_results[gs_num]
        gs_name = QM_STANDARDS[gs_num]['name']
        gs_summaries.append(f"**GS {gs_num} ({gs_name}):** {result.get('general_standard_summary', 'N/A')}")
        for ev in result.get('evaluations', []):
            std_info = None
            for s in QM_STANDARDS[gs_num]['standards']:
                if s['id'] == ev.get('standard_id'):
                    std_info = s
                    break
            all_evaluations.append({
                "standard_id": ev.get('standard_id'),
                "weight": std_info['weight'] if std_info else 'Unknown',
                "points": std_info['points'] if std_info else 0,
                "standard_text": std_info['text'] if std_info else '',
                "status": ev.get('status'),
                "evidence": ev.get('evidence', ''),
                "gaps": ev.get('gaps', ''),
                "recommendation": ev.get('recommendation', ''),
            })

    # Count statuses
    met = sum(1 for e in all_evaluations if e['status'] == 'Met')
    partial = sum(1 for e in all_evaluations if e['status'] == 'Partially Met')
    not_met = sum(1 for e in all_evaluations if e['status'] == 'Not Met')
    review = sum(1 for e in all_evaluations if e['status'] == 'Needs Review')

    data = {
        "course_identity": identity,
        "score_summary": {
            "total_standards": len(all_evaluations),
            "met": met, "partially_met": partial,
            "not_met": not_met, "needs_review": review,
        },
        "gs_summaries": gs_summaries,
        "all_evaluations": all_evaluations,
        "udl_result": udl_result,
    }

    data_json = json.dumps(data, indent=2, default=str)

    return f"""## Write an Executive Summary and Needs Assessment

### Complete Evaluation Results
```json
{data_json}
```

Write the executive summary and needs assessment following the structure specified in your instructions. Be specific, constructive, and actionable."""


# ══════════════════════════════════════════════════════════════════
# API CALL WRAPPER
# ══════════════════════════════════════════════════════════════════

def _call_anthropic(api_key, system_prompt, user_prompt, model, max_tokens,
                    progress_callback=None, call_label=""):
    """
    Make a single API call to Anthropic.
    Returns parsed JSON dict if response is JSON, else raw text string.
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError(
            "The 'anthropic' package is required for LLM analysis. "
            "Install it with: pip install anthropic"
        )

    client = anthropic.Anthropic(api_key=api_key)

    if progress_callback:
        progress_callback(f"🔍 {call_label}...")

    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        # Extract text from response
        text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                text += block.text

        # Track token usage
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "model": model,
        }

        # Try to parse as JSON
        # Strip markdown code fences if present
        clean = text.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()

        try:
            parsed = json.loads(clean)
            return parsed, usage
        except json.JSONDecodeError:
            # Return raw text if not valid JSON
            return {"raw_text": text}, usage

    except Exception as e:
        error_msg = str(e)
        if "authentication" in error_msg.lower() or "api key" in error_msg.lower():
            raise ValueError(
                "API key authentication failed. Please check your Anthropic API key "
                "in .streamlit/secrets.toml"
            )
        raise


# ══════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════

def run_llm_analysis(api_key, data, modules, objectives,
                     grading_groups, rubrics, identity,
                     progress_callback=None):
    """
    Run the full LLM-powered QM + UDL analysis.

    Args:
        api_key:     Anthropic API key
        data:        Full CeCe data dict from read_imscc()
        modules:     List of module dicts from extract_modules()
        objectives:  List of objective dicts from extract_learning_objectives()
        grading_groups: Grading structure string from extract_grading_structure()
        rubrics:     Rubrics string from extract_rubrics()
        identity:    Identity dict from extract_course_identity()
        progress_callback: Optional callable(str) for UI status updates

    Returns:
        dict with keys:
          'gs_results':      {gs_num: evaluation_dict} for each GS 1-8
          'udl_result':      UDL evaluation dict
          'executive_summary': Full markdown executive summary text
          'token_usage':     List of usage dicts per call
          'errors':          List of any errors encountered (non-fatal)
    """
    results = {
        'gs_results': {},
        'udl_result': {},
        'executive_summary': '',
        'token_usage': [],
        'errors': [],
    }

    def log(msg):
        if progress_callback:
            progress_callback(msg)

    # ── Phase 1: Evaluate each General Standard ──────────────
    log("Starting QM evaluation (8 General Standards)...")

    for gs_num in range(1, 9):
        gs_name = QM_STANDARDS[gs_num]['name']
        model = GS_MODEL_MAP[gs_num]
        model_label = "Sonnet" if "sonnet" in model else "Haiku"

        try:
            # Slice the data for this GS
            slice_fn = GS_SLICE_MAP[gs_num]
            data_slice = slice_fn(
                data=data, modules=modules, objectives=objectives,
                grading_groups=grading_groups, rubrics=rubrics,
                identity=identity,
            )

            # Build the prompt
            user_prompt = _build_gs_prompt(gs_num, data_slice)

            # Make the API call
            result, usage = _call_anthropic(
                api_key=api_key,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                model=model,
                max_tokens=MAX_TOKENS_PER_CALL,
                progress_callback=progress_callback,
                call_label=f"GS {gs_num}: {gs_name} ({model_label})",
            )

            results['gs_results'][gs_num] = result
            results['token_usage'].append({
                "call": f"GS {gs_num}: {gs_name}",
                **usage,
            })

            log(f"  ✅ GS {gs_num} complete ({usage['input_tokens']}+{usage['output_tokens']} tokens)")

            # Brief pause to respect rate limits
            time.sleep(0.5)

        except Exception as e:
            error_msg = f"GS {gs_num} ({gs_name}): {str(e)}"
            results['errors'].append(error_msg)
            log(f"  ⚠️ {error_msg}")
            results['gs_results'][gs_num] = {
                "evaluations": [],
                "general_standard_summary": f"Error during evaluation: {str(e)}",
            }

    # ── Phase 2: UDL Analysis ────────────────────────────────
    log("Running UDL analysis...")
    try:
        udl_prompt = _build_udl_prompt(data, modules, objectives)
        udl_result, udl_usage = _call_anthropic(
            api_key=api_key,
            system_prompt=UDL_SYSTEM_PROMPT,
            user_prompt=udl_prompt,
            model=MODEL_HAIKU,
            max_tokens=MAX_TOKENS_PER_CALL,
            progress_callback=progress_callback,
            call_label="UDL Analysis (Haiku)",
        )
        results['udl_result'] = udl_result
        results['token_usage'].append({"call": "UDL Analysis", **udl_usage})
        log(f"  ✅ UDL complete ({udl_usage['input_tokens']}+{udl_usage['output_tokens']} tokens)")
        time.sleep(0.5)
    except Exception as e:
        results['errors'].append(f"UDL: {str(e)}")
        log(f"  ⚠️ UDL error: {str(e)}")

    # ── Phase 3: Executive Summary & Needs Assessment ────────
    log("Generating executive summary and needs assessment...")
    try:
        summary_prompt = _build_summary_prompt(
            results['gs_results'], results['udl_result'], identity
        )
        summary_result, summary_usage = _call_anthropic(
            api_key=api_key,
            system_prompt=SUMMARY_SYSTEM_PROMPT,
            user_prompt=summary_prompt,
            model=MODEL_SONNET,
            max_tokens=MAX_TOKENS_SUMMARY,
            progress_callback=progress_callback,
            call_label="Executive Summary (Sonnet)",
        )

        # Summary should be raw text (markdown), not JSON
        if isinstance(summary_result, dict) and 'raw_text' in summary_result:
            results['executive_summary'] = summary_result['raw_text']
        elif isinstance(summary_result, str):
            results['executive_summary'] = summary_result
        else:
            results['executive_summary'] = json.dumps(summary_result, indent=2)

        results['token_usage'].append({"call": "Executive Summary", **summary_usage})
        log(f"  ✅ Summary complete ({summary_usage['input_tokens']}+{summary_usage['output_tokens']} tokens)")

    except Exception as e:
        results['errors'].append(f"Executive Summary: {str(e)}")
        log(f"  ⚠️ Summary error: {str(e)}")

    # ── Final stats ──────────────────────────────────────────
    total_input = sum(u.get('input_tokens', 0) for u in results['token_usage'])
    total_output = sum(u.get('output_tokens', 0) for u in results['token_usage'])
    log(f"\n📊 Analysis complete: {total_input:,} input + {total_output:,} output tokens")
    log(f"   {len(results['errors'])} error(s)")

    return results


# ══════════════════════════════════════════════════════════════════
# DOCUMENT BUILDER — Format LLM results for the Analysis Document
# ══════════════════════════════════════════════════════════════════

def build_llm_sections(llm_results):
    """
    Convert LLM analysis results into markdown sections for the
    CeCe Analysis Document. Returns a list of strings (lines) to
    append to the document's L list.

    This produces two new sections:
      - Section N:  LLM-Powered QM Deep Analysis (per-standard detail)
      - Section N+1: Executive Summary & Needs Assessment
    """
    L = []

    # ── LLM QM Deep Analysis ─────────────────────────────────
    L += [
        '', '---', '',
        '## LLM-POWERED QM DEEP ANALYSIS',
        '> *AI-generated evaluation using Claude (Anthropic). Each QM standard was evaluated against extracted course content.*',
        '> *This supplements the automated pre-check above with genuine pedagogical reasoning.*',
        '',
    ]

    gs_results = llm_results.get('gs_results', {})

    for gs_num in range(1, 9):
        gs = QM_STANDARDS.get(gs_num, {})
        gs_name = gs.get('name', f'General Standard {gs_num}')
        result = gs_results.get(gs_num, {})

        L += [f'### GS {gs_num}: {gs_name}', '']

        # General Standard summary
        summary = result.get('general_standard_summary', '')
        if summary:
            L += [f'> {summary}', '']

        # Per-standard evaluation table
        evaluations = result.get('evaluations', [])
        if evaluations:
            L += ['| Standard | Status | Confidence | Evidence | Gaps | Recommendation |',
                  '|----------|--------|------------|----------|------|----------------|']
            for ev in evaluations:
                std_id = ev.get('standard_id', '?')
                status = ev.get('status', '?')
                conf = ev.get('confidence', '?')
                evidence = ev.get('evidence', '').replace('|', '/').replace('\n', ' ')[:200]
                gaps = ev.get('gaps', '').replace('|', '/').replace('\n', ' ')[:150]
                rec = ev.get('recommendation', '').replace('|', '/').replace('\n', ' ')[:200]

                # Status emoji
                if status == 'Met':
                    status_fmt = '✅ Met'
                elif status == 'Partially Met':
                    status_fmt = '⚠️ Partially Met'
                elif status == 'Not Met':
                    status_fmt = '❌ Not Met'
                else:
                    status_fmt = '🔍 Needs Review'

                L.append(
                    f'| {std_id} | {status_fmt} | {conf} | {evidence} | {gaps} | {rec} |'
                )
            L.append('')
        elif 'raw_text' in result:
            L += [result['raw_text'], '']
        else:
            L += ['*Evaluation not available for this standard.*', '']

    # ── UDL Deep Analysis ────────────────────────────────────
    udl = llm_results.get('udl_result', {})
    if udl and not isinstance(udl, str):
        L += [
            '### UDL Deep Analysis', '',
            '> *AI-generated UDL evaluation supplementing the automated pre-check above.*',
            '',
        ]

        for principle in ['representation', 'action_expression', 'engagement']:
            p_data = udl.get(principle, {})
            if not p_data:
                continue
            nice_name = principle.replace('_', ' ').title()
            status = p_data.get('status', '?')
            L += [f'**{nice_name}:** {status}', '']
            if p_data.get('strengths'):
                L += [f'*Strengths:* {p_data["strengths"]}', '']
            if p_data.get('gaps'):
                L += [f'*Gaps:* {p_data["gaps"]}', '']
            recs = p_data.get('recommendations', [])
            if recs:
                L.append('*Recommendations:*')
                for r in recs:
                    L.append(f'- {r}')
                L.append('')

        udl_summary = udl.get('overall_udl_summary', '')
        if udl_summary:
            L += [f'> {udl_summary}', '']

    # ── Executive Summary & Needs Assessment ─────────────────
    exec_summary = llm_results.get('executive_summary', '')
    if exec_summary:
        L += [
            '', '---', '',
            '## EXECUTIVE SUMMARY & NEEDS ASSESSMENT',
            '> *AI-generated synthesis of the complete QM and UDL evaluation.*',
            '> *This section provides the instructor with a clear picture of course strengths, priority improvements, and recommended next steps.*',
            '',
            exec_summary,
            '',
        ]

    # ── Token Usage Report ───────────────────────────────────
    usage = llm_results.get('token_usage', [])
    if usage:
        L += [
            '### Analysis Token Usage', '',
            '| Call | Model | Input Tokens | Output Tokens |',
            '|------|-------|-------------|---------------|',
        ]
        total_in = 0
        total_out = 0
        for u in usage:
            model_short = 'Sonnet' if 'sonnet' in u.get('model', '') else 'Haiku'
            inp = u.get('input_tokens', 0)
            out = u.get('output_tokens', 0)
            total_in += inp
            total_out += out
            L.append(f'| {u.get("call", "?")} | {model_short} | {inp:,} | {out:,} |')
        L.append(f'| **Total** | | **{total_in:,}** | **{total_out:,}** |')
        L.append('')

    # ── Errors ───────────────────────────────────────────────
    errors = llm_results.get('errors', [])
    if errors:
        L += ['### Analysis Errors', '']
        for err in errors:
            L.append(f'- ⚠️ {err}')
        L.append('')

    return L
