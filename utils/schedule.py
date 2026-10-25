from datetime import datetime, time


def parse_hhmm(raw: str | None) -> time | None:
    if not raw:
        return None

    try:
        return datetime.strptime(raw.strip(), "%H:%M").time()
    except ValueError:
        return None


def in_window(now: time, start: str | None, end: str | None) -> bool:
    # True when `now` falls inside [start, end). A window that crosses
    # midnight (e.g. 22:00-06:00) is supported. No window configured means
    # downloads are always allowed.
    start_t, end_t = parse_hhmm(start), parse_hhmm(end)

    if start_t is None or end_t is None or start_t == end_t:
        return True

    if start_t < end_t:
        return start_t <= now < end_t

    return now >= start_t or now < end_t
