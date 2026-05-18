import argparse
import time
import json
import os

from maps_toolkit.reconstruct.core.config_loader import load_config
from maps_toolkit.reconstruct.core.data_processor import DataProcessor


def main():
    parser = argparse.ArgumentParser(description='Process prescription and culture data.')
    parser.add_argument(
        '--config',
        type=str,
        required=True,
        help='Path to configuration YAML file (e.g. configs/reconstruct.yaml)',
    )
    parser.add_argument(
        '--skip-summary',
        action='store_true',
        help='Skip summary calculation and printing',
    )
    args = parser.parse_args()

    start_all = time.time()

    t0 = time.time()
    config = load_config(args.config)
    print(f"[Timer] Config loaded in {time.time() - t0:.2f} seconds")

    t0 = time.time()
    processor = DataProcessor(config)
    print(f"[Timer] DataProcessor initialized in {time.time() - t0:.2f} seconds")

    t0 = time.time()
    result = processor.process_data()
    print(f"[Timer] Data processed in {time.time() - t0:.2f} seconds")

    t0 = time.time()
    processor.save_output(result)
    print(f"[Timer] Output saved in {time.time() - t0:.2f} seconds")

    skip_summary = args.skip_summary or os.environ.get("RECONSTRUCT_SKIP_SUMMARY") == "1"
    if not skip_summary:
        t0 = time.time()
        summary = processor.summarize_output(result)
        print(json.dumps(summary, indent=2))
        print(f"[Timer] Summary calculated in {time.time() - t0:.2f} seconds")

    print(f"[Timer] Total execution time: {time.time() - start_all:.2f} seconds")


if __name__ == "__main__":
    main()
