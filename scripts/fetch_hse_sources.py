#!/usr/bin/env python3
"""Fetch, clean, and save the 40 HSE construction source pages as Markdown.

Deterministic extraction only (BeautifulSoup + html2text) -- no LLM rewriting,
so content is never paraphrased. Pages that cannot be fetched or cleanly
extracted are logged to data/rejected_sources.csv and skipped.

Writes:
    data/raw_sources/hse/<doc_id>.md   (with YAML frontmatter)
    data/rejected_sources.csv          (any skipped sources)
    appends rows to data/sources.csv   (for each successfully added doc)

Usage:
    python scripts/fetch_hse_sources.py
"""

from __future__ import annotations

import csv
import io
import sys
from datetime import date
from pathlib import Path

import html2text
import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "data" / "raw_sources" / "hse"
SOURCES_CSV = PROJECT_ROOT / "data" / "sources.csv"
REJECTED_CSV = PROJECT_ROOT / "data" / "rejected_sources.csv"

SOURCE_ORG = "Health and Safety Executive (HSE)"
LICENCE = "Open Government Licence v3.0 unless otherwise stated"
RETRIEVED_AT = date.today().isoformat()

HEADERS = {"User-Agent": "Mozilla/5.0 (research; NLP assignment corpus builder)"}

# doc_id, title, url, category
SOURCES = [
    ("hse_001", "Planning for construction work", "https://www.hse.gov.uk/construction/safetytopics/planning.htm", "safety_planning"),
    ("hse_002", "Site rules and induction", "https://www.hse.gov.uk/construction/safetytopics/site-rules-induction.htm", "safety_planning"),
    ("hse_003", "Traffic management on site", "https://www.hse.gov.uk/construction/safetytopics/vehiclestrafficmanagement.htm", "site_traffic"),
    ("hse_004", "Site lighting", "https://www.hse.gov.uk/construction/safetytopics/site-lighting.htm", "site_management"),
    ("hse_005", "Protecting the public", "https://www.hse.gov.uk/construction/safetytopics/publicprotection.htm", "public_safety"),
    ("hse_006", "Materials storage and waste management", "https://www.hse.gov.uk/construction/safetytopics/storage.htm", "site_management"),
    ("hse_007", "Administration", "https://www.hse.gov.uk/construction/safetytopics/admin.htm", "site_management"),
    ("hse_008", "Assessing all work at height", "https://www.hse.gov.uk/construction/safetytopics/assess.htm", "work_at_height"),
    ("hse_009", "Roof work", "https://www.hse.gov.uk/construction/safetytopics/roofwork.htm", "work_at_height"),
    ("hse_010", "Fragile surfaces", "https://www.hse.gov.uk/construction/safetytopics/fragile.htm", "work_at_height"),
    ("hse_011", "Using ladders safely", "https://www.hse.gov.uk/construction/safetytopics/ladders.htm", "work_at_height"),
    ("hse_012", "Scaffolds", "https://www.hse.gov.uk/construction/safetytopics/scaffoldinginfo.htm", "work_at_height"),
    ("hse_013", "Tower scaffolds", "https://www.hse.gov.uk/construction/safetytopics/scaffold.htm", "work_at_height"),
    ("hse_014", "Mobile elevating work platforms", "https://www.hse.gov.uk/construction/safetytopics/mewp.htm", "work_at_height"),
    ("hse_015", "Safety nets and soft landing systems", "https://www.hse.gov.uk/construction/safetytopics/safety-nets.htm", "work_at_height"),
    ("hse_016", "Steel erection", "https://www.hse.gov.uk/construction/safetytopics/steel-erection.htm", "structural_work"),
    ("hse_017", "Structural stability during alteration demolition and dismantling", "https://www.hse.gov.uk/construction/safetytopics/buildings.htm", "structural_work"),
    ("hse_018", "Catastrophic events in construction", "https://www.hse.gov.uk/construction/pdf/m3-annex-5.pdf", "structural_work"),
    ("hse_019", "Electricity systems in buildings", "https://www.hse.gov.uk/construction/safetytopics/systems.htm", "electrical_safety"),
    ("hse_020", "Electricity overhead power lines", "https://www.hse.gov.uk/construction/safetytopics/overhead.htm", "electrical_safety"),
    ("hse_021", "Electricity underground cables", "https://www.hse.gov.uk/construction/safetytopics/underground.htm", "electrical_safety"),
    ("hse_022", "General fire safety", "https://www.hse.gov.uk/construction/safetytopics/generalfire.htm", "fire_safety"),
    ("hse_023", "Process fire risks", "https://www.hse.gov.uk/construction/safetytopics/processfire.htm", "fire_safety"),
    ("hse_024", "Excavators", "https://www.hse.gov.uk/construction/safetytopics/excavators.htm", "plant_equipment"),
    ("hse_025", "Telescopic handlers", "https://www.hse.gov.uk/construction/safetytopics/telescopic.htm", "plant_equipment"),
    ("hse_026", "Dumpers", "https://www.hse.gov.uk/construction/safetytopics/dumpers.htm", "plant_equipment"),
    ("hse_027", "Slips and trips", "https://www.hse.gov.uk/construction/safetytopics/falls.htm", "site_hazards"),
    ("hse_028", "Excavations", "https://www.hse.gov.uk/construction/safetytopics/excavations.htm", "groundworks"),
    ("hse_029", "Lifting operations", "https://www.hse.gov.uk/construction/safetytopics/lifting-operations.htm", "lifting_operations"),
    ("hse_030", "Demolition", "https://www.hse.gov.uk/construction/safetytopics/demolition.htm", "demolition"),
    ("hse_031", "Prevention of drowning", "https://www.hse.gov.uk/construction/safetytopics/prevention-of-drowning.htm", "water_safety"),
    ("hse_032", "Temporary works", "https://www.hse.gov.uk/construction/safetytopics/temporary-works.htm", "temporary_works"),
    ("hse_033", "Construction health risks key points", "https://www.hse.gov.uk/construction/healthrisks/key-points.htm", "health_risks"),
    ("hse_034", "Construction dust", "https://www.hse.gov.uk/construction/healthrisks/hazardous-substances/construction-dust.htm", "hazardous_substances"),
    ("hse_035", "Cement", "https://www.hse.gov.uk/construction/healthrisks/hazardous-substances/cement.htm", "hazardous_substances"),
    ("hse_036", "Asbestos", "https://www.hse.gov.uk/construction/healthrisks/cancer-and-construction/asbestos.htm", "hazardous_substances"),
    ("hse_037", "Silica dust", "https://www.hse.gov.uk/construction/healthrisks/cancer-and-construction/silica-dust.htm", "hazardous_substances"),
    ("hse_038", "Noise", "https://www.hse.gov.uk/construction/healthrisks/physical-ill-health-risks/noise.htm", "physical_health"),
    ("hse_039", "Vibration", "https://www.hse.gov.uk/construction/healthrisks/physical-ill-health-risks/vibration.htm", "physical_health"),
    ("hse_040", "Manual handling", "https://www.hse.gov.uk/construction/healthrisks/physical-ill-health-risks/manual-handling.htm", "physical_health"),
]

NOISE_IDS = ["contentAside", "feedback", "sidebarAside"]
NOISE_CLASSES = ["hse-feedback", "hse-back-to-top", "hse-sidebar", "hse-sidebar-top"]


def clean_html_page(html_bytes: bytes) -> str | None:
    soup = BeautifulSoup(html_bytes, "html.parser")
    h1 = soup.find("h1")
    title_text = h1.get_text(strip=True) if h1 else ""

    content = soup.find(id="page-contents")
    if content is None:
        return None

    for node_id in NOISE_IDS:
        node = content.find(id=node_id)
        if node is not None:
            node.decompose()
    for cls in NOISE_CLASSES:
        for node in content.find_all(class_=cls):
            node.decompose()

    converter = html2text.HTML2Text()
    converter.body_width = 0
    converter.ignore_links = True
    converter.ignore_images = True
    body_md = converter.handle(str(content)).strip()

    if not body_md:
        return None

    parts = []
    if title_text:
        parts.append(f"# {title_text}\n")
    parts.append(body_md)
    return "\n".join(parts).strip() + "\n"


def extract_pdf_text(pdf_bytes: bytes) -> str | None:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if len(text) >= 200:
            return text
    except Exception:
        pass

    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = "\n\n".join(page.extract_text() or "" for page in pdf.pages).strip()
        if len(text) >= 200:
            return text
    except Exception:
        pass

    return None


def frontmatter(doc_id: str, title: str, url: str, category: str) -> str:
    escaped_title = title.replace('"', '\\"')
    return (
        "---\n"
        f"doc_id: {doc_id}\n"
        f'title: "{escaped_title}"\n'
        f'source_url: "{url}"\n'
        f'source_org: "{SOURCE_ORG}"\n'
        f'licence: "{LICENCE}"\n'
        f"retrieved_at: \"{RETRIEVED_AT}\"\n"
        f"category: {category}\n"
        "---\n\n"
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    accepted = []
    rejected = []

    for doc_id, title, url, category in SOURCES:
        print(f"{doc_id}  {url}")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
        except requests.RequestException as exc:
            rejected.append((doc_id, title, url, f"request failed: {exc}"))
            print(f"  REJECTED: request failed: {exc}")
            continue

        if resp.status_code != 200:
            rejected.append((doc_id, title, url, f"HTTP {resp.status_code}"))
            print(f"  REJECTED: HTTP {resp.status_code}")
            continue

        if url.lower().endswith(".pdf"):
            body_text = extract_pdf_text(resp.content)
            if body_text is None:
                rejected.append((doc_id, title, url, "PDF text extraction failed (pypdf and pdfplumber)"))
                print("  REJECTED: PDF extraction failed")
                continue
            markdown = frontmatter(doc_id, title, url, category) + f"# {title}\n\n" + body_text.strip() + "\n"
        else:
            body_md = clean_html_page(resp.content)
            if body_md is None:
                rejected.append((doc_id, title, url, "could not locate/clean main content"))
                print("  REJECTED: could not locate main content")
                continue
            markdown = frontmatter(doc_id, title, url, category) + body_md

        out_path = OUT_DIR / f"{doc_id}.md"
        out_path.write_text(markdown, encoding="utf-8")
        accepted.append((doc_id, title, url, category))
        print(f"  OK -> {out_path.relative_to(PROJECT_ROOT)} ({len(markdown)} chars)")

    if accepted:
        with open(SOURCES_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for doc_id, title, url, category in accepted:
                writer.writerow([
                    doc_id, f"raw_sources/hse/{doc_id}.md", title,
                    "", "OGL v3.0", url, SOURCE_ORG, RETRIEVED_AT, category,
                ])

    with open(REJECTED_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["doc_id", "title", "source_url", "reason"])
        writer.writerows(rejected)

    print(f"\nAccepted: {len(accepted)}/{len(SOURCES)}  Rejected: {len(rejected)}")
    print(f"Sources appended to {SOURCES_CSV}")
    print(f"Rejections logged to {REJECTED_CSV}")


if __name__ == "__main__":
    main()
