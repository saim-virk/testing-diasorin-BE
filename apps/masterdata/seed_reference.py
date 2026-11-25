"""Reference data from the URS (DSI-FORM-000208) and the prototype. Used by the data migration.

Frozen copy: migrations import this module, so change it only together with a new migration.
"""

# (code, description_it, description_en, un_number, hazard, default_temperature)
PVARI = [
    ("P9935", "Materiale pubblicitario (carta)", "Advertising material (paper)", "", "UNINFECTED", "AMBIENT"),
    (
        "P9925",
        "Materiale vario (parti ricambio, plastica, materiale pubblicitario no carta)",
        "Various material (spare parts, plastic, advertising mat. not paper)",
        "",
        "UNINFECTED",
        "AMBIENT",
    ),
    (
        "P9993",
        "Prodotti diagnostici ed altri materiali",
        "Diagnostic products and other materials",
        "",
        "UNINFECTED",
        "COOL_2_8",
    ),
    (
        "P9930",
        "Prodotti diagnostici ed altri materiali",
        "Diagnostic products and other materials",
        "",
        "UNINFECTED",
        "DRY_ICE",
    ),
    (
        "P9902",
        "Materia infettante per l'uomo",
        "Infectious substance affecting humans",
        "UN 2814",
        "INFECTIOUS",
        "COOL_2_8",
    ),
    (
        "P9996",
        "Sostanza infetta di origine umana",
        "Infectious substance affecting humans",
        "UN 2814",
        "INFECTIOUS",
        "DRY_ICE",
    ),
    (
        "P9903",
        "Materia infettante per gli animali, unicamente",
        "Infectious substance affecting animals",
        "UN 2900",
        "INFECTIOUS",
        "COOL_2_8",
    ),
    (
        "P9997",
        "Materia infettante per gli animali, unicamente",
        "Infectious substance affecting animals",
        "UN 2900",
        "INFECTIOUS",
        "DRY_ICE",
    ),
    (
        "P9929",
        "Microrganismi geneticamente modificati (MOGM)",
        "Genetically Modified Micro-organisms (GMMOs)",
        "UN 3245",
        "INFECTIOUS",
        "DRY_ICE",
    ),
    (
        "P9901",
        "Materia biologica Categoria B",
        "Biological Substance Category B",
        "UN 3373",
        "INFECTIOUS",
        "COOL_2_8",
    ),
    (
        "P9995",
        "Materia biologica Categoria B",
        "Biological Substance Category B",
        "UN 3373",
        "INFECTIOUS",
        "DRY_ICE",
    ),
]

# (scope_group, code, description_it, description_en)
REASON_CODES = [
    (
        "ITALY",
        "10",
        "Prove per convalide di ricerca di nostra produzione",
        "Trials for research validations of our manufacturing",
    ),
    ("ITALY", "15", "Materiale inviato in sostituzione", "Material sent to be replenished"),
    ("ITALY", "42", "Strumento POC in omaggio al Cliente", "Free POC instrument sent to Customer"),
    ("ITALY", "53", "Conto lavorazione e taratura", "Manufacturing account and calibration"),
    ("ITALY", "63", "Merce Diasorin c/o clienti in visione", "DiaSorin goods on consignment"),
    (
        "ITALY",
        "79",
        "Trasferimento ricambi per ricondizionamento strumenti",
        "Transfer of spares for instruments reconditioning",
    ),
    ("ITALY", "91", "Imballaggi vuoti", "Empty packages"),
    ("ITALY", "85", "Trasferimento materiale", "Transfer of material"),
    (
        "ITALY",
        "100",
        "Invio consumabili per integrazione PDF",
        "Transfer of consumables supply plans replenishment",
    ),
    (
        "ITALY",
        "101",
        "Invio access. causa rotture (es. Rack)",
        "Transfer of accessories due to breakdown (e.g. Rack)",
    ),
    (
        "ITALY",
        "102",
        "Invio mat. per manutenzione semestr. MDX",
        "Transfer of materials for six months MDX maintenance",
    ),
    ("EU_EXTRA", "01", "Unità reinviata al fornitore", "Unit returned to the supplier"),
    (
        "EU_EXTRA",
        "02",
        "Trasferimento materiale per lavorazione / riparazione",
        "Transfer of material for working / repair",
    ),
    (
        "EU_EXTRA",
        "08",
        "Trasferimento materiale di nostra produzione",
        "Transfer of material of our manufacturing",
    ),
    ("EU_EXTRA", "09", "Campioni per prove tecniche", "Samples for technical trials"),
    ("EU_EXTRA", "16", "Campioni per valutazioni cliniche", "Samples for clinical evaluation"),
    ("EU_EXTRA", "17", "Materiale pubblicitario", "Advertising material"),
    ("EU_EXTRA", "18", "Omologazione", "Homologation"),
    ("EU_EXTRA", "19", "Campioni per scopi dimostrativi", "Samples for demonstration purposes"),
    ("EU_EXTRA", "95", "Prodotto di rimpiazzo", "Product replacement"),
    (
        "EU_EXTRA",
        "A6",
        "Trasferimento materiale come concordato (da contratto)",
        "Transfer of materials agreement (as per contract)",
    ),
    (
        "EU_EXTRA",
        "10A",
        "Prove per convalide di ricerca di nostra produzione",
        "Trials for research validations of our manufacturing",
    ),
]

# (code, dimensions, description)
PACKAGING = [
    ("I/2", "10 × 14 × 27 cm", ""),
    ("I/4", "25 × 24 × 24 cm", ""),
    ("I/6", "40 × 30 × 30 cm", ""),
    ("I/6 S", "40 × 30 × 30 cm", "dry ice"),
    ("I/6 G", "40 × 30 × 30 cm", "cool packs"),
    ("I/10", "37 × 37 × 52 cm", ""),
    ("I/10 S", "37 × 37 × 52 cm", "dry ice"),
    ("I/10 G", "37 × 37 × 52 cm", "cool packs"),
    ("I/14", "60 × 40 × 50 cm", ""),
    ("I/14 S", "60 × 40 × 50 cm", "dry ice"),
    ("I/14 G", "60 × 40 × 50 cm", "cool packs"),
    ("I/16", "80 × 120 × 80 cm", ""),
    ("I/18", "80 × 120 × 80 cm", ""),
]

# (iso2, name, scope) — prototype COUNTRIES
COUNTRIES = (
    [("IT", "Italy", "ITALY")]
    + [
        (c, n, "EU")
        for c, n in [
            ("AT", "Austria"),
            ("BE", "Belgium"),
            ("BG", "Bulgaria"),
            ("HR", "Croatia"),
            ("CY", "Cyprus"),
            ("CZ", "Czech Republic"),
            ("DK", "Denmark"),
            ("EE", "Estonia"),
            ("FI", "Finland"),
            ("FR", "France"),
            ("DE", "Germany"),
            ("GR", "Greece"),
            ("HU", "Hungary"),
            ("IE", "Ireland"),
            ("LV", "Latvia"),
            ("LT", "Lithuania"),
            ("LU", "Luxembourg"),
            ("MT", "Malta"),
            ("NL", "Netherlands"),
            ("PL", "Poland"),
            ("PT", "Portugal"),
            ("RO", "Romania"),
            ("SK", "Slovakia"),
            ("SI", "Slovenia"),
            ("ES", "Spain"),
            ("SE", "Sweden"),
        ]
    ]
    + [("US", "United States", "USA")]
    + [
        (c, n, "EXTRA_EU")
        for c, n in [
            ("AR", "Argentina"),
            ("AU", "Australia"),
            ("BR", "Brazil"),
            ("CA", "Canada"),
            ("CN", "China"),
            ("IN", "India"),
            ("IL", "Israel"),
            ("JP", "Japan"),
            ("MX", "Mexico"),
            ("NO", "Norway"),
            ("SA", "Saudi Arabia"),
            ("SG", "Singapore"),
            ("ZA", "South Africa"),
            ("KR", "South Korea"),
            ("CH", "Switzerland"),
            ("TR", "Türkiye"),
            ("AE", "United Arab Emirates"),
            ("GB", "United Kingdom"),
        ]
    ]
)

CURRENCIES = [
    "EUR",
    "USD",
    "GBP",
    "CHF",
    "JPY",
    "CNY",
    "CAD",
    "AUD",
    "SEK",
    "DKK",
    "NOK",
    "PLN",
    "CZK",
    "HUF",
]

CARRIERS = ["DHL Medical Express", "DHL Express", "World Courier", "UPS Healthcare", "Dedicated transport"]

# (code, name, applies_calendar)
SHIPS_FROM = [("SALUGGIA", "Saluggia", True), ("GERENZANO", "Gerenzano", False), ("OTHER", "Other", False)]

# Saluggia: Monday–Thursday allowed (prototype assumption; real calendar DSI-ATTACH-000594 pending)
SALUGGIA_ALLOWED_WEEKDAYS = {0, 1, 2, 3}
