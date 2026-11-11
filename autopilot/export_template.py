"""Baut aus diesem Repo eine saubere Verkaufsvorlage:
Code, Workflows, Formate und Regeln – ohne deine Posts, Zahlen, Tokens und Markendaten.

  python -m autopilot.export_template            → dist/insta-autopilot-vorlage-<datum>.zip
  python -m autopilot.export_template --with-case → zusätzlich deine Fallstudie (Meilensteine + Wirkung)
"""
from __future__ import annotations

import argparse
import shutil
import tempfile
import zipfile
from pathlib import Path

import yaml

from .common import DATA, ROOT, load_config, now

INCLUDE = ["autopilot", ".github", "README.md", "requirements.txt", ".gitignore"]
PLACEHOLDER_BRAND = {"name": "DEIN PAGE-NAME", "handle": "@deinhandle"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-case", action="store_true", help="Fallstudie mit echten Zahlen beilegen")
    args = ap.parse_args()

    cfg = load_config()
    tmp = Path(tempfile.mkdtemp()) / "insta-autopilot"
    tmp.mkdir()
    for name in INCLUDE:
        src = ROOT / name
        if src.is_dir():
            shutil.copytree(src, tmp / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        elif src.exists():
            shutil.copy2(src, tmp / name)

    # Config: alles behalten (Formate, Regeln, Säulen = dein Know-how), Marke neutralisieren
    cfg["brand"].update(PLACEHOLDER_BRAND)
    (tmp / "config.yaml").write_text(
        "# Insta-Autopilot – Vorlage. Mindestens brand.name und brand.handle anpassen.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False, width=110), encoding="utf-8")

    # leere Arbeitsordner
    for d in ("queue", "posted", "data", "content", "docs"):
        (tmp / d).mkdir(exist_ok=True)
    (tmp / "queue" / ".gitkeep").touch()
    (tmp / "posted" / ".gitkeep").touch()
    (tmp / "data" / "history.json").write_text("[]\n", encoding="utf-8")
    (tmp / "data" / "state.json").write_text("{}\n", encoding="utf-8")
    (tmp / "content" / "journal.md").write_text(
        "# Journal\n\nStichworte zum Aufbau deiner Page – einzige Quelle für Making-of-Fakten.\n"
        "Änderungen am Setup als `- Meilenstein: …` unter dem Datum eintragen.\n\n"
        f"## {now(cfg):%d.%m.%Y}\n- Meilenstein: Start\n", encoding="utf-8")

    if args.with_case:
        case = tmp / "FALLSTUDIE.md"
        parts = ["# Fallstudie – so hat sich das Original entwickelt\n"]
        for f in ("impact.md", "learnings.md"):
            if (DATA / f).exists():
                parts.append((DATA / f).read_text(encoding="utf-8"))
        case.write_text("\n\n".join(parts), encoding="utf-8")

    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"insta-autopilot-vorlage-{now(cfg):%Y-%m-%d}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(tmp.rglob("*")):
            if p.is_file():
                z.write(p, Path("insta-autopilot") / p.relative_to(tmp))
    print(f"✓ Vorlage: {out}")


if __name__ == "__main__":
    main()
