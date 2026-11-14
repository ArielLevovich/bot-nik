"""Hebrew labels for values stored in English in the database."""

from __future__ import annotations

STATUS_EMOJI = {"good": "🟢", "watch": "🟡", "needs_care": "🔴", "unknown": "⚪"}
STATUS_HE = {"good": "טוב", "watch": "במעקב", "needs_care": "צריך טיפול", "unknown": "לא ידוע"}

AREA_HE = {
    "main_railing": "מעקה ראשי",
    "corner": "פינה",
    "north_railing": "מעקה צפוני",
    "upper_opening": "פתח עליון",
    "back_wall": "קיר הבטון",
    "ceiling_hanging": "תלוי מהתקרה",
    "entrance": "כניסה",
}
NO_SLOT_KEY = "none"
NO_SLOT_HE = "ללא מיקום"

LEVEL_HE = {
    "railing": "על המעקה",
    "railing_hanging": "תלוי על המעקה",
    "shelf": "מדף",
    "floor": "רצפה",
    "hanging": "תלוי",
}
SHAPE_HE = {"round": "עגול", "rectangular": "מלבני", "elliptical": "אליפטי", "roundish": "עגלגל"}
MATERIAL_HE = {
    "plastic": "פלסטיק",
    "plastic (thick)": "פלסטיק עבה",
    "plastic (nursery pot)": "פלסטיק (עציץ משתלה)",
    "ceramic": "קרמיקה",
}
COLOR_HE = {
    "white": "לבן",
    "red": "אדום",
    "black": "שחור",
    "dark grey": "אפור כהה",
    "blue": "כחול",
    "light blue": "תכלת",
    "terracotta": "טרקוטה",
    "pink": "ורוד",
}
SUBSTRATE_HE = {"succulent mix": "מצע לסוקולנטים"}
TYPE_HE = {"red_rail_large": "אדנית מעקה אדומה גדולה", "red_rail_small": "אדנית מעקה אדומה קטנה"}
SECTION_HE = {"A": "צד A", "B": "צד B", "AB": "במרכז (A+B)"}

MISSING_HE = {
    "outer": "מידות",
    "outer.width": "רוחב",
    "outer.length": "אורך",
    "outer.height": "גובה המיכל",
    "outer.diameter": "קוטר",
    "outer_raw_meaning": "מה המשמעות של המידה שנרשמה",
    "level": "גובה הצבה (מעקה/מדף/רצפה/תלוי)",
    "shape": "צורה",
    "material": "חומר",
    "color": "צבע",
    "condition": "מצב הצמח",
    "slot": "מיקום במפה",
    "section": "צד באדנית",
    "section_assignment_by_color": "איזה צבע באיזה צד",
}


def he(table: dict[str, str], value: str | None, empty: str = "—") -> str:
    """Translate a value; unknown values are shown as-is, None as a dash."""
    if value is None:
        return empty
    return table.get(value, value)


def missing_he(key: str) -> str:
    if key in MISSING_HE:
        return MISSING_HE[key]
    if key.startswith("outer"):  # e.g. "outer (meaning of 10×12)"
        return "מידות (מה המשמעות של 10×12?)" if "10×12" in key else "מידות"
    return key
