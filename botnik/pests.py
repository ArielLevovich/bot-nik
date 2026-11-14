"""Pests and diseases common on the coastal plain (spec table), as data."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from botnik.models import Product


@dataclass(frozen=True)
class Pest:
    key: str
    name_he: str
    kind: str  # insect / mite / fungus / rot
    signs_he: str
    neem_ok: bool  # neem helps (for mildew: as prevention)
    confidor_ok: bool  # systemic, sucking insects only


PESTS: dict[str, Pest] = {
    p.key: p
    for p in [
        Pest("mealybug", "כנימה קמחית", "insect", "צמר לבן ודביק בבסיס העלים ובפרקים", True, True),
        Pest("aphids", "כנימות עלה", "insect", "מושבות על קצוות צעירים, דבש וטל דביק", True, True),
        Pest("whitefly", "זבוב לבן", "insect", "ענן לבן קטן כשמנערים את הצמח", True, True),
        Pest("spider_mites", "אקריות (עכביש אדום)", "mite", "נקודות בהירות על העלים וקורים דקים", True, False),
        Pest("leafminer", "מנהרן", "insect", "מנהרות כסופות בתוך עלים צעירים", False, False),
        Pest("mildew", "קמחון", "fungus", "ציפוי אבקתי לבן על פני העלה", True, False),
        Pest("root_rot", "עובש שורשים", "rot", "נבילה למרות שהמצע רטוב", False, False),
    ]
}

# What the owner sees -> which pest. Order = button order.
SYMPTOMS: list[tuple[str, str]] = [
    ("mealybug", "🐑 צמר לבן ודביק בפרקים"),
    ("mildew", "🌫 אבקה לבנה על פני העלה"),
    ("spider_mites", "🕸 נקודות בהירות וקורים דקים"),
    ("aphids", "🐜 מושבות קטנות על קצוות, דביק"),
    ("whitefly", "🦋 ענן לבן כשמנערים"),
    ("leafminer", "〰️ מנהרות כסופות בעלים"),
    ("root_rot", "🥀 נבול למרות שהמצע רטוב"),
]

# The classic confusion: asked again before opening an issue for either of these.
CONFUSABLE = ("mealybug", "mildew")
CONFUSION_TEXT = (
    "רגע, לוודא שזה לא בלבול נפוץ:\n"
    "• <b>כנימה קמחית</b> היא <b>חרק</b>: צמר לבן ודביק, בעיקר בפרקים ובבסיס העלים. "
    "אם מסתכלים מקרוב רואים גופים קטנים.\n"
    "• <b>קמחון</b> היא <b>פטרייה</b>: אבקה לבנה דקה על פני העלה, שנמחקת באצבע.\n"
    "מה מתאים יותר?"
)

SEVERITY_HE = {"light": "קל – כמה נקודות", "medium": "בינוני", "heavy": "כבד – הרבה, מתפשט"}

PRODUCT_NAMES = {"neem": "שמן נים", "confidor": "קונפידור"}


def product(session: Session, user_id: int, key: str | None) -> Product | None:
    """The home product for 'neem' / 'confidor', matched by its Hebrew name."""
    if key is None:
        return None
    name = PRODUCT_NAMES[key]
    return session.scalars(select(Product).where(Product.user_id == user_id, Product.name.contains(name))).first()
