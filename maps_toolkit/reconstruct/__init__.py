from maps_toolkit.reconstruct.main import main as _main
import argparse


def reconstruct(config_path: str) -> None:
    """Run the reconstruct stage from a YAML config file path."""
    import sys
    sys.argv = ["maps-reconstruct", "--config", str(config_path)]
    _main()


def cli() -> None:
    parser = argparse.ArgumentParser(description="maps-toolkit reconstruct stage")
    parser.add_argument("-c", "--config", required=True, help="Path to reconstruct YAML config")
    args = parser.parse_args()
    reconstruct(args.config)
