"""
analytics.py — Main entry point.

Usage:
    python3 analytics.py <path_to_csv>
    python3 analytics.py <path_to_csv> --config custom_config.yaml

Pipeline:
    1. Load config.yaml
    2. Build parser + insight providers from config
    3. csv_parser: detect & label CSV sections
    4. insights:   analyse each section + generate final report
"""
import sys
from app_config import (
    CONFIG_PATH,
    completion_options,
    load_config,
    load_dotenv,
    runtime_options,
)
from providers import build_provider
import csv_parser
import insights

def main():
    args = sys.argv[1:]
    if not args:
        print("Usage:   python3 analytics.py <path_to_csv> [--config config.yaml]")
        print("Example: python3 analytics.py ./data/Firebase_overview_dashboard.csv")
        sys.exit(1)

    filepath    = args[0]
    config_path = CONFIG_PATH
    if "--config" in args:
        idx         = args.index("--config")
        if idx + 1 >= len(args):
            print("[ERROR] --config requires a path")
            sys.exit(1)
        config_path = args[idx + 1]

    print("\n" + "=" * 60)
    print("  FIREBASE ANALYTICS PIPELINE")
    print("=" * 60 + "\n")

    config = load_config(config_path)
    load_dotenv(config.get("env_file", ".env"))

    parser_cfg  = config.get("parser",  {})
    insight_cfg = config.get("insight", {})
    parser_options = completion_options(
        parser_cfg,
        default_max_tokens=15,
        default_temperature=0.0,
    )
    section_options = completion_options(
        insight_cfg,
        default_max_tokens=200,
        default_temperature=0.1,
        max_tokens_key="section_max_tokens",
    )
    report_options = completion_options(
        insight_cfg,
        default_max_tokens=800,
        default_temperature=0.1,
    )
    insight_runtime_options = runtime_options(insight_cfg)

    print(f"[config] Parser  provider : {parser_cfg.get('provider')} / {parser_cfg.get('model')}")
    print(f"[config] Insight provider : {insight_cfg.get('provider')} / {insight_cfg.get('model')}\n")

    parser_provider = build_provider(parser_cfg)

    # ── Step 1: Parse CSV ─────────────────────────────────────
    print("STEP 1 — Parsing CSV\n" + "-" * 30)
    csv_parser.init(parser_provider, parser_options)
    sections = csv_parser.parse(filepath)

    if not sections:
        print("[ERROR] No sections found.")
        sys.exit(1)

    # ── Step 2: Analyse sections ──────────────────────────────
    print("STEP 2 — Analysing sections\n" + "-" * 30)
    insight_provider = build_provider(insight_cfg)
    insights.init(
        insight_provider,
        section_options,
        report_options,
        insight_runtime_options,
    )
    section_insights = insights.analyse_all(sections)

    # ── Step 3: Final report ──────────────────────────────────
    print("STEP 3 — Generating report\n" + "-" * 30)
    insights.generate_report(section_insights)

if __name__ == "__main__":
    main()
