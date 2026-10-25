"""Génère les illustrations SVG fictives de démonstration dans static/images/.

Ce sont des visuels originaux, créés pour la démo (aucune image sous droits).
En production, les vraies photos seraient publiées dans un stockage objet
(ex. Amazon S3) sous les mêmes clés que celles stockées en base (image_key).
"""
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "static" / "images"
W, H = 480, 360


def wrap(body: str, bg1: str, bg2: str, label: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-label="{label}">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{bg1}"/><stop offset="1" stop-color="{bg2}"/></linearGradient></defs>
<rect width="{W}" height="{H}" fill="url(#g)"/>
<ellipse cx="240" cy="318" rx="150" ry="12" fill="#0b1f33" opacity=".12"/>
{body}
</svg>
'''


DARK, MID, LIGHT, ACCENT = "#14293f", "#3b5873", "#dbe6ef", "#f2a007"


def laptop(screen=ACCENT, big=False):
    w = 300 if big else 260
    x = 240 - w / 2
    return f'''<rect x="{x}" y="95" width="{w}" height="170" rx="10" fill="{DARK}"/>
<rect x="{x+10}" y="105" width="{w-20}" height="150" rx="4" fill="{screen}" opacity=".9"/>
<rect x="{x+10}" y="105" width="{w-20}" height="150" rx="4" fill="url(#g)" opacity=".25"/>
<path d="M{x-30} 270 H{x+w+30} L{x+w+14} 292 H{x-14} Z" fill="{MID}"/>
<rect x="215" y="274" width="50" height="5" rx="2.5" fill="{LIGHT}" opacity=".7"/>'''


def tower(h=190, w=100):
    x, y = 240 - w / 2, 300 - h
    return f'''<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{DARK}"/>
<rect x="{x+14}" y="{y+22}" width="{w-28}" height="8" rx="4" fill="{MID}"/>
<rect x="{x+14}" y="{y+40}" width="{w-28}" height="8" rx="4" fill="{MID}"/>
<circle cx="{x+w/2}" cy="{y+h-40}" r="14" fill="{ACCENT}"/>
<circle cx="{x+w/2}" cy="{y+h-40}" r="6" fill="{DARK}"/>'''


def router():
    ants = "".join(f'<rect x="{x}" y="60" width="8" height="120" rx="4" fill="{MID}"/>' for x in (150, 200, 272, 322))
    leds = "".join(f'<circle cx="{x}" cy="248" r="5" fill="{c}"/>' for x, c in ((190, "#4ade80"), (215, "#4ade80"), (240, ACCENT), (265, "#4ade80")))
    return f'''{ants}<rect x="110" y="170" width="260" height="100" rx="14" fill="{DARK}"/>{leds}
<rect x="130" y="194" width="220" height="6" rx="3" fill="{MID}"/>'''


def switch(ports=12):
    ps = "".join(f'<rect x="{70+i*27}" y="{190 if i%2==0 else 214}" width="20" height="18" rx="3" fill="{MID}" stroke="{ACCENT}" stroke-width="1"/>' for i in range(ports))
    return f'''<rect x="50" y="160" width="380" height="100" rx="10" fill="{DARK}"/>{ps}
<circle cx="72" cy="176" r="4" fill="#4ade80"/><rect x="92" y="172" width="120" height="8" rx="4" fill="{MID}"/>'''


def ap():
    return f'''<ellipse cx="240" cy="200" rx="110" ry="40" fill="{DARK}"/>
<ellipse cx="240" cy="190" rx="110" ry="40" fill="{LIGHT}"/>
<ellipse cx="240" cy="190" rx="70" ry="22" fill="{MID}" opacity=".35"/>
<circle cx="240" cy="190" r="6" fill="{ACCENT}"/>
<path d="M170 120 q70 -55 140 0" fill="none" stroke="{ACCENT}" stroke-width="6" stroke-linecap="round"/>
<path d="M195 140 q45 -32 90 0" fill="none" stroke="{ACCENT}" stroke-width="6" stroke-linecap="round"/>'''


def ups():
    return f'''<rect x="150" y="120" width="180" height="170" rx="14" fill="{DARK}"/>
<rect x="172" y="142" width="136" height="36" rx="6" fill="{MID}"/>
<rect x="182" y="152" width="70" height="8" rx="4" fill="#4ade80"/>
{''.join(f'<circle cx="{185+i*32}" cy="235" r="11" fill="{LIGHT}" opacity=".85"/>' for i in range(4))}
<path d="M246 255 l-12 20 h10 l-6 16 l18 -24 h-10 l8 -12 z" fill="{ACCENT}"/>'''


def monitor(w=280, h=170, curved=False):
    x = 240 - w / 2
    r = 30 if curved else 8
    return f'''<rect x="{x}" y="{250-h}" width="{w}" height="{h}" rx="{r if curved else 8}" fill="{DARK}"/>
<rect x="{x+10}" y="{260-h}" width="{w-20}" height="{h-20}" rx="3" fill="{ACCENT}" opacity=".9"/>
<rect x="{x+10}" y="{260-h}" width="{w-20}" height="{h-20}" rx="3" fill="url(#g)" opacity=".28"/>
<rect x="228" y="250" width="24" height="34" fill="{MID}"/>
<rect x="190" y="282" width="100" height="10" rx="5" fill="{MID}"/>'''


def keyboard():
    keys = "".join(f'<rect x="{85+c*30}" y="{135+r*38}" width="26" height="30" rx="5" fill="{LIGHT}"/>' for r in range(4) for c in range(12))
    return f'''<rect x="65" y="115" width="350" height="180" rx="14" fill="{DARK}"/>{keys}'''


def mouse():
    return f'''<path d="M240 90 C300 90 320 150 320 210 C320 265 285 295 240 295 C195 295 160 265 160 210 C160 150 180 90 240 90 Z" fill="{DARK}"/>
<path d="M240 90 V170" stroke="{MID}" stroke-width="4"/>
<rect x="228" y="130" width="24" height="34" rx="12" fill="{ACCENT}"/>'''


def ssd():
    return f'''<rect x="150" y="105" width="180" height="150" rx="20" fill="{DARK}" transform="rotate(-6 240 180)"/>
<rect x="170" y="125" width="140" height="14" rx="7" fill="{ACCENT}" transform="rotate(-6 240 180)"/>
<rect x="170" y="150" width="90" height="8" rx="4" fill="{MID}" transform="rotate(-6 240 180)"/>
<text x="240" y="218" font-family="sans-serif" font-size="30" font-weight="700" fill="{LIGHT}" text-anchor="middle" transform="rotate(-6 240 180)">1 TB</text>'''


def headset():
    return f'''<path d="M150 210 V170 a90 90 0 0 1 180 0 V210" fill="none" stroke="{DARK}" stroke-width="16" stroke-linecap="round"/>
<rect x="128" y="190" width="40" height="76" rx="16" fill="{MID}"/>
<rect x="312" y="190" width="40" height="76" rx="16" fill="{MID}"/>
<path d="M148 266 q-6 36 60 34" fill="none" stroke="{DARK}" stroke-width="6" stroke-linecap="round"/>
<circle cx="214" cy="300" r="9" fill="{ACCENT}"/>'''


def placeholder():
    return f'''<rect x="150" y="100" width="180" height="140" rx="12" fill="none" stroke="{MID}" stroke-width="6" stroke-dasharray="14 10"/>
<circle cx="205" cy="148" r="14" fill="{MID}"/><path d="M160 230 l50 -50 l32 32 l24 -22 l54 40 z" fill="{MID}"/>'''


ITEMS = {
    1: (laptop(), "#e8f1f8", "#c5d9ea", "Ordinateur portable ultrafin"),
    2: (laptop("#2dd4bf", big=True), "#e9f6f3", "#bfe6dd", "Ordinateur portable performance"),
    3: (tower(150, 90), "#f1f1f6", "#d4d6e6", "PC de bureau compact"),
    4: (tower(210, 120), "#f6eee3", "#ecd5b0", "Station de travail"),
    5: (router(), "#e8f1f8", "#c5d9ea", "Routeur Wi-Fi 6"),
    6: (switch(12), "#eef1f4", "#cfd8e1", "Switch 24 ports"),
    7: (ap(), "#eaf4ef", "#c4e2d3", "Point d'accès plafonnier"),
    8: (ups(), "#f6efe3", "#ecd9b4", "Onduleur 1000 VA"),
    9: (monitor(250, 150), "#e8f1f8", "#c5d9ea", "Moniteur 24 pouces"),
    10: (monitor(290, 175), "#eaf1f6", "#c9dbe8", "Moniteur 27 pouces QHD"),
    11: (monitor(330, 195), "#f0ecf7", "#d8cdea", "Moniteur 32 pouces 4K"),
    12: (monitor(380, 150, curved=True), "#e9f6f3", "#bfe6dd", "Moniteur ultrawide"),
    13: (keyboard(), "#eef1f4", "#cfd8e1", "Clavier sans fil"),
    14: (mouse(), "#f1f1f6", "#d4d6e6", "Souris ergonomique"),
    15: (ssd(), "#e8f1f8", "#c5d9ea", "SSD externe 1 To"),
    16: (headset(), "#f6eee3", "#ecd5b0", "Casque USB"),
}

OUT.mkdir(parents=True, exist_ok=True)
for n, (body, c1, c2, label) in ITEMS.items():
    (OUT / f"product-image-{n:03d}.svg").write_text(wrap(body, c1, c2, label), encoding="utf-8")
(OUT / "placeholder.svg").write_text(wrap(placeholder(), "#eef1f4", "#cfd8e1", "Image indisponible"), encoding="utf-8")
print(f"{len(ITEMS) + 1} images écrites dans {OUT}")
