"""
Baseline junk-shop prices (PHP per kg) per material category.

IMPORTANT: these are rough placeholder estimates, NOT live market prices.
Prices vary by city, junk shop, cleanliness and quantity. Ask 2-3 junk shops
near you (e.g. in Cebu) and edit the numbers below. The AI only picks the
material category; the prices always come from this table so the model can't
invent them.
"""

MATERIALS = {
    # key: (label, min_php_per_kg, max_php_per_kg)  -- None = not usually bought
    "plastic_pet":        ("Plastic (PET bottles)",      8,   15),
    "plastic_other":      ("Plastic (other)",            5,   12),
    "glass":              ("Glass",                      1,    3),
    "paper_cardboard":    ("Paper / cardboard",          2,    6),
    "metal_aluminum":     ("Metal (aluminum)",          50,   90),
    "metal_steel_tin":    ("Metal (steel / tin)",        8,   15),
    "metal_copper_brass": ("Metal (copper / brass)",   200,  450),
    "textile":            ("Textile / fabric",           1,    5),
    "electronic":         ("Electronics / e-waste",   None, None),
    "wood":               ("Wood",                    None, None),
    "rubber":             ("Rubber",                  None, None),
    "organic":            ("Organic",                 None, None),
    "composite":          ("Mixed / composite",       None, None),
    "other":              ("Other",                   None, None),
}

MATERIAL_KEYS = tuple(MATERIALS.keys())


def material_label(key: str) -> str:
    return MATERIALS.get(key, MATERIALS["other"])[0]


def scrap_value_for(key: str):
    """Return a dict with the baseline range, or None if junk shops usually don't buy it."""
    label, low, high = MATERIALS.get(key, MATERIALS["other"])
    if low is None:
        return None
    return {
        "min": low,
        "max": high,
        "unit": "PHP/kg",
        "note": "Rough estimate. Prices vary by shop and location; clean, sorted material sells for more.",
    }
