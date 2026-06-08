"""
csv_parser.py — Reads any CSV and splits it into named sections.
Uses the parser provider (from config) only to NAME unnamed sections.
"""
import os
import sys
import re

_parser_provider = None
_parser_options = {"max_tokens": 15, "temperature": 0.0}

def init(provider, options=None):
    """Inject the parser provider (called from analytics.py)."""
    global _parser_provider, _parser_options
    _parser_provider = provider
    _parser_options = {"max_tokens": 15, "temperature": 0.0}
    if options:
        _parser_options.update(options)

def unload():
    """Release parser model from RAM after parsing is done."""
    global _parser_provider
    if _parser_provider is not None:
        _parser_provider.unload()
        _parser_provider = None


def read_file(filepath: str) -> list:
    if not os.path.exists(filepath):
        print(f"[ERROR] File not found: {filepath}")
        sys.exit(1)
    with open(filepath, encoding="utf-8") as f:
        return f.readlines()


def detect_sections(lines: list) -> list:
    sections      = []
    current_title = None
    current_start = None
    pending_title = None

    def is_blank(line):
        return line.strip().rstrip(",").strip() == ""

    def is_comment(line):
        return line.strip().startswith("#")

    def clean_comment(line):
        text = line.strip().lstrip("#").strip().rstrip(",").strip()
        if re.match(r"^(start|end) date:", text, re.IGNORECASE):
            return None
        return text if len(text) > 3 else None

    def save(end_idx):
        nonlocal current_title, current_start
        if current_start is not None and end_idx > current_start:
            sections.append({
                "title": current_title or "Section",
                "start": current_start,
                "end":   end_idx - 1
            })
        current_title = None
        current_start = None

    for i, line in enumerate(lines):
        if is_blank(line):
            save(i)
            current_title = pending_title
            pending_title = None
        elif is_comment(line):
            label = clean_comment(line)
            if label:
                pending_title = label
        else:
            if current_start is None:
                current_start = i
                if current_title is None:
                    current_title = pending_title or "Section"
                    pending_title = None

    save(len(lines))
    return [s for s in sections if (s["end"] - s["start"]) >= 1]


NAMING_SYSTEM = "Return a short title (5 words max) for this CSV section. Respond with ONLY the title."

def name_section(header: str, sample: str) -> str:
    if _parser_provider is None:
        return header
    try:
        return _parser_provider.complete(
            system      = NAMING_SYSTEM,
            user        = f"Header: {header}\nSample:\n{sample}",
            max_tokens  = _parser_options["max_tokens"],
            temperature = _parser_options["temperature"]
        )
    except Exception:
        return header


def extract_sections(lines: list, sections_map: list) -> list:
    results = []
    for section in sections_map:
        title = section.get("title", "Section")
        start = max(0, section["start"])
        end   = min(len(lines) - 1, section["end"])

        data_lines = []
        for line in lines[start:end + 1]:
            cleaned = line.strip().rstrip(",").strip()
            if cleaned and not cleaned.startswith("#"):
                data_lines.append(cleaned)

        if len(data_lines) < 2:
            continue

        if title in ("Section", "General") or not title:
            header = data_lines[0]
            sample = "\n".join(data_lines[1:4])
            title  = name_section(header, sample)

        results.append({
            "title":     title,
            "data":      "\n".join(data_lines),
            "row_count": len(data_lines) - 1
        })

    return results


def parse(filepath: str) -> list:
    print(f"[csv_parser] Reading: {filepath}")
    lines = read_file(filepath)
    print(f"[csv_parser] Total lines: {len(lines)}")

    print("[csv_parser] Detecting sections...")
    sections_map = detect_sections(lines)
    print(f"[csv_parser] Found {len(sections_map)} raw sections.")

    print("[csv_parser] Labelling sections...")
    sections = extract_sections(lines, sections_map)

    unload()  # free parser model RAM before insights model loads

    print(f"\n[csv_parser] Done — {len(sections)} sections:")
    for i, s in enumerate(sections):
        print(f"  {i+1}. '{s['title']}' — {s['row_count']} data rows")
    print()

    return sections
