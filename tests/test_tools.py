"""Self-test of tools/validate.py and tools/build.py (stdlib unittest; no network)."""
import io
import json
import shutil
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
import build as B  # noqa: E402
import validate as V  # noqa: E402


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_for(records):
    """records: doi → Crossref message (None → 404)."""
    def op(req, timeout=None):
        doi = req.full_url.split("/works/")[1].split("?")[0].replace("%2F", "/")
        if records.get(doi) is None:
            raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, None)
        return FakeResp(json.dumps({"message": records[doi]}).encode())
    return op


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(HERE / "fixtures" / "entries", self.tmp / "entries")
        self._root, self._entries = V.ROOT, V.ENTRIES
        V.ROOT, V.ENTRIES = self.tmp, self.tmp / "entries"

    def tearDown(self):
        V.ROOT, V.ENTRIES = self._root, self._entries
        shutil.rmtree(self.tmp)


class TestValidate(Base):
    def test_fixtures_are_valid(self):
        items, rep = V.validate()
        self.assertEqual(len(items), 3)
        self.assertEqual(rep.errors, [])

    def test_errors_are_found(self):
        p = self.tmp / "entries" / "xrd" / "zno-wurtzite-test2001.yaml"
        t = p.read_text().replace("d: 2.8143, ", "").replace('hkl: "002"', "hkl: 002").replace("31.770", "331.770")
        p.write_text(t)
        bad = self.tmp / "entries" / "raman" / "copy.yaml"
        bad.write_text((self.tmp / "entries" / "raman" / "si-crystalline-test2000.yaml").read_text())
        _, rep = V.validate()
        msgs = " | ".join(m for _, m in rep.errors)
        self.assertIn("need the d-spacing", msgs)
        self.assertIn("must be quoted", msgs)
        self.assertIn("outside the plausible xrd range", msgs)
        self.assertIn("id must be 'raman/copy'", msgs)
        self.assertIn("duplicate id", msgs)

    def test_two_theta(self):
        self.assertAlmostEqual(V.two_theta(2.4759, 1.540598), 36.253, places=2)
        self.assertIsNone(V.two_theta(0.5, 1.54))


class TestDoi(Base):
    def test_title_normalisation(self):
        self.assertGreater(V.title_ratio("Raman of BaTiO<sub>3</sub> – phonons", "Raman of BaTiO₃ - phonons"), 0.95)
        self.assertEqual(V.citation_year("A, Phys. Rev. B 58, 14256 (1998)"), 1998)

    def test_check_and_write_status(self):
        items, rep = V.validate()
        recs = {
            "10.1000/test.1": {"title": ["Raman Scattering in Crystalline Silicon"], "issued": {"date-parts": [[2000, 3]]}},
            "10.1000/test.2": {"title": ["A different paper altogether about polymers"], "issued": {"date-parts": [[2001]]}},
            "10.1000/test.3": None,
        }
        client = V.Crossref(min_interval=0, retries=1, opener=opener_for(recs))
        st = V.check_dois(items, rep, write=True, client=client, today="2026-10-22")
        self.assertEqual((st["ok"], st["mismatch"], st["not_found"]), (1, 1, 1))
        si = V.load(self.tmp / "entries" / "raman" / "si-crystalline-test2000.yaml")
        self.assertEqual((si["status"], si["checked"]), ("doi_verified", "2026-10-22"))
        zno = V.load(self.tmp / "entries" / "xrd" / "zno-wurtzite-test2001.yaml")
        self.assertEqual(zno["status"], "unverified")
        self.assertTrue(any("title does not match" in m for _, m in rep.errors))

    def test_year_mismatch(self):
        e = {"source": {"title": "X Y Z", "citation": "A, J 1, 1 (1999)"}}
        self.assertTrue(V.compare(e, {"title": ["X Y Z"], "issued": {"date-parts": [[2005]]}}))
        self.assertFalse(V.compare(e, {"title": ["X Y Z"], "issued": {"date-parts": [[1999]]}}))


class TestBuild(Base):
    def test_build_versions(self):
        out = self.tmp / "dist" / "library.json"
        r = B.build(self.tmp, out, today="2026-10-22")
        lib = json.loads(out.read_text())
        self.assertTrue(r["changed"])
        self.assertEqual((lib["version"], lib["count"]), ("2026.10.22", 3))
        self.assertEqual(lib["entries"][0]["id"], "raman/si-crystalline-test2000")
        self.assertEqual(lib["entries"][1]["checked"], "2026-01-01")  # YAML date → string
        self.assertFalse(B.build(self.tmp, out, today="2026-10-22")["changed"])
        p = self.tmp / "entries" / "raman" / "si-crystalline-test2000.yaml"
        p.write_text(p.read_text().replace("520.7", "520.5"))
        self.assertEqual(B.build(self.tmp, out, today="2026-10-22")["version"], "2026.10.22.2")


if __name__ == "__main__":
    unittest.main()
