"""
metrics.py - Deterministic Firebase analytics metrics.

This module keeps arithmetic out of the LLM path:
CSV -> section DataFrames -> structured metrics brief -> one LLM call.
"""
import csv
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd


ERROR_PATTERN = re.compile(r"error|crash|exception|fail", re.IGNORECASE)
PERCENT_BASELINE_MIN = 20


def load_df(filepath: str) -> list[dict[str, Any]]:
    """Backward-compatible entry point: load CSV sections as DataFrames."""
    return load_sections(filepath)


def load_sections(filepath: str) -> list[dict[str, Any]]:
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {filepath}")

    rows = list(csv.reader(path.read_text(encoding="utf-8").splitlines()))
    sections = []
    comments = []
    dates = {}
    header = None
    data_rows = []
    title = None
    section_index = 1

    def flush():
        nonlocal header, data_rows, title, section_index
        if header is None or not data_rows:
            header = None
            data_rows = []
            title = None
            return

        df = _build_dataframe(header, data_rows)
        if not df.empty:
            sections.append(
                {
                    "title": title or _title_from_header(header, section_index),
                    "date_range": dict(dates),
                    "dataframe": df,
                }
            )
            section_index += 1

        header = None
        data_rows = []
        title = None

    for row in rows:
        if _is_blank_row(row):
            flush()
            continue

        comment = _comment_text(row)
        if comment is not None:
            flush()
            date_key, date_value = _parse_date_comment(comment)
            if date_key:
                dates[date_key] = date_value
            elif _is_useful_comment(comment):
                comments.append(comment)
            continue

        if header is None:
            header = row
            title = _choose_title(comments, header, section_index)
            comments = []
        else:
            data_rows.append(row)

    flush()
    return sections


def build_metrics(sections: list[dict[str, Any]]) -> dict[str, Any]:
    section_metrics = []
    warnings = []

    for section in sections:
        summary = _summarize_section(section)
        section_metrics.append(summary)
        warnings.extend(summary.get("warnings", []))

    return _json_safe(
        {
            "source_type": "firebase_analytics_export",
            "section_count": len(section_metrics),
            "sections": section_metrics,
            "cross_section_signals": _cross_section_signals(section_metrics),
            "warnings": sorted(
                warnings,
                key=lambda item: item.get("severity_rank", 99),
            )[:20],
            "llm_instructions": {
                "role": "Use these deterministic metrics only.",
                "priority": "Focus on material changes, root-cause hypotheses, and next actions.",
                "do_not": "Do not recalculate, invent missing data, or mention every metric.",
                "language_rules": {
                    "error_volume": "Say error-like event volume share, not user error rate.",
                    "proxy_ratios": "Say aggregate event-count proxy ratio, not funnel conversion or completion rate.",
                    "app_versions": "Say active users on app version X, not total active-user growth.",
                    "causality": "Use may indicate/may reflect unless the metric directly proves the cause.",
                },
            },
        }
    )


def _build_dataframe(header: list[str], rows: list[list[str]]) -> pd.DataFrame:
    cleaned_header = []
    seen = {}
    for idx, cell in enumerate(header):
        name = _clean_cell(cell) or f"unnamed_{idx}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        cleaned_header.append(name)

    width = len(cleaned_header)
    aligned_rows = []
    for row in rows:
        aligned = [_clean_cell(cell) for cell in row[:width]]
        aligned.extend([""] * (width - len(aligned)))
        aligned_rows.append(aligned)

    df = pd.DataFrame(aligned_rows, columns=cleaned_header)
    df = df.replace("", pd.NA).dropna(how="all")

    empty_cols = [
        col for col in df.columns
        if str(col).startswith("unnamed_") and df[col].isna().all()
    ]
    if empty_cols:
        df = df.drop(columns=empty_cols)

    for col in df.columns:
        converted = pd.to_numeric(
            df[col].astype("string").str.replace(",", "", regex=False),
            errors="coerce",
        )
        if converted.notna().sum() >= max(1, int(len(df) * 0.6)):
            df[col] = converted

    return df.reset_index(drop=True)


def _summarize_section(section: dict[str, Any]) -> dict[str, Any]:
    df = section["dataframe"]
    title = section["title"]
    event_col = _find_col(df, ["event_name", "event name"])
    numeric_cols = _metric_numeric_cols(df)
    section_type = _classify_section(df, title, event_col, numeric_cols)

    summary = {
        "title": title,
        "type": section_type,
        "date_range": section.get("date_range", {}),
        "row_count": int(len(df)),
        "columns": list(map(str, df.columns)),
        "warnings": [],
    }

    if event_col:
        summary.update(_event_metrics(df, event_col))
    elif numeric_cols:
        summary.update(_numeric_section_metrics(df, numeric_cols, section_type))
    else:
        summary["sample_rows"] = df.head(5).to_dict(orient="records")

    return summary


def _event_metrics(df: pd.DataFrame, event_col: str) -> dict[str, Any]:
    count_col = _find_col(df, ["event_count", "event count", "count"])
    users_col = _find_col(df, ["total_users", "total users", "users"])
    per_user_col = _find_col(df, ["event_count_per_active_user", "event count per active user"])

    work = df.copy()
    work["_event_name"] = work[event_col].astype("string").fillna("")
    work["_count"] = _series_or_default(work, count_col, 1)
    total_events = float(work["_count"].sum())
    total_users = float(work[users_col].sum()) if users_col else None
    top = work.sort_values("_count", ascending=False).head(15)

    error_rows = work[work["_event_name"].str.contains(ERROR_PATTERN, na=False)]
    error_count = float(error_rows["_count"].sum())
    top_event_count = float(top.iloc[0]["_count"]) if not top.empty else 0
    top_event_share = _safe_div(top_event_count, total_events)

    metrics = {
        "total_event_count": _round(total_events),
        "estimated_total_users_sum": _round(total_users) if total_users is not None else None,
        "unique_event_names": int(work["_event_name"].nunique()),
        "top_events": _records(top, ["_event_name", "_count", users_col, per_user_col], 15),
        "error_summary": {
            "error_event_count": _round(error_count),
            "error_event_volume_share": _round(_safe_div(error_count, total_events), 4),
            "evidence_type": "aggregate_event_count",
            "safe_label": "error-like event volume share",
            "unsafe_label": "user error rate or app crash rate",
            "interpretation_limit": "This is share of recorded event volume, not affected-user rate or session error rate.",
            "top_error_events": _records(
                error_rows.sort_values("_count", ascending=False),
                ["_event_name", "_count", users_col, per_user_col],
                10,
            ),
        },
        "event_categories": _event_categories(work),
        "event_count_ratios": _event_count_ratios(work),
        "warnings": [],
    }

    if per_user_col:
        high_frequency = work.sort_values(per_user_col, ascending=False).head(10)
        metrics["high_frequency_events"] = _records(
            high_frequency,
            ["_event_name", "_count", users_col, per_user_col],
            10,
        )

    if len(work) >= 3 and total_events >= PERCENT_BASELINE_MIN and top_event_share >= 0.4:
        metrics["warnings"].append(
            _warning(
                "high",
                "event_concentration",
                f"Top event accounts for {_pct(top_event_share)} of event volume.",
            )
        )

    error_share = _safe_div(error_count, total_events)
    if error_share >= 0.1:
        metrics["warnings"].append(
            _warning(
                "critical",
                "high_error_volume",
                f"Error/crash-like events account for {_pct(error_share)} of event volume.",
            )
        )
    elif error_share >= 0.03:
        metrics["warnings"].append(
            _warning(
                "medium",
                "error_volume",
                f"Error/crash-like events account for {_pct(error_share)} of event volume.",
            )
        )

    for ratio in metrics["event_count_ratios"]:
        overall_ratio = ratio.get("overall_ratio")
        if overall_ratio is not None and overall_ratio < 0.5:
            metrics["warnings"].append(
                _warning(
                    "high",
                    "low_event_count_ratio",
                    f"{ratio['name']} aggregate event-count ratio is {_pct(overall_ratio)}.",
                )
            )

    return metrics


def _classify_section(
    df: pd.DataFrame,
    title: str,
    event_col: str | None,
    numeric_cols: list[str],
) -> str:
    if event_col:
        return "event_count_table"

    first_col = str(df.columns[0]) if len(df.columns) else ""
    norm_first = _norm(first_col)
    norm_title = _norm(title)

    if norm_first in {"nth_day", "day"}:
        if _looks_like_app_version_columns(numeric_cols):
            return "app_version_time_series"
        return "time_series"
    if norm_first == "cohort":
        return "cohort_curve"
    if norm_first == "date" or "retain" in norm_title:
        return "cohort_retention_table"
    if any(token in norm_first for token in ["country", "device", "page_title", "screen", "app"]):
        return "segment_breakdown"
    if numeric_cols:
        return "numeric_table"
    return "table"


def _numeric_section_metrics(
    df: pd.DataFrame,
    numeric_cols: list[str],
    section_type: str,
) -> dict[str, Any]:
    if section_type == "time_series":
        return _time_series_metrics(df, numeric_cols)
    if section_type == "app_version_time_series":
        metrics = _time_series_metrics(df, numeric_cols)
        metrics["interpretation_limit"] = (
            "Columns are app versions over time. Changes reflect version adoption/migration, "
            "not total active-user growth."
        )
        for item in metrics.get("numeric_metrics", []):
            item["evidence_type"] = "app_version_time_series"
            item["safe_label"] = "active users on this app version"
            item["unsafe_label"] = "total active-user growth"
        return metrics
    if section_type == "cohort_curve":
        return _cohort_curve_metrics(df, numeric_cols)
    return _segment_breakdown_metrics(df, numeric_cols, section_type)


def _time_series_metrics(df: pd.DataFrame, numeric_cols: list[str]) -> dict[str, Any]:
    series_metrics = []
    for col in numeric_cols:
        values = pd.to_numeric(df[col], errors="coerce").dropna()
        if values.empty:
            continue

        first = float(values.iloc[0])
        last = float(values.iloc[-1])
        delta = last - first
        recent_avg = float(values.tail(min(7, len(values))).mean())
        previous_avg = None
        recent_delta_pct = None
        if len(values) >= 14:
            previous_avg = float(values.iloc[-14:-7].mean())
            recent_delta_pct = _safe_div(recent_avg - previous_avg, previous_avg)

        diffs = values.diff().dropna()
        largest_drop = float(diffs.min()) if not diffs.empty else None
        largest_gain = float(diffs.max()) if not diffs.empty else None

        series_metrics.append(
            {
                "metric": col,
                "first": _round(first),
                "last": _round(last),
                "absolute_change": _round(delta),
                "percent_change": _guarded_percent(delta, first),
                "average": _round(float(values.mean())),
                "min": _round(float(values.min())),
                "max": _round(float(values.max())),
                "recent_7_avg": _round(recent_avg),
                "previous_7_avg": _round(previous_avg),
                "recent_7_vs_previous_7_pct": _guarded_percent(
                    None if recent_delta_pct is None or previous_avg is None else recent_avg - previous_avg,
                    previous_avg,
                ),
                "largest_row_drop": _round(largest_drop),
                "largest_row_gain": _round(largest_gain),
                "direction": _direction(delta),
                "evidence_type": "time_series",
            }
        )

    warnings = []
    for metric in series_metrics:
        recent_change = metric.get("recent_7_vs_previous_7_pct")
        if recent_change is not None and abs(recent_change) >= 0.2:
            warnings.append(
                _warning(
                    "medium" if abs(recent_change) < 0.4 else "high",
                    "recent_trend_change",
                    f"{metric['metric']} changed {_pct(recent_change)} in the recent 7-day average.",
                )
            )

    return {
        "numeric_metrics": series_metrics[:20],
        "warnings": warnings,
    }


def _segment_breakdown_metrics(
    df: pd.DataFrame,
    numeric_cols: list[str],
    section_type: str,
) -> dict[str, Any]:
    label_col = df.columns[0] if len(df.columns) else None
    rows = []
    for col in numeric_cols:
        total = float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())
        if total == 0:
            continue
        value_col = "__value"
        label_values = df[label_col] if label_col else pd.Series([col] * len(df), index=df.index)
        work = pd.DataFrame(
            {
                "__segment": label_values,
                value_col: pd.to_numeric(df[col], errors="coerce").fillna(0),
            }
        )
        work = work.sort_values(value_col, ascending=False).head(15)
        for _, row in work.iterrows():
            rows.append(
                {
                    "dimension": label_col,
                    "segment": row["__segment"],
                    "metric": col,
                    "value": _round(row[value_col]),
                    "share": _round(_safe_div(row[value_col], total), 4),
                }
            )

    warnings = []
    if rows and rows[0].get("share") is not None and rows[0]["share"] >= 0.5:
        warnings.append(
            _warning(
                "medium",
                "segment_concentration",
                f"{rows[0]['segment']} accounts for {_pct(rows[0]['share'])} of {rows[0]['metric']}.",
            )
        )

    return {
        "segment_breakdown": {
            "evidence_type": section_type,
            "interpretation_limit": "Rows are categorical segments, not time order. Do not compute trend deltas from row order.",
            "top_segments": rows[:20],
        },
        "warnings": warnings,
    }


def _cohort_curve_metrics(df: pd.DataFrame, numeric_cols: list[str]) -> dict[str, Any]:
    metrics = _segment_breakdown_metrics(df, numeric_cols, "cohort_curve")
    if numeric_cols:
        col = numeric_cols[0]
        values = pd.to_numeric(df[col], errors="coerce").dropna()
        metrics["cohort_curve"] = {
            "metric": col,
            "day_0": _round(values.iloc[0]) if len(values) else None,
            "day_1": _round(values.iloc[1]) if len(values) > 1 else None,
            "day_7": _round(values.iloc[7]) if len(values) > 7 else None,
            "day_30": _round(values.iloc[30]) if len(values) > 30 else None,
            "interpretation_limit": "Retention curve values, not active-user volume trend.",
        }
    return metrics


def _event_categories(work: pd.DataFrame) -> list[dict[str, Any]]:
    categories = {
        "errors": r"error|crash|exception|fail",
        "signup": r"sign_?up|signup",
        "sync": r"sync",
        "notifications": r"notification",
        "ai_glucose": r"glucose",
        "engagement": r"screen_view|user_engagement|session_start",
        "app_lifecycle": r"first_open|app_remove|app_update|os_update|app_clear_data",
    }
    total = float(work["_count"].sum())
    results = []
    for name, pattern in categories.items():
        mask = work["_event_name"].str.contains(pattern, case=False, regex=True, na=False)
        count = float(work.loc[mask, "_count"].sum())
        if count:
            results.append(
                {
                    "category": name,
                    "event_count": _round(count),
                    "share": _round(_safe_div(count, total), 4),
                }
            )
    return sorted(results, key=lambda item: item["event_count"], reverse=True)


def _event_count_ratios(work: pd.DataFrame) -> list[dict[str, Any]]:
    count_by_event = {
        str(row["_event_name"]).lower(): float(row["_count"])
        for _, row in work.iterrows()
    }

    ratios = [
        _event_count_ratio(
            "sign_up",
            count_by_event,
            ["Sign_Up_Step", "sign_up"],
            errors=["Sign_Up_Error"],
        ),
        _event_count_ratio(
            "sync",
            count_by_event,
            ["Syncing_Attempt", "Syncing_Start", "Finish_Syncing"],
            errors=["Syncing_Error"],
        ),
        _event_count_ratio(
            "notifications",
            count_by_event,
            ["notification_receive", "notification_open"],
            errors=["notification_dismiss"],
        ),
        _event_count_ratio(
            "ai_glucose_setup",
            count_by_event,
            ["AI_Glucose_Setup_show_prompt", "AI_Glucose_Setup_finish_set_up"],
        ),
        _event_count_ratio(
            "ai_glucose_scan",
            count_by_event,
            ["Start_AI_Glucose_Scan", "First_AI_Glucose_Scan"],
        ),
    ]
    return [ratio for ratio in ratios if ratio]


def _event_count_ratio(
    name: str,
    counts: dict[str, float],
    steps: list[str],
    errors: list[str] | None = None,
) -> dict[str, Any] | None:
    step_counts = [{"step": step, "count": _round(counts.get(step.lower(), 0.0))} for step in steps]
    if not any(item["count"] for item in step_counts):
        return None

    first = float(step_counts[0]["count"])
    last = float(step_counts[-1]["count"])
    transitions = []
    for previous, current in zip(step_counts, step_counts[1:]):
        transitions.append(
            {
                "from": previous["step"],
                "to": current["step"],
                "ratio": _round(_safe_div(current["count"], previous["count"]), 4),
                "count_difference": _round(previous["count"] - current["count"]),
            }
        )

    error_count = 0.0
    if errors:
        error_count = sum(counts.get(error.lower(), 0.0) for error in errors)

    return {
        "name": name,
        "evidence_type": "aggregate_event_count_ratio",
        "safe_label": "aggregate event-count proxy ratio",
        "unsafe_label": "true funnel conversion rate",
        "interpretation_limit": "Not a true funnel: no user identity, session boundary, timestamp ordering, or deduplication.",
        "steps": step_counts,
        "step_ratios": transitions,
        "overall_ratio": _round(_safe_div(last, first), 4),
        "error_count": _round(error_count),
        "error_count_vs_first_step_ratio": _round(_safe_div(error_count, first), 4),
    }


def _cross_section_signals(sections: list[dict[str, Any]]) -> dict[str, Any]:
    largest_recent_changes = []
    critical_events = []

    for section in sections:
        if section.get("type") != "time_series":
            continue
        for metric in section.get("numeric_metrics", []):
            change = metric.get("recent_7_vs_previous_7_pct")
            if change is not None:
                largest_recent_changes.append(
                    {
                        "section": section["title"],
                        "metric": metric["metric"],
                        "recent_7_vs_previous_7_pct": change,
                    }
                )

        if section.get("type") == "event_table":
            critical_events.extend(section.get("error_summary", {}).get("top_error_events", [])[:5])

    largest_recent_changes = sorted(
        largest_recent_changes,
        key=lambda item: abs(item["recent_7_vs_previous_7_pct"]),
        reverse=True,
    )[:10]

    return {
        "largest_recent_metric_changes": largest_recent_changes,
        "top_error_events": critical_events[:10],
    }


def _records(df: pd.DataFrame, columns: list[str | None], limit: int) -> list[dict[str, Any]]:
    usable = [col for col in columns if col and col in df.columns]
    renamed = {"_event_name": "event_name", "_count": "event_count"}
    records = df[usable].head(limit).rename(columns=renamed).to_dict(orient="records")
    return _json_safe(records)


def _series_or_default(df: pd.DataFrame, col: str | None, default: float) -> pd.Series:
    if col and col in df.columns:
        return pd.to_numeric(df[col], errors="coerce").fillna(default)
    return pd.Series([default] * len(df), index=df.index)


def _metric_numeric_cols(df: pd.DataFrame) -> list[str]:
    index_names = {"nth_day", "nth day", "date", "day", "period"}
    numeric_cols = []
    for col in df.columns:
        if _norm(col) in index_names:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            numeric_cols.append(col)
    return numeric_cols


def _looks_like_app_version_columns(cols: list[str]) -> bool:
    if not cols:
        return False
    version_like = 0
    for col in cols:
        if re.match(r"^\d+(\.\d+){1,3}$", str(col)):
            version_like += 1
    return version_like >= max(2, int(len(cols) * 0.6))


def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    wanted = {_norm(candidate) for candidate in candidates}
    for col in df.columns:
        if _norm(col) in wanted:
            return col
    return None


def _choose_title(comments: list[str], header: list[str], index: int) -> str:
    generic = {"all users", "users", "overview"}
    for comment in reversed(comments):
        cleaned = comment.strip()
        if cleaned.lower() not in generic:
            return cleaned
    if comments:
        return comments[-1]
    return _title_from_header(header, index)


def _title_from_header(header: list[str], index: int) -> str:
    names = [_clean_cell(cell) for cell in header if _clean_cell(cell)]
    return ", ".join(names[:3]) if names else f"Section {index}"


def _comment_text(row: list[str]) -> str | None:
    if not row:
        return None
    first = _clean_cell(row[0])
    if not first.startswith("#"):
        return None
    return first.lstrip("#").strip()


def _parse_date_comment(comment: str) -> tuple[str | None, str | None]:
    match = re.match(r"^(start|end) date:\s*(.+)$", comment, re.IGNORECASE)
    if not match:
        return None, None
    return f"{match.group(1).lower()}_date", match.group(2).strip()


def _is_useful_comment(comment: str) -> bool:
    cleaned = comment.strip()
    if not cleaned:
        return False
    if set(cleaned) <= {"-"}:
        return False
    return True


def _is_blank_row(row: list[str]) -> bool:
    return all(_clean_cell(cell) == "" for cell in row)


def _clean_cell(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _safe_div(numerator: Any, denominator: Any) -> float | None:
    try:
        numerator = float(numerator)
        denominator = float(denominator)
    except (TypeError, ValueError):
        return None
    if denominator == 0:
        return None
    return numerator / denominator


def _guarded_percent(delta: Any, baseline: Any) -> float | None:
    try:
        if delta is None or baseline is None:
            return None
        baseline = float(baseline)
        delta = float(delta)
    except (TypeError, ValueError):
        return None
    if abs(baseline) < PERCENT_BASELINE_MIN:
        return None
    return _round(delta / baseline, 4)


def _direction(delta: float) -> str:
    if delta > 0:
        return "up"
    if delta < 0:
        return "down"
    return "flat"


def _warning(severity: str, code: str, message: str) -> dict[str, Any]:
    ranks = {"critical": 1, "high": 2, "medium": 3, "low": 4}
    return {
        "severity": severity,
        "severity_rank": ranks.get(severity, 99),
        "code": code,
        "message": message,
    }


def _pct(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value * 100:.1f}%"


def _round(value: Any, digits: int = 3) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, (int, str, bool)):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if not math.isfinite(number):
        return None
    if number.is_integer():
        return int(number)
    return round(number, digits)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return _round(value)
