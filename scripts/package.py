"""Build an allowlisted local installation ZIP without private reference files."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "dist" / "homewizard_legacy-0.1.0.zip"
DEST.parent.mkdir(exist_ok=True)
with ZipFile(DEST, "w", ZIP_DEFLATED) as archive:
    for file in sorted((ROOT / "custom_components" / "homewizard_legacy").rglob("*")):
        if file.is_file() and file.suffix in {".py", ".json", ".png", ".svg"}:
            archive.write(file, file.relative_to(ROOT))
    for name in ("README.md", "ENDPOINTS.md", "LICENSE", "hacs.json"):
        archive.write(ROOT / name, name)
print(DEST)
