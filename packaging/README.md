# Packaging — Parametric Generators

Script for parametric die-cut path generation for standard packaging.
Compatible with Rhino 7 and 8..

## Available scripts

| Script | Tipologia ECMA | Descrizione |
|--------|---------------|-------------|
| `ECMA_A20_20_03_01.py` | ECMA A20.20.03.01 | Tuck-end case, staggered flaps |
| `ECMA_A20_20_01_01.py` | ECMA A20.20.01.01 | Tuck-end case, aligned flaps |
| `ECMA_A01_55_00_01.py` | ECMA A01.55.00.01 | Crash-lock bottom |
| `FEFCO_0412.py` | FEFCO 0412 | One Piece Folder |


## Conventions

- **Cut" Layer** (black): cutting lines
- **Crease" Layer** (red): crease lines
- **Punch" Layer** (blue): perforation lines
- **Units:** millimeters
- **Cardboard thickness:** parametric, with automatic compensation
