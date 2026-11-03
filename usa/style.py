"""Gemeinsames Layout (US Letter, englisch) der US-Musterunterlagen."""

from html import escape

CSS = """
@page { size: Letter; margin: 15mm 14mm 17mm 14mm;
  @top-left { content: "__KOPF__"; font: 7.5pt 'Liberation Sans', 'DejaVu Sans', sans-serif; color: #666; }
  @top-right { content: "__DOK__"; font: 7.5pt 'Liberation Sans', 'DejaVu Sans', sans-serif; color: #666; }
  @bottom-left { content: "__FUSS__"; font: 7.5pt 'Liberation Sans', 'DejaVu Sans', sans-serif; color: #666; }
  @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 7.5pt 'Liberation Sans', 'DejaVu Sans', sans-serif; color: #666; }
}
* { box-sizing: border-box; }
body { font-family: 'Liberation Sans', 'DejaVu Sans', Arial, sans-serif; font-size: 9pt; color: #1b1b1b; line-height: 1.35; margin: 0; }
h1 { font-size: 18pt; margin: 0 0 2px; color: #14532d; }
h2 { font-size: 12pt; margin: 16px 0 6px; color: #14532d; border-bottom: 1.5px solid #14532d; padding-bottom: 2px; break-after: avoid; }
h3 { font-size: 10pt; margin: 10px 0 4px; break-after: avoid; }
p { margin: 4px 0; }
.sub { color: #444; margin-bottom: 8px; }
table { border-collapse: collapse; width: 100%; margin: 4px 0 8px; break-inside: auto; }
tr { break-inside: avoid; }
th, td { border: 0.6px solid #b8b8b8; padding: 2.5px 4px; vertical-align: top; }
th { background: #eef4ef; font-weight: bold; text-align: left; font-size: 8pt; }
td.n, th.n { text-align: right; white-space: nowrap; }
tr.sum td { font-weight: bold; background: #f4f4f4; }
tr.tot td { font-weight: bold; background: #e6efe8; }
table.s td, table.s th { font-size: 7.8pt; padding: 2px 3px; }
table.info td:first-child { width: 26%; color: #444; }
.sample { border: 2px solid #b91c1c; color: #b91c1c; padding: 6px 10px; margin: 8px 0 10px; font-weight: bold; font-size: 8.5pt; }
.wm { position: fixed; top: 40%; left: 0; width: 100%; text-align: center; font-size: 110pt; font-weight: bold;
  color: rgba(185, 28, 28, 0.06); transform: rotate(-28deg); z-index: -1; letter-spacing: 8px; }
.tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin: 6px 0 4px; }
.tile { border: 0.8px solid #b8b8b8; border-radius: 4px; padding: 6px 8px; break-inside: avoid; }
.tile .v { font-size: 13.5pt; font-weight: bold; color: #14532d; }
.tile .l { font-size: 7.8pt; color: #444; }
.note { font-size: 7.8pt; color: #444; }
.pass { color: #166534; font-weight: bold; }
.fail { color: #b91c1c; font-weight: bold; }
.verdict { border: 2px solid #166534; background: #f0fdf4; padding: 10px 12px; margin: 8px 0; break-inside: avoid; }
.verdict .big { font-size: 16pt; font-weight: bold; color: #166534; }
ul { margin: 4px 0 4px 18px; padding: 0; }
li { margin: 2px 0; }
.pb { break-before: page; }
.keep { break-inside: avoid; }
.fig { border: 0.6px solid #d4d4d4; padding: 6px; margin: 6px 0; break-inside: avoid; }
.sig { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 18px; break-inside: avoid; }
.sig div { border-top: 0.8px solid #1b1b1b; padding-top: 3px; font-size: 8pt; color: #444; }
.formula { font-family: 'DejaVu Sans Mono', monospace; font-size: 8pt; background: #f6f6f6; padding: 4px 6px; margin: 4px 0; }
"""


def t(x):
    return escape(str(x))


def n(x, d=0):
    return "–" if x is None else f"{x:,.{d}f}"


def table(head, rows, cls="", num=(), row_cls=None):
    h = [f'<table class="{cls}"><thead><tr>']
    for i, k in enumerate(head):
        h.append(f'<th class="{"n" if i in num else ""}">{k}</th>')
    h.append("</tr></thead><tbody>")
    for j, z in enumerate(rows):
        h.append(f'<tr class="{row_cls[j] if row_cls else ""}">')
        for i, c in enumerate(z):
            h.append(f'<td class="{"n" if i in num else ""}">{c}</td>')
        h.append("</tr>")
    h.append("</tbody></table>")
    return "".join(h)


def info(rows):
    return '<table class="info">' + "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in rows) + "</table>"


def tiles(items):
    return '<div class="tiles">' + "".join(
        f'<div class="tile"><div class="v">{v}</div><div class="l">{t(l)}</div></div>' for v, l in items) + "</div>"


def ok(flag):
    return '<span class="pass">PASS</span>' if flag else '<span class="fail">FAIL</span>'


def page_start(p, doc_title, date):
    pj = p["project"]
    css = (CSS.replace("__KOPF__", pj["prepared_by"]["company"].replace('"', ""))
              .replace("__DOK__", doc_title)
              .replace("__FUSS__", f"{pj['title']} · {date:%m/%d/%Y} · SAMPLE".replace('"', "")))
    o = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{t(doc_title)}</title><style>{css}</style></head><body>"]
    if pj.get("sample"):
        o.append('<div class="wm">SAMPLE</div>')
    return o


def signature(p, role):
    pb = p["project"]["prepared_by"]
    return (f'<div class="sig"><div>{t(role)}: {t(pb["name"])}, {t(pb["credentials"])}<br>{t(pb["company"])} · {t(pb["email"])}</div>'
            '<div>Signature / date</div></div>')
