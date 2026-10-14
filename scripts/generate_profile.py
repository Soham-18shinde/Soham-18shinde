#!/usr/bin/env python3
"""Generate this GitHub profile's SVG artwork from GitHub's public profile data."""
import json, os, urllib.request, xml.sax.saxutils as xu
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOGIN = os.getenv("GH_LOGIN", "Soham-18shinde")
TOKEN = os.getenv("GITHUB_TOKEN", "")
ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "assets"
RAMP = " .:-=+*#%@"
W = 620
QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount date weekday } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      nodes {
        primaryLanguage { name }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""

def esc(v):
    return xu.escape(str(v))

def api(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)

def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8")
    print("updated", path.relative_to(ROOT))

def begin_svg(width, height):
    css = """.ink{fill:#57606a}.bright{fill:#24292f}.muted{fill:#6e7781}.line{stroke:#d0d7de}
@media(prefers-color-scheme:dark){.ink{fill:#c9d1d9}.bright{fill:#f0f6fc}.muted{fill:#8b949e}.line{stroke:#30363d}}"""
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"><style>{css}</style>']

def label(text, x, y, size=12, cls="ink", delay="0s", weight="400", anchor="start"):
    return (f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" class="{cls}" text-anchor="{anchor}" opacity="0">'
            f'<set attributeName="opacity" to="1" begin="{delay}" fill="freeze"/>{esc(text)}</text>')

def portrait():
    # Use the current GitHub avatar as input so no third-party image host is required.
    profile = api(f"https://api.github.com/users/{LOGIN}", headers={"User-Agent": "profile-graphics"})
    req = urllib.request.Request(profile["avatar_url"], headers={"User-Agent": "profile-graphics"})
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
    try:
        from PIL import Image, ImageEnhance, ImageOps
        import io
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        side = min(image.size)
        left, top = (image.width-side)//2, (image.height-side)//2
        image = image.crop((left, top, left+side, top+side)).resize((270, 270), Image.Resampling.LANCZOS)
        # The profile photo has a deep-blue studio background. Key out blue-ish
        # background pixels so the character ramp describes the person, not the backdrop.
        px = image.load()
        for yy in range(image.height):
            for xx in range(image.width):
                red, green, blue = px[xx, yy]
                if blue > red * 1.13 and blue > green * 1.04 and blue < 155 and blue - red > 7:
                    px[xx, yy] = (255, 255, 255)
        image = ImageOps.autocontrast(image.convert("L"))
        image = ImageEnhance.Contrast(image).enhance(1.45).resize((90, 42), Image.Resampling.LANCZOS)
    except ImportError as err:
        raise SystemExit("Pillow is required. Install it with: pip install pillow") from err
    lines = []
    for y in range(image.height):
        line = "".join(RAMP[min(len(RAMP)-1, int((255-image.getpixel((x,y)))/256*len(RAMP)))] for x in range(image.width))
        lines.append(line.rstrip())
    while lines and not lines[0].strip(): lines.pop(0)
    while lines and not lines[-1].strip(): lines.pop()
    # Generate a GIF because GitHub's README image renderer may not reliably play
    # SVG SMIL animations. Each frame reveals one additional ASCII line.
    from PIL import Image, ImageDraw, ImageFont
    import io
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
    try:
        font = ImageFont.truetype(font_path, 10)
    except OSError:
        font = ImageFont.load_default()
    char_w = 6.1
    line_h = 11
    pad = 12
    width = int(90 * char_w + pad * 2)
    height = len(lines) * line_h + pad * 2
    frames = []
    for visible in range(1, len(lines) + 1):
        frame = Image.new("RGB", (width, height), (13, 17, 23))
        draw = ImageDraw.Draw(frame)
        for row, line in enumerate(lines[:visible]):
            draw.text((pad, pad + row * line_h), line, font=font, fill=(87, 211, 145))
        frames.append(frame)
    if frames:
        frames[0].save(ASSET / "ascii-profile-once.gif", save_all=True,
                       append_images=frames[1:], duration=55,
                       optimize=False, disposal=2)
        # Keep the SVG source available as a non-animated alternative.
    cw, lh, pad_svg = 7.8, 15, 12
    out = begin_svg(90*cw+pad_svg*2, len(lines)*lh+pad_svg*2)
    for i, line in enumerate(lines):
        out.append(f'<text x="{pad_svg}" y="{pad_svg+i*lh+11}" font-size="13" xml:space="preserve" class="ink">{esc(line)}</text>')
    out.append("</svg>")
    write(ASSET / "ascii-profile.svg", "".join(out))

def stats():
    if not TOKEN:
        raise SystemExit("GITHUB_TOKEN is not set")
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=364)
    payload = json.dumps({"query": QUERY, "variables": {
        "login": LOGIN, "from": f"{start.isoformat()}T00:00:00Z",
        "to": f"{today.isoformat()}T23:59:59Z"}}).encode()
    data = api("https://api.github.com/graphql", payload, {
        "Authorization": f"bearer {TOKEN}", "Content-Type": "application/json",
        "User-Agent": f"{LOGIN}-profile-graphics"})
    if data.get("errors"):
        raise SystemExit("GitHub GraphQL error: " + str(data["errors"]))
    user = (data.get("data") or {}).get("user")
    if not user:
        raise SystemExit("GitHub user was not found: " + LOGIN)
    cal = user["contributionsCollection"]["contributionCalendar"]
    weeks, days = cal["weeks"], [d for week in cal["weeks"] for d in week["contributionDays"]]
    weekly = [sum(d["contributionCount"] for d in week["contributionDays"]) for week in weeks]
    active = sum(d["contributionCount"] > 0 for d in days)
    recent = days[:-1] if days and not days[-1]["contributionCount"] else days
    current = 0
    for day in reversed(recent):
        if not day["contributionCount"]: break
        current += 1
    longest = run = 0
    for day in days:
        run = run + 1 if day["contributionCount"] else 0
        longest = max(longest, run)
    sizes, repos = {}, {}
    for repo in user["repositories"]["nodes"]:
        main = repo.get("primaryLanguage")
        if main: repos[main["name"]] = repos.get(main["name"], 0) + 1
        for edge in (repo.get("languages") or {}).get("edges", []):
            name = edge["node"]["name"]
            sizes[name] = sizes.get(name, 0) + edge["size"]
    by_bytes = sorted(sizes.items(), key=lambda p: (-p[1],p[0]))[:5]
    by_repos = sorted(repos.items(), key=lambda p: (-p[1],p[0]))[:5]

    out = begin_svg(W, 145)
    out.append(label(f"{cal['totalContributions']:,}", 0, 52, 47, "bright", ".1s", "600"))
    out.append(label("contributions in the last year", 2, 75, 12, "muted", ".2s"))
    out.append(label(active, W, 28, 20, "bright", ".3s", "600", "end"))
    out.append(label("active days", W, 47, 10, "muted", ".4s", anchor="end"))
    peak = max(weekly, default=0) or 1
    coords = [(i*W/max(1,len(weekly)-1), 133-v/peak*42) for i,v in enumerate(weekly)]
    path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x,y in coords)
    out.append(f'<path d="{path}" class="line" stroke-width="1.8" stroke-linejoin="round"><animate attributeName="stroke-dasharray" values="0 3000;3000 0" dur="2s" fill="freeze"/></path></svg>')
    write(ROOT/"stats.svg", "".join(out))

    out = begin_svg(W, 86)
    out.append('<line x1="310" y1="10" x2="310" y2="76" class="line"/>')
    out.append(label(current, 34, 39, 31, "bright", ".1s", "600"))
    out.append(label("current streak (days)", 34, 60, 11, "muted", ".2s"))
    out.append(label(longest, 342, 39, 31, "bright", ".3s", "600"))
    out.append(label("longest streak (days)", 342, 60, 11, "muted", ".4s"))
    out.append("</svg>")
    write(ROOT/"streak.svg", "".join(out))

    out = begin_svg(W, 145)
    for gi,(title, entries, x) in enumerate((("BY BYTES",by_bytes,0),("BY REPOS",by_repos,326))):
        out.append(label(title,x,12,9,"muted",f"{.1+gi*.15}s","600"))
        maxval = max((v for _,v in entries),default=1) or 1
        for row,(name,value) in enumerate(entries):
            y=34+row*22; delay=f"{.2+row*.05+gi*.1}s"
            out.append(label(name.lower(),x,y,10,"bright",delay))
            out.append(label(f"{value/maxval*100:.0f}%",x+105,y,10,"muted",delay))
            out.append(f'<rect x="{x+122}" y="{y-9}" width="170" height="7" rx="3" fill="#8c959f" opacity=".18"/>')
            out.append(f'<rect x="{x+122}" y="{y-9}" width="{170*value/maxval:.1f}" height="7" rx="3" class="ink"><animate attributeName="width" from="0" to="{170*value/maxval:.1f}" dur=".8s" begin="{delay}" fill="freeze"/></rect>')
    out.append("</svg>")
    write(ROOT/"langs.svg","".join(out))

    out = begin_svg(W, 138)
    out.append(label("THE YEAR",0,13,9,"muted",".1s","600"))
    out.append(label(f"{active} active days",0,31,12,"bright",".2s"))
    char_weeks=[]
    for week in weeks:
        mapping={d["weekday"]:d for d in week["contributionDays"]}
        chars=[]
        for weekday in range(7):
            n=mapping.get(weekday,{}).get("contributionCount",0)
            idx=0 if n==0 else 1 if n<2 else 2 if n<5 else 3 if n<10 else 4
            chars.append(" " if idx==0 else RAMP[idx])
        char_weeks.append(chars)
    for weekday in range(7):
        line="".join(char_weeks[w][weekday] for w in range(len(char_weeks)))
        out.append(f'<text x="0" y="{48+weekday*11.2}" font-size="10" class="ink" xml:space="preserve">{esc(line)}<animate attributeName="opacity" from="0" to="1" dur=".6s" begin="{weekday*.08:.2f}s" fill="freeze"/></text>')
    out.append("</svg>")
    write(ROOT/"year.svg","".join(out))

def heading(word):
    out=begin_svg(W,26)
    out.append(f'<text x="0" y="18" font-size="16" font-weight="600" class="bright">{esc(word)}<animate attributeName="opacity" from="0" to="1" dur=".6s" fill="freeze"/></text>')
    out.append(f'<line x1="{len(word)*9.6+12:.1f}" y1="12.5" x2="{W}" y2="12.5" class="line"/></svg>')
    write(ROOT/f"hd-{word.replace(' ','-')}.svg","".join(out))

def main():
    portrait()
    s=stats()
    for word in ("about","stack","projects","stats","about this page"):
        heading(word)

if __name__ == "__main__":
    main()
