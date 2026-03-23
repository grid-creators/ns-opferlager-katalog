# Katalog der NS-Opferlager in Österreich

Searchable web application and structured dataset based on the **Katalog der NS-Opferlager in Österreich** (Stand: 31. Jänner 2022), published by the Austrian Federal Monuments Authority (Bundesdenkmalamt).

## Data Source

The original catalog is available as PDF from the Bundesdenkmalamt:

**[Katalog NS-Opferorte (PDF)](https://www.bda.gv.at/dam/jcr:f9cf741d-120d-493b-9693-e3e5043f1b99/Katalog%20NS-Opferorte_Stand%20J%C3%A4nner%202022_BF.pdf)**

The catalog documents Nazi-era camps, forced labor sites, and other sites of persecution across all nine Austrian federal states (Bundesländer). Entries are organized alphabetically by state and municipality.

## What This Project Does

1. **PDF to XHTML conversion** using [Apache Tika](https://tika.apache.org/)
2. **Structured parsing** of the continuous text into a semicolon-delimited CSV with the following columns:
   - Bundesland
   - Politische Gemeinde
   - Lagerbezeichnung
   - Lagerinsassen und Geschichte
   - Lokalisierung (Adresse + Katastralgemeinde mit KG-Nummer)
   - Grundstücksnummern
   - Koordinaten (WGS84/Dezimal)
   - Literatur und Quellenangaben
3. **Interactive web application** with map view and full-text search

## Dataset

| | |
|---|---|
| Total entries | 2,069 |
| Entries with coordinates | 1,262 (61%) |
| Entries with KG reference | 1,922 (93%) |
| Bundesländer | 9 |

## Web Application

Open `index.html` in a browser (requires `data.json` in the same directory).

**Features:**
- **Map view** — OpenStreetMap with markers color-coded by Bundesland, clustered at low zoom levels
- **Table view** — sortable by any column
- **Full-text search** — across Gemeinde, Lagerbezeichnung, Geschichte, Lokalisierung, and Literatur (multiple words are combined with AND)
- **Bundesland filter**
- **Detail panel** — click a map marker to view the full entry

## Files

| File | Description |
|---|---|
| `index.html` | Web application (map + table) |
| `data.json` | Parsed catalog data as JSON |
| `Katalog NS-Opferorte.csv` | Parsed catalog data as CSV (semicolon-delimited, UTF-8 with BOM) |
| `parse_catalog.py` | Python script that parses the Tika XHTML output into CSV/JSON |

## How to Reproduce

```bash
# 1. Download the PDF
curl -L -o catalog.pdf "https://www.bda.gv.at/dam/jcr:f9cf741d-120d-493b-9693-e3e5043f1b99/Katalog%20NS-Opferorte_Stand%20J%C3%A4nner%202022_BF.pdf"

# 2. Convert PDF to XHTML with Apache Tika (requires Java)
java -jar tika-app-3.3.0.jar --xml catalog.pdf > catalog.xml 2>/dev/null

# 3. Parse into CSV
python3 parse_catalog.py
```

## License

The original data is published by the [Bundesdenkmalamt](https://www.bda.gv.at/) (Austrian Federal Monuments Authority).
