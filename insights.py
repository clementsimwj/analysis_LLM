"""
insights.py — Single-call analytics LLM layer
"""
import json
import re
import time
from typing import Any

_insight_provider = None
_report_options = {
    "max_tokens": 800,
    "temperature": 0.1,
}
_runtime_options = {
    "max_retries": 0,
    "retry_base_delay_seconds": 30.0,
    "max_prompt_chars": 14000,
}


def init(provider, report_options=None, runtime_options=None):
    global _insight_provider, _report_options, _runtime_options
    _insight_provider = provider
    if report_options:
        _report_options.update(report_options)
    if runtime_options:
        _runtime_options.update(runtime_options)


SYSTEM_PROMPT = """
You are a senior mobile analytics expert.

You analyse Firebase analytics metrics.

Rules:
- Use ONLY provided data
- Do NOT invent metrics
- Be precise and business-focused
- Identify root causes, not symptoms
- Separate direct evidence from hypotheses
- Prefer high-impact issues over exhaustive summaries
- Never call aggregate event-count ratios true funnels or conversion rates
- Never infer affected-user rate from event volume
- Never interpret categorical segment rows as time trends
- When evidence_type or interpretation_limit is provided, honor it explicitly
- Use safe_label wording when present; avoid unsafe_label wording
- Use "may indicate" for proxy-only evidence or causal hypotheses
- Do not describe app-version movement as total active-user growth
"""


FORMAT = """
Return structure:

1. EXECUTIVE SUMMARY
2. CRITICAL ISSUES
3. SEGMENT DRIVERS AND PROXY EVENT RATIOS
4. POSITIVES
5. RECOMMENDATIONS (top 5, prioritized)
6. WHAT TO CHECK NEXT

For each major insight, include:
- evidence: metric names and values from the JSON
- interpretation: what it likely means
- confidence: High, Medium, or Low
- limitation: include when the JSON marks evidence as proxy-only

Wording requirements:
- Say "error-like event volume share", not "error rate", unless user/session denominators are provided
- Say "aggregate event-count proxy ratio", not "completion rate", "conversion rate", or "funnel"
- For app-version metrics, say "active users on version X", not "active users increased"
- If a root cause is not proven, phrase it as a hypothesis and include what to validate next
"""


def _retry_delay_from_error(error: Exception, attempt: int) -> float:
    message = str(error)
    retry_match = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)", message)
    if retry_match:
        return float(retry_match.group(1)) + 1

    retry_match = re.search(r"retry in ([\d.]+)s", message, re.IGNORECASE)
    if retry_match:
        return float(retry_match.group(1)) + 1

    return float(_runtime_options["retry_base_delay_seconds"]) * attempt


def _is_retryable_error(error: Exception) -> bool:
    message = str(error).lower()
    non_retryable_markers = [
        "error code: 413",
        "request too large",
        "please reduce your message size",
        "context_length_exceeded",
        "invalid api key",
        "incorrect api key",
        "authentication",
    ]
    return not any(marker in message for marker in non_retryable_markers)


def _short_error(error: Exception) -> str:
    message = " ".join(str(error).split())
    return message[:500] + ("..." if len(message) > 500 else "")


def _call_llm(system: str, user: str) -> str:
    max_retries = int(_runtime_options["max_retries"])
    for attempt in range(1, max_retries + 2):
        try:
            return _insight_provider.complete(
                system=system,
                user=user,
                max_tokens=_report_options["max_tokens"],
                temperature=_report_options["temperature"],
            )
        except Exception as e:
            if not _is_retryable_error(e):
                raise RuntimeError(f"Non-retryable LLM error: {_short_error(e)}") from e

            if attempt > max_retries:
                raise
            delay = _retry_delay_from_error(e, attempt)
            print(f"[insights] LLM call failed: {_short_error(e)}")
            print(f"[insights] Retrying in {delay:.1f}s...")
            time.sleep(delay)

    raise RuntimeError("Unexpected retry loop exit.")


def _top(items: list[Any] | None, limit: int) -> list[Any]:
    return list(items or [])[:limit]


def _compact_section(section: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "title": section.get("title"),
        "type": section.get("type"),
        "date_range": section.get("date_range"),
    }

    section_type = section.get("type")
    if section_type in {"time_series", "app_version_time_series"}:
        compact["metrics"] = _top(section.get("numeric_metrics"), 8)
        if section.get("interpretation_limit"):
            compact["interpretation_limit"] = section.get("interpretation_limit")
    elif section_type == "event_count_table":
        error_summary = dict(section.get("error_summary") or {})
        error_summary["top_error_events"] = _top(error_summary.get("top_error_events"), 5)
        compact.update(
            {
                "total_event_count": section.get("total_event_count"),
                "unique_event_names": section.get("unique_event_names"),
                "top_events": _top(section.get("top_events"), 10),
                "error_summary": error_summary,
                "event_categories": _top(section.get("event_categories"), 8),
                "event_count_ratios": _top(section.get("event_count_ratios"), 5),
                "high_frequency_events": _top(section.get("high_frequency_events"), 5),
            }
        )
    elif section_type in {"segment_breakdown", "numeric_table", "cohort_retention_table", "cohort_curve"}:
        segment = dict(section.get("segment_breakdown") or {})
        segment["top_segments"] = _top(segment.get("top_segments"), 8)
        compact["segment_breakdown"] = segment
        if section.get("cohort_curve"):
            compact["cohort_curve"] = section.get("cohort_curve")
    elif section.get("sample_rows"):
        compact["sample_rows"] = _top(section.get("sample_rows"), 3)

    if section.get("warnings"):
        compact["warnings"] = _top(section.get("warnings"), 5)
    return compact


def _compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "source_type": metrics.get("source_type"),
        "section_count": metrics.get("section_count"),
        "warnings": _top(metrics.get("warnings"), 10),
        "cross_section_signals": {
            "largest_recent_metric_changes": _top(
                (metrics.get("cross_section_signals") or {}).get("largest_recent_metric_changes"),
                8,
            ),
            "top_error_events": _top(
                (metrics.get("cross_section_signals") or {}).get("top_error_events"),
                5,
            ),
        },
        "sections": [_compact_section(section) for section in metrics.get("sections", [])],
        "llm_instructions": metrics.get("llm_instructions"),
    }
    return compact


def _section_priority(section: dict[str, Any]) -> int:
    title = str(section.get("title", "")).lower()
    section_type = section.get("type")
    if section_type == "event_count_table":
        return 0
    if "active users trending" in title:
        return 1
    if section_type in {"time_series", "app_version_time_series"}:
        return 2
    if "country" in title:
        return 3
    if "device" in title:
        return 4
    if section_type == "segment_breakdown":
        return 5
    return 9


def _metrics_json_for_prompt(metrics: dict[str, Any]) -> str:
    compact = _compact_metrics(metrics)
    metrics_json = json.dumps(compact, sort_keys=True, separators=(",", ":"))
    max_chars = int(_runtime_options.get("max_prompt_chars", 14000))

    if len(metrics_json) <= max_chars:
        return metrics_json

    compact["sections"] = [
        section for section in compact["sections"]
            if section.get("type") in {
                "time_series",
                "app_version_time_series",
                "event_count_table",
                "segment_breakdown",
            }
    ]
    for section in compact["sections"]:
        if "top_events" in section:
            section["top_events"] = _top(section["top_events"], 6)
        if "event_count_ratios" in section:
            section["event_count_ratios"] = _top(section["event_count_ratios"], 3)
        if "segment_breakdown" in section:
            section["segment_breakdown"]["top_segments"] = _top(
                section["segment_breakdown"].get("top_segments"),
                5,
            )
        if "metrics" in section:
            section["metrics"] = _top(section["metrics"], 5)

    metrics_json = json.dumps(compact, sort_keys=True, separators=(",", ":"))
    if len(metrics_json) > max_chars:
        compact["payload_note"] = "Payload was trimmed to fit provider request limits."
        compact["sections"] = sorted(
            compact["sections"],
            key=_section_priority,
        )[:8]
        metrics_json = json.dumps(compact, sort_keys=True, separators=(",", ":"))

    return metrics_json


def analyse(metrics: dict) -> str:
    global _insight_provider
    metrics_json = _metrics_json_for_prompt(metrics)
    print(f"[insights] Metrics payload size: {len(metrics_json)} characters")

    prompt = f"""
Here is a deterministic Firebase analytics metrics brief as JSON.
Pandas already computed the numbers; do not recalculate them.

{metrics_json}

Task:
- Identify the 5-8 most important patterns
- Explain anomalies and likely causes
- Connect event volume, proxy event ratios, error-volume signals, segments, and time-series signals where possible
- Prioritize recommendations by business impact
- State what additional data would validate uncertain hypotheses
"""

    return _call_llm(SYSTEM_PROMPT + "\n" + FORMAT, prompt)
