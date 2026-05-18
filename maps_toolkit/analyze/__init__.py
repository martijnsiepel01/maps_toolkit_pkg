from maps_toolkit.analyze.analysis_runner import run_analysis
import argparse


def analyze(config_path: str) -> None:
    """Run the analyze stage from a YAML config file path."""
    run_analysis(config_path)


def cli() -> None:
    parser = argparse.ArgumentParser(description="maps-toolkit analyze stage")
    parser.add_argument("--config", "-c", required=True, help="Path to analyze YAML config")
    args = parser.parse_args()
    analyze(args.config)
