"""Minimal SVG builder (XML-escaped, no extra deps)."""

from __future__ import annotations

from html import escape as _esc


def _e(text: object) -> str:
    return _esc(str(text), quote=True)


class Svg:
    def __init__(self, width: float, height: float, *, title: str = "", pad: float = 40.0) -> None:
        self.width = max(120.0, width + pad * 2)
        self.height = max(80.0, height + pad * 2)
        self.pad = pad
        self.title = title
        self._parts: list[str] = []

    def raw(self, markup: str) -> None:
        self._parts.append(markup)

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        stroke: str = "#8b9aab",
        width: float = 1.2,
        dashed: bool = False,
        opacity: float = 1.0,
        extra: str = "",
    ) -> None:
        dash = ' stroke-dasharray="5 4"' if dashed else ""
        self._parts.append(
            f'<line x1="{x1 + self.pad:.1f}" y1="{y1 + self.pad:.1f}" '
            f'x2="{x2 + self.pad:.1f}" y2="{y2 + self.pad:.1f}" '
            f'stroke="{_e(stroke)}" stroke-width="{width}" opacity="{opacity}"{dash} {extra}/>'
        )

    def path(
        self,
        d: str,
        *,
        stroke: str = "#8b9aab",
        fill: str = "none",
        width: float = 1.4,
        opacity: float = 0.85,
        extra: str = "",
    ) -> None:
        self._parts.append(
            f'<path d="{_e(d)}" stroke="{_e(stroke)}" fill="{_e(fill)}" '
            f'stroke-width="{width}" opacity="{opacity}" {extra}/>'
        )

    def circle(
        self,
        x: float,
        y: float,
        r: float = 6.5,
        *,
        fill: str = "#3dd6c6",
        stroke: str = "#0f1419",
        sw: float = 2.0,
        title: str = "",
        extra: str = "",
    ) -> None:
        inner = f"<title>{_e(title)}</title>" if title else ""
        self._parts.append(
            f'<circle cx="{x + self.pad:.1f}" cy="{y + self.pad:.1f}" r="{r}" '
            f'fill="{_e(fill)}" stroke="{_e(stroke)}" stroke-width="{sw}" {extra}>'
            f"{inner}</circle>"
        )

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        fill: str = "#161d27",
        stroke: str = "#243041",
        rx: float = 4.0,
        extra: str = "",
    ) -> None:
        self._parts.append(
            f'<rect x="{x + self.pad:.1f}" y="{y + self.pad:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{rx}" fill="{_e(fill)}" stroke="{_e(stroke)}" {extra}/>'
        )

    def text(
        self,
        x: float,
        y: float,
        content: str,
        *,
        fill: str = "#e7ecf1",
        size: float = 10.0,
        anchor: str = "start",
        extra: str = "",
    ) -> None:
        self._parts.append(
            f'<text x="{x + self.pad:.1f}" y="{y + self.pad:.1f}" fill="{_e(fill)}" '
            f'font-size="{size}" text-anchor="{anchor}" font-family="Segoe UI,system-ui,sans-serif" {extra}>'
            f"{_e(content)}</text>"
        )

    def tostring(self) -> str:
        title = f"<title>{_e(self.title)}</title>" if self.title else ""
        body = "\n".join(self._parts)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width:.0f} {self.height:.0f}" '
            f'width="100%" role="img">'
            f"{title}"
            f'<rect width="100%" height="100%" fill="#0f1419"/>'
            f"{body}</svg>"
        )
