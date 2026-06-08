"""
insights.py — Analyses CSV sections and generates a final report.

ARCHITECTURE (FIXED):
CSV sections (local) → SINGLE LLM call → final report
"""

import time

_insight_provider = None

_section_options = {
    "max_tokens": 200,
    "temperature": 0.1
}

_report_options = {
    "max_tokens": 800,
    "temperature": 0.1
}

_runtime_options = {
    "request_delay_seconds": 0.0,
    "max_retries": 0,
}


# ─────────────────────────────────────────────
# INIT
# ─────────────────────────────────────────────
def init(provider, section_options=None, report_options=None, runtime_options=None):
    global _insight_provider, _section_options, _report_options, _runtime_options

    _insight_provider = provider

    if section_options:
        _section_options.update(section_options)

    if report_options:
        _report_options.update(report_options)

    if runtime_options:
        _runtime_options.update(runtime_options)


# ─────────────────────────────────────────────
# SYSTEM PROMPTS
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """
You are a senior mobile analytics expert.

You will be given structured Firebase Analytics CSV sections.

Your job:
- Detect trends, anomalies, and user behaviour patterns
- Cross-link signals across sections (VERY IMPORTANT)
- Identify root causes, not isolated observations
- Be precise with numbers and event names

Do NOT invent data.
"""

FINAL_FORMAT = """
Structure exactly:

1. CRITICAL ISSUES
2. WARNINGS
3. POSITIVES
4. RECOMMENDATIONS (top 5, prioritized)

Plain text only.
"""


# ─────────────────────────────────────────────
# INTERNAL CALL WRAPPER
# ─────────────────────────────────────────────
def _call_llm(system: str, user: str) -> str:
    """Single safe call wrapper."""
    return _insight_provider.complete(
        system=system,
        user=user,
        max_tokens=_report_options["max_tokens"],
        temperature=_report_options["temperature"]
    )


# ─────────────────────────────────────────────
# MAIN ENTRY (FIXED)
# ─────────────────────────────────────────────
def analyse_all(sections: list) -> list:
    """
    SINGLE CALL PIPELINE (FIXED)

    Converts all sections → one structured prompt → one LLM call
    """

    packed_sections = []

    for s in sections:
        preview = "\n".join(s["data"].splitlines()[:40])

        packed_sections.append(
            f"""
=== {s['title']} ({s['row_count']} rows) ===
{preview}
"""
        )

    full_context = "\n\n".join(packed_sections)

    prompt = f"""
You are analysing Firebase Analytics data.

Below are structured sections of event data.

{full_context}

Task:
- Identify cross-section patterns
- Detect anomalies and spikes
- Explain likely causes
- Prioritize issues by business impact

Return a structured analytics summary.
"""

    print("[insights] Running SINGLE LLM call for full analysis...\n")

    result = _call_llm(SYSTEM_PROMPT + "\n" + FINAL_FORMAT, prompt)

    return [
        {
            "title": "FULL DATASET ANALYSIS",
            "insight": result
        }
    ]


# ─────────────────────────────────────────────
# REPORT GENERATION (NO LLM - FIXED)
# ─────────────────────────────────────────────
def generate_report(section_insights: list) -> None:
    """
    NO SECOND LLM CALL (FIXED)

    Just prints final output.
    """

    print("\n" + "=" * 60)
    print("  FIREBASE ANALYTICS — FINAL INSIGHTS REPORT")
    print("=" * 60 + "\n")

    for item in section_insights:
        if not item["insight"].startswith("[Skipped"):
            print(item["insight"])

    print("\n" + "=" * 60)
    print("  END OF REPORT")
    print("=" * 60)