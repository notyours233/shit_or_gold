# Material Property Extraction

This folder contains the cleaned project files for the material-property extraction workflow.

## Structure

- `main_extract.py` - main extractor implementation.
- `extract.py` - compatibility entrypoint that runs `main_extract.py`.
- `data/` - original Excel input files.
- `results/final_review_package_20260415/` - final cleaned review package with records missing DOI removed.
- `legacy_reaction_extractors/` - older reaction-specific extractor scripts kept for reference or reuse.
- `docs/` - project notes and supporting documents.
- `downstream_projects/` - place future downstream projects here.

## Current Final Results

The final review package contains 6,870 records:

- antiferromagnetism: 1,263
- conductivity: 1,542
- ferrimagnetism: 66
- ferromagnetism: 882
- photothermal conversion efficiency: 1,687
- thermal conductivity: 1,430

Main files:

- `results/final_review_package_20260415/all_results.csv`
- `results/final_review_package_20260415/all_results.jsonl`
- `results/final_review_package_20260415/by_property/`
- `results/final_review_package_20260415/summary.json`

## Run

Create a fresh environment when needed:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python extract.py --help
```

Use `.env.example` as the template for local API configuration.
