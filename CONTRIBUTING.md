# Contributing to the PelRos reference library

Thank you! Every entry makes material identification in PelRos better for everyone.

## Ground rules

- **Only numbers from the cited source.** Copy positions as printed (do not round further, do not convert units
  except where noted). If you are not sure the paper contains exactly these numbers, write `where: "recalled — check"`;
  such entries stay `unverified`.
- **One file = one material + one technique + one source.** Two papers for the same material are two files.
- **A real DOI** (bare, e.g. `10.1103/PhysRevB.75.165202`). Prefer primary sources: single-crystal or well-cited
  reference papers, ICDD/COD-based pattern papers, handbooks with DOIs. No DOI → not in the library.
- **`source.title` exactly as on the DOI page** (https://doi.org/…) and the year in `citation` — the automatic check
  compares both with Crossref.
- Do not set `status` yourself: leave `unverified`. The check sets `doi_verified`; maintainers set `values_verified`
  after reading the paper.

## Per technique

| technique | `peaks[].position` | also | `conditions` worth giving |
|---|---|---|---|
| Raman (`raman`) | Raman shift, cm⁻¹ | `label` = mode (E2g, A1g, D, G, …) | `laser_nm`, `form`, `temperature_K` |
| FTIR (`ftir`) | wavenumber, cm⁻¹ | `label` = vibration (C=O stretch …) | `mode` (ATR / transmission / DRIFTS) |
| XRD (`xrd`) | 2θ in degrees **for the stated radiation** | `d` in Å (**required**), `hkl` in quotes, intensity 0–100 | `radiation`, `wavelength_A` |
| UV-Vis (`uvvis`) | — use `values` | `quantity`: band_gap_direct / band_gap_indirect / absorption_max / exciton | `form`, `temperature_K` |
| PL (`pl`) | — use `values` | `quantity`: emission_max / exciton | `laser_nm`, `temperature_K` |

Intensities: `s`, `m`, `w`, `vw` (strong … very weak) unless the source gives numbers (then 0–100, strongest = 100).
PelRos converts XRD `d` to 2θ for the user's wavelength, so `d` is what makes an entry usable on any instrument.

## File naming

`entries/<technique>/<material>-<phase>-<firstauthor><year>.yaml`, lowercase, words joined by `-`:
`entries/xrd/tio2-anatase-howard1991.yaml`. The `id` inside is the same path without `entries/` and `.yaml`:
`id: xrd/tio2-anatase-howard1991`.

## How to submit

Use the GitHub web editor as described in the [README](README.md#contributing-no-programming-needed), or fork and
open a pull request from the command line. Before pushing you can run the checks locally:

```bash
pip install -r tools/requirements.txt
python tools/validate.py entries/raman/your-file.yaml --check-doi
```

## Reviewing (maintainers)

1. The pull-request check must be green (schema + Crossref).
2. Open the paper at `where` and compare a few numbers. If they all match, you may set `status: values_verified`
   (and `checked:` to today) in the same pull request or later.
3. Merge. The workflow on `main` marks the DOI status, rebuilds `dist/library.json` and commits it.

## Licence

Contributions are published under CC BY 4.0 (data) and MIT (tools); see the README.
