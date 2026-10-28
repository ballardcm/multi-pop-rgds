"""Build the theme's platform cards from original PNG hardware artwork."""

from pathlib import Path
import json
import sys
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1] / "multi-pop-rgds"
FONT = ROOT / "assets/fonts/RobotoCondensed-Bold.ttf"
REGULAR = ROOT / "assets/fonts/Roboto-Regular.ttf"
INK = "191A2E"

# Each installed platform has its own color, while the hardware preserves its original material colors.
SYSTEMS = {
    "fbneo": ("Final Burn Neo", "Arcade", "2002", "E9B33F"),
    "atari2600": ("Atari 2600", "Atari", "1977", "9B522B"),
    "atari5200": ("Atari 5200", "Atari", "1982", "5C6774"),
    "atari7800": ("Atari 7800", "Atari", "1986", "A9B0B7"),
    "atarilynx": ("Atari Lynx", "Atari", "1989", "F2CB57"),
    "atarijaguar": ("Atari Jaguar", "Atari", "1993", "B6283D"),
    "wonderswancolor": ("WonderSwan Color", "Bandai", "2000", "48AABD"),
    "colecovision": ("ColecoVision", "Coleco", "1982", "BD405B"),
    "intellivision": ("Intellivision", "Mattel", "1979", "947146"),
    "c64": ("Commodore 64", "Commodore", "1982", "3567A8"),
    "pico8": ("PICO-8", "Lexaloffle", "2015", "EF70A5"),
    "xbox": ("Xbox", "Microsoft", "2001", "357D28"),
    "pcengine": ("PC Engine", "NEC", "1987", "E8D8AA"),
    "pce-cd": ("PC Engine CD", "NEC", "1988", "A88872"),
    "nes": ("Nintendo Entertainment System", "Nintendo", "1985", "B83931"),
    "gb": ("Game Boy", "Nintendo", "1989", "A3AD46"),
    "snes": ("Super Nintendo", "Nintendo", "1991", "B49EE1"),
    "n64": ("Nintendo 64", "Nintendo", "1996", "156B59"),
    "gbc": ("Game Boy Color", "Nintendo", "1998", "78BE48"),
    "gc": ("GameCube", "Nintendo", "2001", "5B32DF"),
    "gba": ("Game Boy Advance", "Nintendo", "2001", "393977"),
    "nds": ("Nintendo DS", "Nintendo", "2004", "C8D5DF"),
    "3ds": ("Nintendo 3DS", "Nintendo", "2011", "EB5E52"),
    "virtualboy": ("Virtual Boy", "Nintendo", "1995", "D81F36"),
    "atomiswave": ("Atomiswave", "Sammy", "2003", "F5A53D"),
    "sg-1000": ("SG-1000", "Sega", "1983", "6AAAD8"),
    "mastersystem": ("Master System", "Sega", "1985", "D74A49"),
    "genesis": ("Genesis", "Sega", "1989", "243858"),
    "segacd": ("Sega CD", "Sega", "1992", "9AA4D9"),
    "saturn": ("Saturn", "Sega", "1994", "426B8E"),
    "gamegear": ("Game Gear", "Sega", "1990", "177D8D"),
    "sega32x": ("Sega 32X", "Sega", "1994", "993BCE"),
    "model3": ("Sega Model 3", "Sega", "1996", "0765C2"),
    "dreamcast": ("Dreamcast", "Sega", "1998", "E57731"),
    "naomi": ("Naomi", "Sega", "1998", "98C8CC"),
    "neogeo": ("Neo Geo", "SNK", "1990", "D7AD27"),
    "ngp": ("Neo Geo Pocket", "SNK", "1998", "646C78"),
    "ngpc": ("Neo Geo Pocket Color", "SNK", "1999", "4B55A4"),
    "vectrex": ("Vectrex", "GCE", "1982", "427D80"),
    "ps2": ("PlayStation 2", "Sony", "2000", "2448CC"),
    "ps3": ("PlayStation 3", "Sony", "2006", "373B45"),
    "steam": ("Steam", "PC Gaming", "", "287BB5"),
    "music": ("Music Player", "Your Collection", "", "A42883"),
    "ports": ("Ports", "PC Gaming", "", "3F7269"),
    "tools": ("Tools", "Thor Utilities", "", "B16B49"),
    "auto-favorites": ("Favorites", "Your Collection", "", "C73269"),
    "psx": ("PlayStation", "Sony", "1994", "77796F"),
    "psp": ("PSP", "Sony", "2004", "2A4D62"),
    "psvita": ("PlayStation Vita", "Sony", "2011", "1686C7"),
    "sfc": ("Super Famicom", "Nintendo", "1990", "EEEDEE"),
    "famicom": ("Famicom", "Nintendo", "1983", "8D1C32"),
    "megadrive": ("Mega Drive", "Sega", "1988", "172D3B"),
    "mame": ("MAME", "Arcade", "1997", "623C7E"),
    "arcade": ("Arcade", "Coin-Op Classics", "", "D33D23"),
    "auto-allgames": ("All Games", "Your Collection", "", "1F9C94"),
    "auto-lastplayed": ("Recently Played", "Your Collection", "", "FAAE82"),
    "wii": ("Wii", "Nintendo", "2006", "93BFC9"),
    "wiiu": ("Wii U", "Nintendo", "2012", "258BB1"),
    "switch": ("Nintendo Switch", "Nintendo", "2017", "DE564D"),
    "3do": ("3DO", "Panasonic", "1993", "485B83"),
    "amiga": ("Amiga", "Commodore", "1985", "D99565"),
    "atarist": ("Atari ST", "Atari", "1985", "8699AB"),
    "zxspectrum": ("ZX Spectrum", "Sinclair", "1982", "D6A851"),
    "msx": ("MSX", "MSX", "1983", "B9535A"),
    "wonderswan": ("WonderSwan", "Bandai", "1999", "A7B5C0"),
    "tg16": ("TurboGrafx-16", "NEC", "1989", "D79439"),
    "tg-cd": ("TurboGrafx-CD", "NEC", "1989", "707A9E"),
    "channelf": ("Channel F", "Fairchild", "1976", "A36834"),
    "odyssey": ("Odyssey²", "Magnavox", "1978", "605f5A"),
    "fds": ("Famicom Disk System", "Nintendo", "1986", "99132E"),
    "msx2": ("MSX2", "MSX", "1985", "161313"),
    "megacd": ("Mega CD", "Sega", "1992", "7D89C4"),
    "scv": ("Super Cassette Vision", "Epoch", "1984", "BB731B"),
    "megaduck": ("Mega Duck", "Welback", "1993", "159097"),
    "n64dd": ("Nintendo 64 DD", "Nintendo", "1999", "1A826B"),
    "pokemini": ("Pokémon Mini", "Nintendo", "2001", "5F1A82"),
    "doom": ("Doom", "ID", "1993", "1C380A"),
    "tic-80": ("TIC-80", "Nesbox", "2017", "275F7C"),
    "wasm4": ("WASM-4", "Bruno Garcia", "2021", "06540F"),
    "supervision": ("Supervision", "Watara", "1992", "3EDAD6"),
    "default": ("Game Library", "Multi Pop", "", "6D4776"),
}


def rgb(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def luminance(hex_color):
    values = [c / 255 for c in rgb(hex_color)]
    linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in values]
    return sum(c * weight for c, weight in zip(linear, (.2126, .7152, .0722)))


def foreground(accent):
    dark_ink = "000000"
    light = 1.05 / (luminance(accent) + .05)
    dark = (luminance(accent) + .05) / (luminance(dark_ink) + .05)
    return "FFFFFF" if light >= dark else dark_ink

def selection_accent(accent, paper="F7F8FC"):
    paper_lum = luminance(paper)
    def contrast(color):
        return (paper_lum + 0.05) / (luminance(color) + 0.05)
    if contrast(accent) >= 3:
        return accent
    low, high = 0.0, 1.0
    for _ in range(32):
        factor = (low + high) / 2
        candidate = "".join(
            f"{round(c * factor):02X}" for c in rgb(accent)
        )
        if contrast(candidate) >= 3.05:
            low = factor
        else:
            high = factor
    return "".join(f"{round(c * low):02X}" for c in rgb(accent))

def tint(accent, amount):
    return tuple(round(c * amount + 248 * (1 - amount)) for c in rgb(accent))


def draw_lines(draw, text, x, y, width, font_size, fill, max_lines=3, max_height=None):
    while font_size > 18:
        font = ImageFont.truetype(str(FONT), font_size)
        lines = []
        for word in text.split():
            if lines and draw.textlength(lines[-1] + " " + word, font=font) <= width:
                lines[-1] += " " + word
            else:
                lines.append(word)
        fits_height = max_height is None or len(lines) * font_size * 1.12 <= max_height
        if fits_height and len(lines) <= max_lines and all(draw.textlength(line, font=font) <= width for line in lines):
            break
        font_size -= 2
    for line in lines:
        draw.text((x, y), line, fill=fill, font=font)
        y += font_size * 1.12
    return y


def make_art(key, details, hardware):
    title, maker, year, accent = details
    color, text_color = rgb(accent), rgb(foreground(accent))
    card = Image.new("RGBA", (400, 640), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle((0, 0, 399, 639), radius=28, fill="#FAFBFE", outline=tint(accent, .4), width=3)
    draw.rounded_rectangle((0, 0, 399, 190), radius=28, fill=color)
    draw.rectangle((0, 110, 399, 190), fill=color)
    draw.text((28, 22), maker.upper(), fill=text_color, font=ImageFont.truetype(str(REGULAR), 19))
    draw_lines(draw, title, 28, 61, 345, 47, text_color, max_lines=3, max_height=112)
    draw.ellipse((42, 435, 358, 475), fill=tint(accent, .12))
    small = hardware.copy()
    small.thumbnail((382, 286), Image.Resampling.LANCZOS)
    card.alpha_composite(small, ((400 - small.width) // 2, 205 + (286 - small.height) // 2))
    draw.text((28, 550), year or "YOUR LIBRARY", fill=rgb(INK), font=ImageFont.truetype(str(FONT), 34))
    draw.line((28, 527, 372, 527), fill=tint(accent, .45), width=3)
    draw.text((28, 598), "MULTI POP  /  RGDS", fill="#646A80", font=ImageFont.truetype(str(REGULAR), 17))
    card.save(ROOT / "assets/cards" / (key + ".png"))

    # An opaque rectangular stage fills the upper panel without a card floating over a second background.
    hero = Image.new("RGBA", (1600, 900), "#FAFBFE")
    draw = ImageDraw.Draw(hero)
    draw.rectangle((630, 0, 1599, 899), fill=tint(accent, .20))
    draw.rounded_rectangle((84, 78, 560, 146), radius=20, fill=color)
    draw.text((108, 94), maker.upper(), fill=text_color, font=ImageFont.truetype(str(REGULAR), 32))
    draw_lines(draw, title, 84, 255, 530, 104, rgb(INK), max_lines=3)
    draw.text((86, 739), year or "YOUR COLLECTION", fill=rgb(INK), font=ImageFont.truetype(str(FONT), 56))
    draw.ellipse((695, 735, 1490, 802), fill=tint(accent, .32))
    large = hardware.copy()
    large.thumbnail((1040, 780), Image.Resampling.LANCZOS)
    hero.alpha_composite(large, (580 + (1040 - large.width) // 2, 74 + (780 - large.height) // 2))
    hero.save(ROOT / "assets/heroes" / (key + ".png"))


def make_grid():
    # Building the overview from the same heroes keeps the README artwork in sync with the theme.
    columns, width, height, gap = 5, 400, 225, 18
    rows = (len(SYSTEMS) + columns - 1) // columns
    grid = Image.new("RGB", (columns * width + (columns + 1) * gap,
                             100 + rows * height + (rows + 1) * gap), "#ECEEF5")
    draw = ImageDraw.Draw(grid)
    draw.text((18, 18), "Multi Pop — all systems", fill=rgb(INK),
              font=ImageFont.truetype(str(REGULAR), 34))
    draw.text((18, 64), f"{len(SYSTEMS)} original hardware and collection designs · includes Virtual Boy",
              fill="#646A80", font=ImageFont.truetype(str(REGULAR), 20))
    for index, key in enumerate(SYSTEMS):
        with Image.open(ROOT / "assets/heroes" / (key + ".png")) as hero:
            preview = hero.resize((width, height), Image.Resampling.LANCZOS)
            grid.paste(preview, (gap + index % columns * (width + gap),
                                 100 + index // columns * (height + gap)), preview)
    grid.save(ROOT.parent / "docs/artwork-grid.png")


def main():
    logos = json.loads((ROOT / "assets/logos/catalog.json").read_text())
    for name in ["palettes", "assets/cards", "assets/heroes"]:
        (ROOT / name).mkdir(parents=True, exist_ok=True)
    for key, details in SYSTEMS.items():
        accent = details[3]
        manufacturer_logo = logos["manufacturers"].get(details[1])
        platform_logo = logos["platforms"].get(key)
        def logo_variables(prefix, entry):
            path = '${themePath}/assets/logos/' + entry['file'] if entry else '${themePath}/assets/ui/white.svg'
            return (f'        <{prefix}Logo>{path}</{prefix}Logo>\n'
                    f'        <{prefix}LogoVisible>{str(bool(entry)).lower()}</{prefix}LogoVisible>\n'
                    f'        <{prefix}TextVisible>{str(not entry).lower()}</{prefix}TextVisible>\n')
        (ROOT / "palettes" / (key + ".xml")).write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<theme>\n    <formatVersion>7</formatVersion>\n'
            '    <variables>\n'
            f'        <accent>{accent}FF</accent>\n'
            f'        <selectionAccent>{selection_accent(accent)}FF</selectionAccent>\n'
            f'        <accentInk>{foreground(accent)}FF</accentInk>\n'
            f'        <accentWash>{"".join(f"{c:02X}" for c in tint(accent, .18))}FF</accentWash>\n'
            f'        <manufacturer>{escape(details[1])}</manufacturer>\n'
            f'        <hardwareYear>{escape(details[2])}</hardwareYear>\n'
            + logo_variables('manufacturer', manufacturer_logo)
            + logo_variables('platform', platform_logo)
            +
            f'        <systemIcon>${{themePath}}/assets/systems/{key}.png</systemIcon>\n'
            f'        <systemCard>${{themePath}}/assets/cards/{key}.png</systemCard>\n'
            f'        <systemHero>${{themePath}}/assets/heroes/{key}.png</systemHero>\n'
            '    </variables>\n</theme>\n'
        )
    (ROOT / "platforms.json").write_text(json.dumps({key: dict(zip(["title", "manufacturer", "year", "accent"], value)) for key, value in SYSTEMS.items()}, indent=2) + "\n")
    if "--palettes-only" in sys.argv:
        print(f"Built {len(SYSTEMS)} distinct palettes.")
        return
    for key, details in SYSTEMS.items():
        source = ROOT / "assets/systems" / (key + ".png")
        with Image.open(source) as hardware:
            make_art(key, details, hardware.convert("RGBA"))
    make_grid()
    print(f"Built {len(SYSTEMS)} hero panels and {len(SYSTEMS)} platform cards.")


if __name__ == "__main__":
    main()
