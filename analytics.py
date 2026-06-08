"""
analytics.py — Main entry point.

Usage:
    python3 analytics.py <path_to_csv>
    python3 analytics.py <path_to_csv> --config custom_config.yaml

Pipeline:
    1. Load config.yaml
    2. Build deterministic metrics with Pandas
    3. Send one compact analytics brief to the insight provider
    4. Print the final report
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
import insights
import metrics

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

    insight_cfg = config.get("insight", {})
    report_options = completion_options(
        insight_cfg,
        default_max_tokens=800,
        default_temperature=0.1,
    )
    insight_runtime_options = runtime_options(insight_cfg)
    print(f"[config] Insight provider : {insight_cfg.get('provider')} / {insight_cfg.get('model')}\n")

    # ── Step 1: Obtain Metrics ─────────────────────────────────────
    print("STEP 1 — Computing metrics\n" + "-" * 30)

    sections = metrics.load_df(filepath)
    metric_data = metrics.build_metrics(sections)

    # ── Step 2: Analyse sections ──────────────────────────────
    print("STEP 2 — LLM analysis\n" + "-" * 30)

    insight_provider = build_provider(insight_cfg)

    insights.init(insight_provider, report_options, insight_runtime_options)
    report = insights.analyse(metric_data)

    # ── Step 3: Final report ──────────────────────────────────
    print("STEP 3 — Report\n" + "-" * 30)

    print(report)

if __name__ == "__main__":
    main()
