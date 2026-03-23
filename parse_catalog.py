#!/usr/bin/env python3
"""
Parse NS-Opferlager catalog XHTML into a structured CSV table.

Columns:
  Bundesland | Politische Gemeinde | Lagerbezeichnung |
  Lagerinsassen und Geschichte | Lokalisierung (Adresse + KG) |
  Grundstücksnummern | Koordinaten (WGS84/Dezimal) |
  Literatur und Quellenangaben
"""

import csv
import re
import sys
from html.parser import HTMLParser

INPUT_FILE = "Katalog NS-Opferorte_Stand Jänner 2022_BF.xml"
OUTPUT_FILE = "Katalog NS-Opferorte.csv"

# ---------------------------------------------------------------------------
# 1. HTML / XHTML paragraph extractor
# ---------------------------------------------------------------------------

class ParagraphExtractor(HTMLParser):
    """Extract text from <p> elements, skipping annotation divs."""

    def __init__(self):
        super().__init__()
        self.paragraphs: list[str] = []
        self._buf: str | None = None
        self._in_p = False
        self._anno_depth = 0

    def handle_starttag(self, tag, attrs):
        ad = dict(attrs)
        if tag == "div" and ad.get("class") == "annotation":
            self._anno_depth += 1
        elif tag == "p" and self._anno_depth == 0:
            self._in_p = True
            self._buf = ""

    def handle_endtag(self, tag):
        if tag == "p" and self._in_p:
            self._in_p = False
            if self._buf is not None:
                t = self._buf.strip()
                if t:
                    self.paragraphs.append(t)
            self._buf = None
        elif tag == "div" and self._anno_depth > 0:
            self._anno_depth -= 1

    def handle_data(self, data):
        if self._in_p and self._buf is not None and self._anno_depth == 0:
            self._buf += data

    def handle_entityref(self, name):
        if self._in_p and self._buf is not None and self._anno_depth == 0:
            ch = {"amp": "&", "lt": "<", "gt": ">",
                  "quot": '"', "apos": "'"}.get(name, f"&{name};")
            self._buf += ch

    def handle_charref(self, name):
        if self._in_p and self._buf is not None and self._anno_depth == 0:
            try:
                if name.startswith("x"):
                    ch = chr(int(name[1:], 16))
                else:
                    ch = chr(int(name))
                self._buf += ch
            except (ValueError, OverflowError):
                self._buf += f"&#{name};"


# ---------------------------------------------------------------------------
# 2. Constants & compiled patterns
# ---------------------------------------------------------------------------

BUNDESLAENDER = {
    "Burgenland", "Kärnten", "Niederösterreich", "Oberösterreich",
    "Salzburg", "Steiermark", "Tirol", "Vorarlberg", "Wien",
}

PAGE_HEADER_RE = re.compile(r"^Seite[\s\ufffd\xa0]*\d+$")
CATALOG_HEADER = "Katalog der NS-Opferlager in Österreich"

# Coordinate pair — lon (≈9‑17) , lat (≈46‑49) with comma or dot decimal sep
COORD_RE = re.compile(
    r"(\d{1,2}[,\.]\d{2,8})\s*[,;]\s*(\d{1,2}[,\.]\d{2,8})"
)

# KG with number:  "KG Name, 12345"
KG_NUM_RE = re.compile(r"KG\s+([^,]+?)\s*,\s*(\d{4,6})")
# KG without number (fallback):  "KG Name."
KG_BARE_RE = re.compile(r"KG\s+([A-ZÄÖÜ][^.]{2,80}?)\.")

# Standard entry start: "Gemeinde. Lagerbezeichnung. ..."
ENTRY_STD_RE = re.compile(
    r"^([A-ZÄÖÜ][a-zA-ZäöüÄÖÜß \(\)\-/]+?)\.\s+"  # Gemeinde
    r"([A-ZÄÖÜ„\(\"][^\n.]*?)\.\s+",                 # Lagerbezeichnung
)

# Wien entry start: "N. Bezirk. Wien … . …"
ENTRY_WIEN_RE = re.compile(
    r"^(\d{1,2}\.\s*Bezirk)\.\s+"
    r"((?:Wien|Inha\s*Wien)\s+[^\n.]*?)\.\s+",
)

# Camp-related keywords expected in a genuine Lagerbezeichnung
_CAMP_KW = re.compile(
    r"(?i)lager|KZ|STALAG|DULAG|OFLAG|Arbeitsstätte|Euthanasie|Ziegelei|"
    r"Panzergraben|Fabrik|Arrest|Heim|Kriegsgefangen|Zwangsarbeit|"
    r"Internierung|Sammellager|Umsiedler|Flüchtling|BBU|Braunkohle|"
    r"Firma|Kompanie|Akkumulatoren|Porsche|Mutter-Kind|Arbeitsmaid|"
    r"Schlössl|Judenlager|Sinti|Roma"
)

# Words that never appear in genuine Austrian Gemeinde names — if the
# candidate "Gemeinde" field contains any of these, the paragraph is a
# continuation, not a new entry.
_BAD_GEMEINDE = re.compile(
    r"\b(?:"
    # function words / prepositions / conjunctions not found in place names
    r"mit|für|von|aus|über|beim|zur|sowie|aber|jedoch|davon|darunter|damals|"
    r"zwischen|heute|ehemals?|rezent|nördlich|südlich|östlich|westlich|"
    # verbs
    r"werden|wurde|wurden|waren|wird|sind|haben|hatte|ist|"
    # description / camp-related nouns unlikely as place name components
    r"Zwangsarbeiter|Kriegsgefangene|Häftlinge?|Arbeiter(?:innen)?|"
    r"Unterbringung|Evakuierung|Erschießung|Massaker|Einsatz|"
    r"Baracke[n]?|Relikte|Gebäude|Gelände|Bereich|Krematorium|"
    r"Verladen|Kinder|Sägewerk|Strickwaren|Seidenband|Textilfabrik|"
    r"Flugzeugwerk[e]?|Teil(?:stück)?|Kommando"
    r")\b", re.IGNORECASE
)

# Lagerbezeichnung should NOT start with "KG " (that is a KG reference,
# not a camp name — means we split mid-entry)
_BAD_LAGER_START = re.compile(
    r"^(?:KG\s|Rezent|Genaue Lage|Lage unklar|Nördlich|Südlich|Östlich|"
    r"Westlich|Textilfabrik|Am Fabrik)"
)


# ---------------------------------------------------------------------------
# 3. Helper functions
# ---------------------------------------------------------------------------

def is_page_header(text: str) -> bool:
    return bool(PAGE_HEADER_RE.match(text)) or text.strip() == CATALOG_HEADER


def is_bundesland_header(text: str) -> bool:
    return text.strip() in BUNDESLAENDER


def is_entry_start(text: str, bundesland: str) -> bool:
    """Decide whether *text* begins a new catalog entry."""
    # Wien pattern
    if ENTRY_WIEN_RE.match(text):
        return True
    # Standard pattern
    m = ENTRY_STD_RE.match(text)
    if not m:
        return False
    gemeinde = m.group(1).strip()
    lager = m.group(2).strip()
    # Reject if Lagerbezeichnung is suspiciously long AND lacks camp keywords
    if len(lager) > 60 and not _CAMP_KW.search(lager):
        return False
    # Reject if "Gemeinde" contains words impossible in a place name
    if _BAD_GEMEINDE.search(gemeinde):
        return False
    # Reject if Lagerbezeichnung starts with a KG ref or location note
    if _BAD_LAGER_START.match(lager):
        return False
    # Reject preposition-started "Gemeinde" (likely continuation)
    if re.match(
        r"^(?:Im|Am|Bei|Auf|An|In|Unter|Über|Vor|Hinter|Zwischen|Aus|Durch|Nach|Seit|Auch|Sowie|Weitere)\s",
        gemeinde,
    ):
        return False
    return True


def join_paragraphs(paras: list[str]) -> str:
    """Join consecutive paragraphs, re-joining hyphenated words."""
    if not paras:
        return ""
    result = paras[0]
    for p in paras[1:]:
        if result.endswith("-") and p and p[0].islower():
            result = result[:-1] + p          # dehyphenate
        else:
            result = result + " " + p
    # collapse multiple spaces
    result = re.sub(r"  +", " ", result)
    return result.strip()


def find_austrian_coords(text: str):
    """Return the first COORD_RE match whose values lie within Austria."""
    for m in COORD_RE.finditer(text):
        try:
            lon = float(m.group(1).replace(",", "."))
            lat = float(m.group(2).replace(",", "."))
        except ValueError:
            continue
        if 9 <= lon <= 18 and 46 <= lat <= 50:
            return m
    return None


def split_address_grundstuecke(text: str):
    """
    Given the text between KG and coordinates, separate address from
    Grundstücksnummern.

    Heuristic: the first '. ' that precedes a digit or dot-digit marks the
    boundary between address and property numbers.
    """
    text = text.strip().rstrip(".")
    if not text:
        return "", ""

    # Find the split point: ". " followed by a digit or .digit
    sp = re.search(r"\.\s+([\d\.])", text)
    if sp:
        address = text[: sp.start()].strip().rstrip(".")
        grund = text[sp.start() + 2 :].strip().rstrip(".")
        return address, grund

    # No split point found — classify the whole chunk
    if text[0].isdigit() or (text[0] == "." and len(text) > 1 and text[1].isdigit()):
        return "", text.rstrip(".")      # all Grundstücke
    else:
        return text.rstrip("."), ""       # all address


def guess_literatur_split(text: str):
    """
    For entries *without* KG or coordinates, try to separate the Geschichte
    part from trailing Literature references.

    Literature refs typically look like:
      Author Year   |   Author u. a. Year   |   http(s)://…   |   Verzeichnis 1979
    """
    text = text.strip().rstrip(".")
    if not text:
        return "", ""

    # A literature reference token (author year, URL, institution, …)
    _LIT_TOKEN = (
        r"(?:[A-ZÄÖÜ][a-zäöüß]+(?:\s+u\.\s*a\.)?\s+\d{4})"   # Author Year
        r"|(?:https?://)"                                         # URL
        r"|(?:Verzeichnis\s+\d{4})"                              # Verzeichnis
        r"|(?:Eintrag\s+in\s+)"                                  # Eintrag in …
        r"|(?:Ludwig\s+Boltzmann)"                                # LBI
        r"|(?:Wiener\s+Stadt-\s*und\s+Landesarchiv)"             # WSTLA
        r"|(?:Bundesdenkmalamt)"                                  # BDA
        r"|(?:Informanten)"                                       # Informanten
    )
    # Anchored after: start of string, ". ", or "; "
    lit_re = re.compile(
        r"(?:^|[.;]\s+)" r"(" + _LIT_TOKEN + r")"
    )
    # Find the FIRST literature-like token (we split there)
    m = lit_re.search(text)
    if m:
        pos = m.start()
        # Step back past the ". " / "; " separator if present
        if pos >= 2 and text[pos] in ".;":
            geschichte = text[:pos].strip().rstrip(".")
            literatur = text[pos + 1 :].strip().lstrip().rstrip(".")
        elif pos == 0:
            geschichte = ""
            literatur = text.rstrip(".")
        else:
            geschichte = text[:pos].strip().rstrip(". ")
            literatur = text[pos:].strip().rstrip(".")
        return geschichte, literatur

    # No literature pattern found — everything is Geschichte
    return text.rstrip("."), ""


# ---------------------------------------------------------------------------
# 4. Entry parser
# ---------------------------------------------------------------------------

def parse_entry(full_text: str, bundesland: str) -> dict:
    """Parse a single catalog entry into structured fields."""

    entry = {
        "Bundesland": bundesland,
        "Politische Gemeinde": "",
        "Lagerbezeichnung": "",
        "Lagerinsassen und Geschichte": "",
        "Lokalisierung": "",
        "Grundstücksnummern": "",
        "Koordinaten": "",
        "Literatur und Quellenangaben": "",
    }

    # ---- Extract Gemeinde & Lagerbezeichnung ----
    m_wien = ENTRY_WIEN_RE.match(full_text)
    m_std = ENTRY_STD_RE.match(full_text)

    if m_wien:
        entry["Politische Gemeinde"] = m_wien.group(1).strip()
        entry["Lagerbezeichnung"] = m_wien.group(2).strip()
        rest = full_text[m_wien.end():]
    elif m_std:
        entry["Politische Gemeinde"] = m_std.group(1).strip()
        entry["Lagerbezeichnung"] = m_std.group(2).strip()
        rest = full_text[m_std.end():]
    else:
        # Fallback: split on first two periods
        parts = full_text.split(". ", 2)
        entry["Politische Gemeinde"] = parts[0].strip()
        if len(parts) > 1:
            entry["Lagerbezeichnung"] = parts[1].strip().rstrip(".")
        rest = parts[2] if len(parts) > 2 else ""

    rest = rest.strip()

    # ---- Find KG ----
    kg_match = KG_NUM_RE.search(rest)
    kg_bare = KG_BARE_RE.search(rest) if not kg_match else None

    if kg_match:
        kg_name = kg_match.group(1).strip()
        kg_num = kg_match.group(2).strip()
        kg_label = f"KG {kg_name}, {kg_num}"

        geschichte = rest[: kg_match.start()].strip().rstrip(". ")
        after_kg = rest[kg_match.end():].strip().lstrip(".?! ").strip()

        # Find coordinates after KG
        coord = find_austrian_coords(after_kg)
        if coord:
            before_c = after_kg[: coord.start()].strip().rstrip(",. ")
            entry["Koordinaten"] = f"{coord.group(1)}, {coord.group(2)}"
            after_c = after_kg[coord.end():].strip().lstrip(". ").strip()
            entry["Literatur und Quellenangaben"] = after_c.rstrip(".")

            addr, grund = split_address_grundstuecke(before_c)
            entry["Lokalisierung"] = kg_label
            if addr:
                entry["Lokalisierung"] += f". {addr}"
            entry["Grundstücksnummern"] = grund
        else:
            # No coordinates — try to separate addr/grund/literature from after_kg
            # Look for literature at end
            addr_grund, lit = guess_literatur_split(after_kg)
            addr, grund = split_address_grundstuecke(addr_grund)
            entry["Lokalisierung"] = kg_label
            if addr:
                entry["Lokalisierung"] += f". {addr}"
            entry["Grundstücksnummern"] = grund
            entry["Literatur und Quellenangaben"] = lit.rstrip(".")

        entry["Lagerinsassen und Geschichte"] = geschichte

    elif kg_bare:
        kg_name = kg_bare.group(1).strip()
        kg_label = f"KG {kg_name}"

        geschichte = rest[: kg_bare.start()].strip().rstrip(". ")
        after_kg = rest[kg_bare.end():].strip().lstrip(".?! ").strip()

        coord = find_austrian_coords(after_kg)
        if coord:
            before_c = after_kg[: coord.start()].strip().rstrip(",. ")
            entry["Koordinaten"] = f"{coord.group(1)}, {coord.group(2)}"
            after_c = after_kg[coord.end():].strip().lstrip(". ").strip()
            entry["Literatur und Quellenangaben"] = after_c.rstrip(".")
            addr, grund = split_address_grundstuecke(before_c)
            entry["Lokalisierung"] = kg_label
            if addr:
                entry["Lokalisierung"] += f". {addr}"
            entry["Grundstücksnummern"] = grund
        else:
            entry["Lokalisierung"] = kg_label
            _, lit = guess_literatur_split(after_kg)
            entry["Literatur und Quellenangaben"] = lit.rstrip(".")

        entry["Lagerinsassen und Geschichte"] = geschichte

    else:
        # No KG at all
        coord = find_austrian_coords(rest)
        if coord:
            geschichte = rest[: coord.start()].strip().rstrip(",. ")
            entry["Koordinaten"] = f"{coord.group(1)}, {coord.group(2)}"
            after_c = rest[coord.end():].strip().lstrip(". ").strip()
            entry["Literatur und Quellenangaben"] = after_c.rstrip(".")
            entry["Lagerinsassen und Geschichte"] = geschichte
        else:
            # No KG, no coordinates — split Geschichte / Literatur heuristically
            geschichte, lit = guess_literatur_split(rest)
            entry["Lagerinsassen und Geschichte"] = geschichte
            entry["Literatur und Quellenangaben"] = lit

    # ---- Final cleanup ----
    for key in entry:
        v = entry[key]
        # Strip stray leading/trailing punctuation & whitespace
        v = re.sub(r"^[.;,\s]+", "", v)
        v = re.sub(r"[.;,\s]+$", "", v)
        entry[key] = v.strip()

    return entry


# ---------------------------------------------------------------------------
# 5. Main
# ---------------------------------------------------------------------------

def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as fh:
        html = fh.read()

    extractor = ParagraphExtractor()
    extractor.feed(html)
    paragraphs = extractor.paragraphs

    # Walk paragraphs, grouping into entries per Bundesland
    entries_raw: list[tuple[str, list[str]]] = []
    current_bl: str | None = None
    current_paras: list[str] = []
    catalog_started = False

    for para in paragraphs:
        para = para.replace("\xa0", " ").replace("\ufffd", " ").strip()
        if not para:
            continue

        if is_page_header(para):
            continue

        if is_bundesland_header(para):
            if current_paras and current_bl:
                entries_raw.append((current_bl, current_paras))
                current_paras = []
            current_bl = para.strip()
            catalog_started = True
            continue

        if para.strip() == "Literatur":
            # End of catalog entries; bibliography follows
            break

        if not catalog_started:
            continue

        if is_entry_start(para, current_bl):
            if current_paras:
                entries_raw.append((current_bl, current_paras))
            current_paras = [para]
        else:
            current_paras.append(para)

    # flush last entry
    if current_paras and current_bl:
        entries_raw.append((current_bl, current_paras))

    # Parse every raw entry
    entries = []
    for bl, paras in entries_raw:
        text = join_paragraphs(paras)
        entries.append(parse_entry(text, bl))

    # Write CSV (semicolon-separated for easier handling with commas in data)
    fieldnames = [
        "Bundesland",
        "Politische Gemeinde",
        "Lagerbezeichnung",
        "Lagerinsassen und Geschichte",
        "Lokalisierung",
        "Grundstücksnummern",
        "Koordinaten",
        "Literatur und Quellenangaben",
    ]

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=fieldnames, delimiter=";", quoting=csv.QUOTE_ALL
        )
        writer.writeheader()
        for e in entries:
            writer.writerow(e)

    print(f"Fertig: {len(entries)} Einträge → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
