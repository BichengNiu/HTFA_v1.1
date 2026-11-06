"""HTML presentation of prepared monitoring cards."""

from html import escape


def cards_html(cards, css_class="monitoring-cards"):
    def visible_lines(label, lines):
        if label in {"港口监测", "咽喉点监测", "油田监测"}:
            return []
        return lines

    return (
        f'<div class="{css_class}">'
        + "".join(
            '<div class="monitoring-card">'
            + f"<span>{escape(label)}</span>"
            + (f"<strong>{escape(value)}</strong>" if value else "")
            + "".join(
                f'<div class="monitoring-card-detail">{escape(line)}</div>'
                for line in visible_lines(label, lines)
            )
            + "</div>"
            for label, value, *lines in cards
        )
        + "</div>"
    )
