# 2024 Validation Sources

Author: Max Stoddard

This folder contains the tracked source artifacts required to review and reproduce the 2024 validation catalog without relying on ignored `private-datasets/` paths.

Contents:
- `cis/`: frozen FPC June 2024 PDF and text extraction aid
- `ukf/`: UK Finance source PDFs and validation evidence notes for advances and rental yield
- `boe/`: housing-tools workbook and spread evidence note
- `mlar/`: MLAR workbook and owner-occupier debt-to-income evidence note
- `ons/`: minimal repo-local QWND snapshot used for the owner-occupier debt-to-income denominator

These files are tracked because they are the authoritative source snapshots referenced by:
- `scripts/python/validation/model/validation_catalog_2024.py`
- `scripts/python/validation/model/catalog_review_2024.py`
- `input-data-versions/validation/*.json`

The `ons/` snapshot keeps the original ONS series URL as contextual metadata, but the validation workflow should use the repo-local snapshot path as the authoritative source for reproducibility.
