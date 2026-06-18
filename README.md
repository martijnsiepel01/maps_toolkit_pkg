# maps-toolkit

A three-stage pipeline for analysing hospital antimicrobial treatment data.

The toolkit converts raw electronic-health-record exports into a nested,
patient-centric JSON of antimicrobial treatment episodes, then runs
configurable plugin-based analyses on that structure.

## Pipeline stages

| Stage | Purpose | Input | Output |
|---|---|---|---|
| **preprocess** | Clean and normalise raw EHR exports using a sequence of declarative steps. | One or more delimited files (TSV/CSV) | One processed table per source. |
| **reconstruct** | Merge processed tables into a hierarchical structure: patients → admissions → treatment episodes. | Processed tables + a `reconstruct.yaml` describing source roles. | A single nested JSON file. |
| **analyze** | Run plugin-based analyses (e.g. treatment duration, IV-to-oral switches, culture appropriateness) on the reconstructed JSON. | Reconstructed JSON + an `analyze/<analysis>.yaml`. | One CSV per analysis. |

Each stage is driven by a YAML config and can be invoked from Python or
the command line.

## Installation

```bash
pip install git+https://github.com/martijnsiepel01/maps_toolkit_pkg.git
```

For development:

```bash
git clone https://github.com/martijnsiepel01/maps_toolkit_pkg.git
cd maps_toolkit_pkg
pip install -e .[dev]
```

Requires Python 3.9 or newer.

## Usage

### Python API

```python
import maps_toolkit

maps_toolkit.preprocess("configs/preprocess.yaml")
maps_toolkit.reconstruct("configs/reconstruct.yaml")
maps_toolkit.analyze("configs/analyze/treatment_duration.yaml")
```

### Command line

```bash
maps-preprocess  -c configs/preprocess.yaml
maps-reconstruct -c configs/reconstruct.yaml
maps-analyze     -c configs/analyze/treatment_duration.yaml
```

## Custom steps and plugins

Institutions plug in their own logic by pointing YAML configs at Python
files containing custom preprocess steps or analyze plugins. No code
changes to `maps_toolkit` itself are required.

```yaml
# configs/preprocess.yaml
sources:
  - name: prescriptions
    steps:
      - { fn: drop_nulls, columns: [patient_id] }
      - { fn: my_custom_clean, module: configs/custom_steps.py }
```

```yaml
# configs/analyze/my_analysis.yaml
plugin:
  fn: count_episodes_per_patient
  module: configs/my_plugins.py
```

## Reference implementation

A complete worked example on MIMIC-IV data — including real configs,
custom steps, custom plugins, and an end-to-end Jupyter notebook — lives
in the companion repository:
<https://github.com/martijnsiepel01/MAPS_toolkit>.

## Citation

This package implements the MAPS method described in the paper. If you
use it, please cite:

```bibtex
@article{siepel_maps_2026,
  title   = {TODO: paper title once published},
  author  = {Siepel, Martijn},
  journal = {TODO: venue},
  year    = {2026},
  doi     = {TODO: DOI once published}
}
```

## License

MIT — see [LICENSE](LICENSE).
