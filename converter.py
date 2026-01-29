import csv
import io
import xml.etree.ElementTree as ET


def localname(tag: str) -> str:
    if tag and tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def get_value(elem: ET.Element) -> str:
    v = elem.get("V")
    if v is not None:
        return v
    return (elem.text or "").strip()


def parse_header_bytes(xml_bytes: bytes) -> dict:
    header = {"Exercice": "", "Siret": "", "Nom": ""}

    f = io.BytesIO(xml_bytes)
    for _, elem in ET.iterparse(f, events=("end",)):
        tag = localname(elem.tag)

        if tag == "Exercice":
            header["Exercice"] = get_value(elem)

        elif tag == "Collectivite":
            header["Siret"] = elem.get("Siret") or elem.get("SIRET") or header["Siret"]
            header["Nom"] = elem.get("Libelle") or header["Nom"]

        if all(header.values()):
            break

        elem.clear()

    return header


def iter_lignebudget_bytes(xml_bytes: bytes):
    f = io.BytesIO(xml_bytes)
    for _, elem in ET.iterparse(f, events=("end",)):
        if localname(elem.tag) != "LigneBudget":
            continue

        row = {"LigneBudget_id": elem.get("id", "")}

        for child in list(elem):
            name = localname(child.tag)

            if name in ("MtSup", "CaracSup"):
                code = (child.get("Code", "") or "").strip()
                col = f"{name}_{code}" if code else name
                row[col] = get_value(child)
            else:
                row[name] = get_value(child)

        elem.clear()
        yield row


def map_to_scdl(raw: dict, header: dict) -> dict:
    codrd = (raw.get("CodRD", "") or "").upper()
    artspe = (raw.get("ArtSpe", "") or "").lower()
    opbudg = raw.get("OpBudg", "")

    return {
        "BGT_ID": raw.get("LigneBudget_id", ""),

        "BGT_NATDEC": "compte administratif",
        "BGT_ANNEE": header.get("Exercice", ""),
        "BGT_SIRET": header.get("Siret", ""),
        "BGT_NOM": header.get("Nom", ""),

        "BGT_CONTNAT": "",
        "BGT_CONTNAT_LABEL": "",
        "BGT_NATURE": raw.get("Nature", ""),
        "BGT_NATURE_LABEL": "",
        "BGT_FONCTION": raw.get("Fonction", ""),
        "BGT_FONCTION_LABEL": "",
        "BGT_OPERATION": "",
        "BGT_SECTION": "",

        "BGT_OPBUDG": "ordre" if opbudg == "1" else "réel",
        "BGT_CODRD": "dépense" if codrd == "D" else ("recette" if codrd == "R" else ""),
        "BGT_ARTSPE": "spécialisé" if artspe == "true" else ("non spécialisé" if artspe == "false" else ""),

        "BGT_MTREAL": raw.get("MtReal", ""),
        "BGT_MTBUDGPREC": raw.get("MtBudgPrec", ""),
        "BGT_MTRARPREC": raw.get("MtRARPrec", ""),
        "BGT_MTPROPNOUV": raw.get("MtPropNouv", ""),
        "BGT_MTPREV": raw.get("MtPrev", ""),
        "BGT_CREDOUV": raw.get("CredOuv", ""),
        "BGT_MTRAR3112": raw.get("MtRAR3112", ""),
    }


def _write_csv_string(rows, fields, sep: str) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields, delimiter=sep, quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k, "") for k in fields})
    return out.getvalue()


def convert_cfu_bytes(xml_bytes: bytes, csv_separator: str = ","):
    header = parse_header_bytes(xml_bytes)

    raw_rows = []
    raw_fields = set()

    for row in iter_lignebudget_bytes(xml_bytes):
        raw_rows.append(row)
        raw_fields.update(row.keys())

    raw_fields = sorted(raw_fields)

    raw_csv = _write_csv_string(raw_rows, raw_fields, csv_separator)

    scdl_fields = [
        "BGT_ID",
        "BGT_NATDEC","BGT_ANNEE","BGT_SIRET","BGT_NOM",
        "BGT_CONTNAT","BGT_CONTNAT_LABEL",
        "BGT_NATURE","BGT_NATURE_LABEL",
        "BGT_FONCTION","BGT_FONCTION_LABEL",
        "BGT_OPERATION","BGT_SECTION",
        "BGT_OPBUDG","BGT_CODRD","BGT_ARTSPE",
        "BGT_MTREAL","BGT_MTBUDGPREC","BGT_MTRARPREC",
        "BGT_MTPROPNOUV","BGT_MTPREV","BGT_CREDOUV","BGT_MTRAR3112"
    ]

    scdl_rows = [map_to_scdl(r, header) for r in raw_rows]
    scdl_csv = _write_csv_string(scdl_rows, scdl_fields, csv_separator)

    stats = {
        "exercice": header.get("Exercice", ""),
        "siret": header.get("Siret", ""),
        "nom": header.get("Nom", ""),
        "lignes": len(raw_rows),
        "raw_cols": len(raw_fields),
    }

    return raw_csv, scdl_csv, stats

