import csv
import io
import re
import xml.etree.ElementTree as ET


def localname(tag: str) -> str:
    if tag and tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def get_value(elem: ET.Element) -> str:
    v = elem.get("V")
    if v is not None:
        return str(v).strip()
    return (elem.text or "").strip()


def format_decimal_fr(value) -> str:
    """
    Convertit un nombre au format français avec virgule décimale.
    Exemples :
    '123.45' -> '123,45'
    123.45   -> '123,45'
    ''       -> ''
    None     -> ''
    """
    if value is None:
        return ""

    s = str(value).strip()
    if s == "":
        return ""

    try:
        f = float(s.replace(",", "."))
        return str(f).replace(".", ",")
    except Exception:
        return s


def parse_header_bytes(xml_bytes: bytes) -> dict:
    header = {"Exercice": "", "Siret": "", "Nom": ""}

    f = io.BytesIO(xml_bytes)
    for _, elem in ET.iterparse(f, events=("end",)):
        tag = localname(elem.tag)

        if tag == "Exercice":
            header["Exercice"] = get_value(elem)

        elif tag == "Collectivite":
            header["Siret"] = (
                elem.get("Siret")
                or elem.get("SIRET")
                or header["Siret"]
            )
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

        row = {"LigneBudget_id": (elem.get("id", "") or "").strip()}

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


def normalize_nature_code(value) -> str:
    """
    Nettoie la nature pour récupérer un code exploitable,
    en conservant les zéros à gauche pour les cas métier.
    Exemples :
    '24'     -> '24'
    '24.0'   -> '24'
    ' 2 '    -> '2'
    '2324A'  -> '2324'
    'NAT 24' -> '24'
    '001'    -> '001'
    '002'    -> '002'
    '024'    -> '024'
    """
    if value is None:
        return ""

    s = str(value).strip()
    if not s:
        return ""

    m_decimal = re.fullmatch(r"(\d+)\.0+", s)
    if m_decimal:
        return m_decimal.group(1)

    m_digits = re.search(r"\d+", s)
    if m_digits:
        return m_digits.group(0)

    return ""


def normalize_nature_for_section(value) -> str:
    """
    Prépare la nature pour la règle générale
    en supprimant les zéros à gauche.
    Exemples :
    '001' -> '1'
    '002' -> '2'
    '024' -> '24'
    '000' -> ''
    """
    nature = normalize_nature_code(value)
    if not nature:
        return ""
    return nature.lstrip("0")


def get_nature_first_digit(value) -> str:
    """
    Retourne le premier chiffre significatif
    pour la règle générale de section.
    """
    nature = normalize_nature_for_section(value)
    if not nature:
        return ""
    return nature[0]


def get_section_from_nature(nature_value) -> str:
    """
    Déduit la section à partir de la nature.

    Cas métier prioritaires :
    - 001 => investissement
    - 002 => fonctionnement
    - 024 => investissement

    Puis règle générale :
    - 1,2,3 => investissement
    - 6,7   => fonctionnement
    """
    nature_clean = normalize_nature_code(nature_value)

    # Cas métier prioritaires
    if nature_clean == "001":
        return "investissement"

    if nature_clean == "002":
        return "fonctionnement"

    if nature_clean == "024":
        return "investissement"

    # Règle générale
    first_digit = get_nature_first_digit(nature_value)

    if first_digit in {"1", "2", "3"}:
        return "investissement"

    if first_digit in {"6", "7"}:
        return "fonctionnement"

    return ""


def map_to_scdl(raw: dict, header: dict, decimal_comma: bool = True) -> dict:
    codrd = (raw.get("CodRD", "") or "").upper().strip()
    artspe = (raw.get("ArtSpe", "") or "").lower().strip()
    opbudg = (raw.get("OpBudg", "") or "").strip()

    nature_raw = raw.get("Nature", "")
    nature_clean = normalize_nature_code(nature_raw)
    nature_first_digit = get_nature_first_digit(nature_raw)

    def fmt_num(v):
        return format_decimal_fr(v) if decimal_comma else ("" if v is None else str(v).strip())

    return {
        "BGT_ID": raw.get("LigneBudget_id", ""),

        "BGT_NATDEC": "compte financier unique",
        "BGT_ANNEE": header.get("Exercice", ""),
        "BGT_SIRET": header.get("Siret", ""),
        "BGT_NOM": header.get("Nom", ""),

        "BGT_CONTNAT": "",
        "BGT_CONTNAT_LABEL": "",
        "BGT_NATURE": nature_clean,
        "BGT_NATURE_LABEL": "",
        "BGT_FONCTION": raw.get("Fonction", ""),
        "BGT_FONCTION_LABEL": "",
        "BGT_OPERATION": "",
        "BGT_SECTION": get_section_from_nature(nature_raw),

        "BGT_OPBUDG": "ordre" if opbudg == "1" else "réel",
        "BGT_CODRD": "dépense" if codrd == "D" else ("recette" if codrd == "R" else ""),
        "BGT_ARTSPE": "spécialisé" if artspe == "true" else ("non spécialisé" if artspe == "false" else ""),

        "BGT_MTREAL": fmt_num(raw.get("MtReal", "")),
        "BGT_MTBUDGPREC": fmt_num(raw.get("MtBudgPrec", "")),
        "BGT_MTRARPREC": fmt_num(raw.get("MtRARPrec", "")),
        "BGT_MTPROPNOUV": fmt_num(raw.get("MtPropNouv", "")),
        "BGT_MTPREV": fmt_num(raw.get("MtPrev", "")),
        "BGT_CREDOUV": fmt_num(raw.get("CredOuv", "")),
        "BGT_MTRAR3112": fmt_num(raw.get("MtRAR3112", "")),

        # Colonnes de contrôle utiles
        "BGT_NATURE_RAW": nature_raw,
        "BGT_NATURE_FIRST_DIGIT": nature_first_digit,
    }


def _write_csv_string(rows, fields, sep: str) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(
        out,
        fieldnames=fields,
        delimiter=sep,
        quoting=csv.QUOTE_MINIMAL
    )
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k, "") for k in fields})
    return out.getvalue()


def convert_cfu_bytes(
    xml_bytes: bytes,
    csv_separator: str = ",",
    include_raw_unfiltered: bool = True,
    include_scdl: bool = True,
    filter_scdl_empty_codrd: bool = True,
    filter_scdl_empty_section: bool = True,
    decimal_comma_scdl: bool = True
):
    """
    Convertit un XML CFU en CSV brut + CSV SCDL.

    Options :
    - include_raw_unfiltered :
        renvoie le CSV brut sans aucune modification ni filtre
    - include_scdl :
        renvoie le CSV SCDL
    - filter_scdl_empty_codrd :
        supprime du SCDL les lignes où BGT_CODRD est vide
    - filter_scdl_empty_section :
        supprime du SCDL les lignes où BGT_SECTION est vide
    - decimal_comma_scdl :
        met les nombres du SCDL au format français (virgule)
    """
    header = parse_header_bytes(xml_bytes)

    # =========================
    # RAW BRUT SANS MODIFICATION
    # =========================
    raw_rows = []
    raw_fields = set()

    for row in iter_lignebudget_bytes(xml_bytes):
        raw_rows.append(row)
        raw_fields.update(row.keys())

    raw_fields = sorted(raw_fields)
    raw_csv = None

    if include_raw_unfiltered:
        raw_csv = _write_csv_string(raw_rows, raw_fields, csv_separator)

    # =========================
    # SCDL
    # =========================
    scdl_fields = [
        "BGT_ID",
        "BGT_NATDEC", "BGT_ANNEE", "BGT_SIRET", "BGT_NOM",
        "BGT_CONTNAT", "BGT_CONTNAT_LABEL",
        "BGT_NATURE", "BGT_NATURE_LABEL",
        "BGT_FONCTION", "BGT_FONCTION_LABEL",
        "BGT_OPERATION", "BGT_SECTION",
        "BGT_OPBUDG", "BGT_CODRD", "BGT_ARTSPE",
        "BGT_MTREAL", "BGT_MTBUDGPREC", "BGT_MTRARPREC",
        "BGT_MTPROPNOUV", "BGT_MTPREV", "BGT_CREDOUV", "BGT_MTRAR3112",
        "BGT_NATURE_RAW", "BGT_NATURE_FIRST_DIGIT"
    ]

    scdl_rows = []
    lignes_supprimees_bgt_codrd_vide = 0
    lignes_supprimees_bgt_section_vide = 0

    if include_scdl:
        for raw in raw_rows:
            mapped_row = map_to_scdl(raw, header, decimal_comma=decimal_comma_scdl)

            if filter_scdl_empty_codrd and (mapped_row.get("BGT_CODRD") or "").strip() == "":
                lignes_supprimees_bgt_codrd_vide += 1
                continue

            if filter_scdl_empty_section and (mapped_row.get("BGT_SECTION") or "").strip() == "":
                lignes_supprimees_bgt_section_vide += 1
                continue

            scdl_rows.append(mapped_row)

        scdl_csv = _write_csv_string(scdl_rows, scdl_fields, csv_separator)
    else:
        scdl_csv = None

    stats = {
        "exercice": header.get("Exercice", ""),
        "siret": header.get("Siret", ""),
        "nom": header.get("Nom", ""),

        "lignes_raw": len(raw_rows),
        "raw_cols": len(raw_fields),

        "lignes_scdl": len(scdl_rows) if include_scdl else 0,
        "lignes_supprimees_bgt_codrd_vide": lignes_supprimees_bgt_codrd_vide,
        "lignes_supprimees_bgt_section_vide": lignes_supprimees_bgt_section_vide,

        "include_raw_unfiltered": include_raw_unfiltered,
        "include_scdl": include_scdl,
        "decimal_comma_scdl": decimal_comma_scdl,
    }

    return raw_csv, scdl_csv, stats
