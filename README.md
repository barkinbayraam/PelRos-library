# PelRos reference library

An open, citable library of reference values for materials characterization — Raman and FTIR band positions,
XRD reflections (2θ **and** d-spacings), UV-Vis band gaps and PL emission energies — used by
[PelRos](https://github.com/barkinbayraam/PelRos) to suggest candidate materials and to overlay reference lines on
your spectra. Every entry cites the paper its numbers come from, by DOI.

PelRos ships a snapshot of this library and, when it starts, downloads the newest
[`dist/library.json`](dist/library.json) (at most once a day; it keeps working offline).

## What an entry looks like

One YAML file per material + technique + source, in `entries/<technique>/<slug>.yaml`:

```yaml
id: raman/zno-wurtzite-cusco2007
technique: raman            # raman | ftir | xrd | uvvis | pl
material: ZnO (wurtzite)
formula: ZnO
category: oxide
conditions: {form: single crystal, temperature_K: 295, laser_nm: 532}
peaks:
  - {position: 438, intensity: s, label: E2 (high)}
  - {position: 574, intensity: w, label: A1(LO)}
source:
  doi: 10.1103/PhysRevB.75.165202
  citation: "Cuscó et al., Phys. Rev. B 75, 165202 (2007)"
  title: "Temperature dependence of Raman scattering in ZnO"
  where: "Table I"
status: doi_verified
checked: 2026-10-22
```

The full field list is in [SCHEMA.md](SCHEMA.md) (machine-readable: [schema/entry.schema.json](schema/entry.schema.json));
a commented starting point is [templates/entry.yaml](templates/entry.yaml).

## Status — how far an entry has been checked

| status | badge in PelRos | meaning |
|---|---|---|
| `unverified` | grey "unverified" | Entered by a contributor; the DOI has not been confirmed yet (or did not match). |
| `doi_verified` | green "DOI verified" | **Set automatically**: the DOI resolves on Crossref and the paper's title and year match the entry's `title`/`citation`. It says the *reference is real and is the one cited*; it does **not** say the numbers were checked against the paper. Entries whose `source.where` says the numbers were *recalled* (not read in the paper) stay `unverified` even when the DOI is fine. |
| `values_verified` | bold "values verified" | A maintainer compared the numbers with the paper (`where`) by hand. Only humans set this. |

Values shift with crystallite size, strain, doping, temperature, the laser (Raman of carbons), the ATR crystal
(FTIR) and the radiation (XRD 2θ — use `d` across instruments). Treat matches as candidates, not proof.

## Contributing (no programming needed)

The easiest way is GitHub's web editor — you need only a free GitHub account:

1. Open the folder for your technique, e.g. [`entries/raman`](entries/raman), and click **Add file → Create new file**.
   GitHub offers to *fork* the repository: accept.
2. Name the file `<material>-<phase>-<firstauthor><year>.yaml` (lowercase, `-` between words), paste
   [templates/entry.yaml](templates/entry.yaml) and fill it in: numbers exactly as printed in the paper, the bare DOI,
   the title as on the DOI page, and *where* in the paper the numbers are (e.g. "Table 2").
3. Leave `status: unverified`. Click **Commit changes → Propose changes → Create pull request**.
4. A check runs automatically: it validates the file and looks the DOI up on Crossref. If it reports a problem,
   edit the file in your pull request (pencil icon) and the check runs again.
5. A maintainer reviews and merges; the robot then marks the entry `doi_verified`, rebuilds `dist/library.json`,
   and PelRos picks it up at its next start.

To correct an existing entry, open it and click the pencil icon — same flow. Details and conventions:
[CONTRIBUTING.md](CONTRIBUTING.md).

## For maintainers

```bash
pip install -r tools/requirements.txt
python tools/validate.py                 # schema, unique ids, id = path, XRD peaks have d, plausible ranges
python tools/validate.py --check-doi     # + Crossref: DOI exists, title (fuzzy ≥ 0.85) and year match
python tools/validate.py --check-doi --write-status   # + set status doi_verified / checked
python tools/build.py                    # dist/library.json (version = build date)
python -m unittest discover -s tests     # self-test of the tools
```

The workflow [.github/workflows/validate.yml](.github/workflows/validate.yml) runs the checks on every pull request;
on a push to `main` it also writes the DOI status, rebuilds `dist/library.json` and commits both (only if something
changed). Set `values_verified` yourself after comparing an entry with the paper.

## Licence

The **data** in this repository (everything under `entries/` and `dist/`) is licensed under
[Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/):
you may share and adapt it for any purpose, also commercially, if you give appropriate credit — cite
"PelRos reference library, https://github.com/barkinbayraam/PelRos-library" **and the original paper of each entry**.
Numerical values reported in the literature are facts; the credit for them belongs to the cited authors.
The tools (`tools/`, `schema/`, `.github/`) are under the MIT licence. By contributing you agree that your
contribution is published under these licences.
