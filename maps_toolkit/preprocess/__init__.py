from maps_toolkit.preprocess.engine import run_pipeline
import argparse


def preprocess(config_path: str) -> None:
    """Run the preprocess stage from a YAML config file path."""
    run_pipeline(config_path)


def cli() -> None:
    parser = argparse.ArgumentParser(description="maps-toolkit preprocess stage")
    parser.add_argument("--config", "-c", required=True, help="Path to preprocess YAML config")
    args = parser.parse_args()
    preprocess(args.config)
