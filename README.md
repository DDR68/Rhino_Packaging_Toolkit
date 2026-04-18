# Rhino Parametric Packaging

An open-source toolkit for **structural packaging design** in Rhinoceros 7 & 8.

IronPython scripts that automate the most time-consuming parts of folding carton development: parametric die-cut generation, dimensioning, prepress preparation, and diagnostic checks — all running inside Rhino's built-in script editor with zero external dependencies.

> **Who is this for?** Packaging designers and structural engineers (*cartotecnici*) who use Rhino as their CAD environment and want to replace repetitive manual drawing with parametric, reusable scripts.

---

## Structure

```
packaging/          Parametric ECMA die-cut generators
utilities/          Dimensioning, crosshair markers, diagnostics
prepress/           Production file preparation and export
docs/               Guides and documentation
```

---

## Packaging — Parametric Generators

Each script takes basic box dimensions — width, depth, height, board thickness — and produces a complete, production-ready die-cut layout at the origin.

| Script | ECMA Code | Box Style | Status | Img. |
|--------|-----------|-----------|--------|----|
| `ECMA_A20_20_03_01.py` | A20.20.03.01 | Reverse Tuck End | ✅ Published | ![    ](docs/Example_ECMA_A20_20_03_01.png) |
| `ECMA_A20_20_01_01.py` | A20.20.01.01 | Straight Tuck End | ✅ Published | ![    ](docs/Example_ECMA_A20_20_01_01.png) |

**Input parameters:**
- **L** — Width (main panel)
- **P** — Depth (side panel)
- **A** — Height (box body)
- **S** — Board thickness (0.5–1.0 mm)

Internal parameters (glue tab width, tuck hook length, chamfer radius) are exposed as constants at the top of each script for fine-tuning.

**Output layers:**

| Layer | Color | Purpose |
|-------|-------|---------|
| **Taglio** | Black | Cut lines (die knife) |
| **Cordone** | Red | Crease / score lines (creasing rule) |

---

## Utilities

Helper scripts for everyday packaging CAD work in Rhino:

- **Dimensioning** — Automated dimension placement for die-cut layouts
- **Crosshair markers** — Registration marks and reference points
- **Diagnostics** — Geometry validation, layer checks, curve analysis

---

## Prepress

Scripts for preparing files for production output:

- **Geometry export** — Clean export of cut/crease geometry
- **Bounding-box detection** — Automatic format identification
- **Production preparation** — Layer cleanup, metadata tagging, file organization

---

## How It Works

Every script in this toolkit follows the same conventions:

- **Pure RhinoCommon** — no `rhinoscriptsyntax`, no plugins, no external packages. Drop a `.py` file into Rhino's editor and run it.
- **IronPython 2.7** compatible — uses the scripting engine built into Rhino 7 and 8.
- **Separate cut/crease layers** — output always uses `Taglio` (black, cut) and `Cordone` (red, crease) layers, matching standard industry practice.
- **Metadata storage** — layouts store their parameters in `doc.Strings` (Rhino's UserDictionary) for later retrieval.

---

## Getting Started

1. Download or clone this repository.
2. Open **Rhinoceros 7 or 8** (Windows).
3. Run `EditPythonScript` (or `_EditPythonScript`).
4. Open any `.py` file from the relevant folder.
5. Run the script — it will prompt for any required input.

No installation, no package manager, no setup.

---

## ECMA Reference

The parametric generators implement styles from **ECMA** (*EUROPEAN CARTON MAKERS ASSOCIATION*).

The ECMA code structure:
- **A** — Tuck-end styles (integral closure flaps)
- **20.20** — Rectangular base, rectangular body
- **xx.xx** — Specific tuck and flap configuration

The standard is freely available at [ecma-international.org](https://www.ecma-international.org).

---

## Roadmap

This toolkit is actively growing. Planned additions:

**Packaging generators**
- [ ] ECMA A20.20.02.01 — Tuck and tongue
- [ ] ECMA A55 — Auto-lock bottom
- [ ] FEFCO 0421 — Corrugated tray
- [ ] Hexagonal box with handle
- [ ] Geometric solids (dodecahedron with snap-fit assembly)

**Utilities & prepress**
- [ ] Automatic nesting / step-and-repeat
- [ ] PDF/DXF batch export with layer mapping
- [ ] Material usage calculator

Contributions, suggestions, and feedback are welcome — open an issue or submit a pull request.

---

## Background

This project comes from professional experience in *cartotecnica* — structural packaging design and die-cutting for production. The scripts encode years of hands-on knowledge about panel geometry, material compensation, and manufacturing constraints into reusable, inspectable code.

AI-assisted development (Claude by Anthropic) is used as a collaborative tool in the design and scripting process.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

Free to use, modify, and distribute. Attribution appreciated.
