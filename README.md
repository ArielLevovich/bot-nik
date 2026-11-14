# בוט־ניק 🌱

בוט טלגרם אישי לניהול הגינה במרפסת.

## התקנה (פעם אחת)

```bash
uv venv --python 3.12 .venv     # או: python3.12 -m venv .venv
source .venv/bin/activate        # ב-Windows: .venv\Scripts\activate
uv pip install -r requirements.txt   # או: pip install -r requirements.txt
cp .env.example .env             # ואז למלא את הטוקן מ-@BotFather
```

## הרצה

```bash
python -m botnik.seed    # טוען את data/garden.yaml למסד הנתונים (אפשר להריץ שוב בלי כפילויות)
python -m botnik.bot     # מפעיל את הבוט
```

שולחים לבוט `/myid`, מעתיקים את המספר ל-`ALLOWED_USER_IDS` בקובץ `.env`, ומפעילים מחדש.

## בדיקות

```bash
pytest
```

## פקודות בטלגרם

- `/start` – מה הבוט יודע לעשות
- `/garden` – כל הגינה לפי אזורים; לחיצה על אזור ואז על עציץ פותחת את הכרטיס המלא
- `/missing` – עציצים שחסרים להם פרטים
- `/myid` – מספר המשתמש שלך (עובד גם לפני שנוספת לרשימה המורשית)

שינוי בקוד דורש הפעלה מחדש של הבוט (Ctrl+C ואז שוב `python -m botnik.bot`).
שינוי ב־`data/garden.yaml` דורש רק הרצה מחדש של `python -m botnik.seed`.
