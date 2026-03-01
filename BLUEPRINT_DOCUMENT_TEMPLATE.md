# MeMe Course Blueprint
> Produced by MeMe | QM Remediation Consultation Output v2.1
> This document is the direct input for DeDe, the Canvas course builder agent.
> **Do not alter section headers, field labels, or block delimiters.**
> DeDe reads this document programmatically — formatting must be exact.

---

## SECTION 1: COURSE IDENTITY

> Fill every field. Do not leave placeholders.
> Course Start Date must be the Monday of Week 1 (or the actual first day of class).
> Class Meeting Days uses: Mon | Tue | Wed | Thu | Fri | Sat | Sun — comma-separated.
> DeDe uses Start Date + Meeting Days to calculate all absolute due dates from relative ones.

| Field | Value |
|-------|-------|
| Course Title | {{COURSE_TITLE}} |
| Course Code | {{COURSE_CODE}} |
| Delivery Modality | {{MODALITY}} |
| Institution | {{INSTITUTION}} |
| Estimated Weeks | {{WEEK_COUNT}} |
| Course Start Date | {{YYYY-MM-DD}} |
| Class Meeting Days | {{MEETING_DAYS}} |
| Blueprint Version | {{DATE}} |

---

## SECTION 2: COURSE-LEVEL LEARNING OBJECTIVES

> List all CLOs agreed upon during consultation.
> Every CLO must use a measurable Bloom's action verb.
> Every CLO must be addressed by at least one assignment in Section 6.
> Format exactly as shown — one per line, pipe-delimited.

CLO-1 | {{BLOOMS_LEVEL}} | {{OBJECTIVE_STATEMENT}}
CLO-2 | {{BLOOMS_LEVEL}} | {{OBJECTIVE_STATEMENT}}

**Format reference:**
CLO-1 | Analyze | Students will analyze the ethical implications of emerging AI technologies across healthcare, law, and education.
CLO-2 | Apply | Students will apply psychological research methods to design a simple observational study.

---

## SECTION 3: COURSE SCHEDULE

> The authoritative week-by-week calendar for the course.
> Every module and every assignment must appear somewhere in this schedule.
> Week numbers here must match the module and assignment blocks in Sections 5 and 6 exactly.
> Due items: list assignment names only — full details are in Section 6.
> Day abbreviations: Mon | Tue | Wed | Thu | Fri | Sat | Sun

| Week | Topic / Focus | Module | Due This Week | Notes |
|------|--------------|--------|---------------|-------|
| 1 | {{TOPIC}} | {{MODULE_NUMBER}} | {{ASSIGNMENT_NAME}} ({{DAY}}) | {{NOTES}} |

---

## SECTION 4: GRADING STRUCTURE

> DeDe uses this to build Canvas assignment groups with correct weights.
> Weights must sum to exactly 100. DeDe will flag any deviation.
> Drop Lowest N: enter 0 if not applicable.

| Group Name | Weight (%) | Drop Lowest N | Notes |
|------------|-----------|---------------|-------|
| {{GROUP_NAME}} | {{WEIGHT}} | {{DROP_N}} | {{NOTES}} |

---

## SECTION 5: MODULE BLUEPRINTS

> One block per module. Use the exact delimiter: ### MODULE: N — Title
> Repeat the full block for every module in the course.
> Write "None" for any field that does not apply — do not leave fields blank.
> MLOs must be measurable and must map to at least one CLO from Section 2.
> MLO format: MLO-N.N | Bloom's Level | Objective Statement | CLO-#
> Availability uses Week N, Day format — DeDe resolves to absolute dates at build time.

---

### MODULE: 1 — {{MODULE_TITLE}}

**Availability:**
- Opens: Week {{N}}, {{DAY}}
- Closes: Week {{N}}, {{DAY}}

**Overview Text:**
{{MODULE_OVERVIEW}}

**Module Learning Objectives:**
MLO-1.1 | {{BLOOMS_LEVEL}} | {{OBJECTIVE_STATEMENT}} | CLO-{{N}}
MLO-1.2 | {{BLOOMS_LEVEL}} | {{OBJECTIVE_STATEMENT}} | CLO-{{N}}

**Assignments in This Module:**
> Names only — full details go in Section 6. One per line.
- {{ASSIGNMENT_NAME}}

**Instructional Materials:**
> Title and type only. Type options: Video | Reading | Podcast | Webpage | Tool | Slide Deck
- {{MATERIAL_TITLE}} ({{TYPE}})

**Discussion / Reflection Prompt:**
{{MODULE_DISCUSSION}}

**Notes for DeDe:**
{{MODULE_AGENT_NOTES}}

---

## SECTION 6: ASSIGNMENT BLUEPRINTS

> One block per assignment. Use the exact delimiter: ### ASSIGNMENT: Title
> Be thorough — this becomes the actual assignment page in Canvas.
> Every assignment must map to at least one MLO and one CLO.
> Write "None" for Rubric if no rubric is needed (e.g. automated quizzes).
> Due / Available / Until all use relative format: Week N, Day — e.g. "Week 3, Fri"
> DeDe resolves all relative dates to absolute calendar dates at build time.

---

### ASSIGNMENT: {{ASSIGNMENT_TITLE}}

**Belongs To Module:** {{MODULE_NUMBER}}
**Assignment Group:** {{GRADING_GROUP}}
**Points Possible:** {{POINTS}}
**Due:** Week {{N}}, {{DAY}}
**Available From:** Week {{N}}, {{DAY}}
**Until:** Week {{N}}, {{DAY}}
**Submission Type:** {{SUBMISSION_TYPE}}
> Options: Text Entry | File Upload | External URL | Media Recording | No Submission

**Purpose Statement:**
> One sentence. Why does this assignment matter to student learning?
{{ASSIGNMENT_PURPOSE}}

**Instructions:**
{{ASSIGNMENT_INSTRUCTIONS}}

**Rubric:**
> One row per criterion. Point values per criterion should sum to Points Possible.
> Write "None" if this assignment has no rubric (e.g. auto-graded quiz).

| Criterion | Excellent | Satisfactory | Needs Improvement | Points |
|-----------|-----------|--------------|-------------------|--------|
| {{CRITERION}} | {{EXCELLENT}} | {{SATISFACTORY}} | {{NEEDS_IMPROVEMENT}} | {{PTS}} |

**Alignment:**
- Maps to CLOs: {{CLO_NUMBERS}}
- Maps to MLOs: {{MLO_NUMBERS}}
- Fink's Category: {{FINK_CATEGORY}}
> Options: Foundational Knowledge | Application | Integration | Human Dimension | Caring | Learning How to Learn

**Academic Integrity Notes:**
> Note any design decisions made to reduce misconduct risk. Write "None" if not applicable.
{{INTEGRITY_NOTES}}

---

## SECTION 7: COURSE POLICIES & SYLLABUS CONTENT

> This content becomes the Canvas syllabus page.
> Write in complete sentences — this is student-facing.
> Do not use placeholders — MeMe should draft this content during consultation.

**Course Description:**
{{COURSE_DESCRIPTION}}

**Instructor Information:**
> Name, contact method, and office hours or availability.
{{INSTRUCTOR_INFO}}

**Required Materials:**
> Textbooks, software, hardware, access codes.
{{REQUIRED_MATERIALS}}

**Attendance & Participation Policy:**
{{ATTENDANCE_POLICY}}

**Late Work Policy:**
{{LATE_WORK_POLICY}}

**Academic Integrity Policy:**
{{ACADEMIC_INTEGRITY_POLICY}}

**Accessibility Statement:**
> Minimum: link to institutional accessibility office. Preferred: full statement.
{{ACCESSIBILITY_STATEMENT}}

**Additional Policies:**
> Any course-specific policies not covered above. Write "None" if not applicable.
{{ADDITIONAL_POLICIES}}

---

## SECTION 8: TECHNOLOGY & TOOLS

> List every external tool used in the course.
> DeDe will use this to add LTI placeholder links and tool references.
> Canvas-native tools (Discussions, Quizzes, Assignments) do not need to be listed.

| Tool Name | Purpose in Course | Required or Optional | LTI or External URL |
|-----------|------------------|----------------------|---------------------|
| {{TOOL_NAME}} | {{PURPOSE}} | {{REQUIRED_OPTIONAL}} | {{LTI_OR_URL}} |

---

## SECTION 9: BLUEPRINT CHANGE LOG

> MeMe completes this section at the end of consultation.
> This is a record for the ID and instructor — not instructions for DeDe.
> Be specific. Vague entries like "improved objectives" are not useful.

**Summary of Changes:**
{{CHANGE_SUMMARY}}

**QM Standards Addressed:**
> List each standard resolved and what was done.
- {{STANDARD}} — {{WHAT_CHANGED}}

**UDL Improvements Made:**
- {{UDL_CHANGE}}

**Fink's Framework Additions:**
- {{FINK_CHANGE}}

**Grading Adjustments:**
{{GRADING_CHANGES}}

**Instructor Decisions (with rationale):**
> Record any case where the instructor chose to keep something despite MeMe's recommendation.
> Format: Decision | Rationale
- {{DECISION}} | {{RATIONALE}}

---

## SECTION 10: AGENT BUILD INSTRUCTIONS

> Direct instructions from MeMe to DeDe.
> DeDe reads this section first to determine how to handle the build.
> Be explicit — DeDe follows these literally.

**Build Mode:** {{BUILD_MODE}}
> Options:
> FULL BUILD — build the entire course from scratch using this Blueprint
> UPDATE — modify an existing IMSCC file using this Blueprint as a patch

**Preserve From Original:**
> For UPDATE mode only. List elements DeDe should leave exactly as-is.
> Write "None" for FULL BUILD.
{{PRESERVE_LIST}}

**Delete From Original:**
> For UPDATE mode only. List elements DeDe should remove entirely.
> Write "None" for FULL BUILD.
{{DELETE_LIST}}

**Special Build Notes:**
> Any instructions that don't fit elsewhere.
> Write "None" if not applicable.
{{SPECIAL_BUILD_NOTES}}

---

*MeMe Course Blueprint v2.1 — Handoff to DeDe*
