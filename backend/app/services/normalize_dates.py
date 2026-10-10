from datetime import date


def pretty_date(value: str | date | None, style: str = "day") -> str:
    """'2024-03-12' → '12 Mar 2024' (style='month' → 'Mar 2024', style='year' → '2024')."""
    if not value or value == "None":
        return "an unknown date"
    try:
        d = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    if style == "year":
        return str(d.year)
    return d.strftime("%b %Y") if style == "month" else f"{d.day} {d.strftime('%b %Y')}"
