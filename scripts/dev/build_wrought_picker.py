"""Build the picker: one local HTML over every frame of the night run, with both reads shown.

Each card carries the frame, the gate verdict, the advisory numbers, and two marks -- C for the
frame Claude's audit would keep, J for the frame Jarvis kept -- with Jarvis's one-line note. The
owner toggles his own keep on each card; picks persist in the browser (localStorage) and export as
`<root>/<race>_woman/NNN` lines, the unambiguous form `collect_wrought_picks.py` reads.

WHAT "C" MEANS, stated so it is not mistaken for an eye. For the six races rendered with the
identity axis, Claude's mark is the audit's rule -- gate WROUGHT, no speckle flag, face texture
below 0.60 (dragonborn exempt: scales inflate it), not on the reject lists in ASSESSMENT_CLAUDE.md.
For orc, goblin and dark elf -- one face a hundred times -- it is a curated dozen each, chosen from
the sheets for different framings, tiers and lights, as the assessment recommends.
Jarvis's mark is a genuine per-frame verdict from the vision model (`_jarvis_<race>.json`).

Thumbnails are written beside the page (720 px JPEG) so nine hundred frames scroll; a click opens
the full PNG. Everything is relative to the page, so the folder can be zipped and opened anywhere.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_wrought_night import records_for, SPECKLE_FLAG, SPECKLE_RELATIVE  # noqa: E402

ROOTS = [REPO / "runtime/wrought_night", REPO / "runtime/wrought_night_b"]
AUDIT = REPO / "runtime/wrought_night/_audit"
OUT = AUDIT / "picker"
THUMB_W = 720

# Frames Claude's assessment rejects on sight (artifact / blowout), by race.
CLAUDE_REJECTS = {
    "goblin": {20, 25, 29, 16, 45, 54, 99, 95}, "dwarf": {20, 22}, "orc": {23, 93, 97},
    "high_elf": {4}, "beastfolk": {19}, "wood_elf": {0, 15},
}
FACE_EXEMPT = {"dragonborn"}   # scales inside the face crop

# The three pre-identity-axis races are one face a hundred times. ASSESSMENT_CLAUDE.md says take
# them sparingly -- a dozen each, chosen for DIFFERENT frames (framing, tier, light) so the single
# face is diluted rather than reinforced. These are Claude's dozen from the sheets he read; for
# those races the C mark is this choice, not the rule.
CLAUDE_CURATED = {
    "orc": {1, 5, 7, 8, 40, 41, 44, 46, 48, 51, 56, 58},
    "dark_elf": {1, 3, 41, 42, 45, 47, 49, 52, 54, 57, 58, 59},
    "goblin": {21, 22, 24, 27, 28, 30, 31, 32, 33, 34, 36, 39},
}


def thumb(png: Path, dst: Path) -> None:
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(png).convert("RGB")
    im.thumbnail((THUMB_W, THUMB_W * 2))
    im.save(dst, "JPEG", quality=84, optimize=True)


def load_jarvis(race: str) -> dict[str, dict]:
    p = AUDIT / f"_jarvis_{race}.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("verdicts", {})


# --- v2 records (Task 17A) ------------------------------------------------------------------
#
# v2 roots (`runtime/wrought_v2`, `runtime/wrought_v2_b`) hold no Jarvis verdicts and no
# Claude-curated lists yet -- those are v1-night-run artifacts. What the owner needs from the
# picker here is simpler: see the frame(s), the gate, and the advisory numbers, and star a pick.
V2_ROOTS = [REPO / "runtime/wrought_v2", REPO / "runtime/wrought_v2_b"]


def rows_for(root: Path) -> list[dict]:
    """One row per record under `root`, shaped for the picker card.

    This differs from `audit_wrought_night.records_for` on purpose: that function flattens a
    Lane-A pair into two entries (one per PNG) because its sheets are one-frame-per-cell. Here the
    owner picks or rejects an IDENTITY, not a half of one, so a Lane-A skin/suit pair stays ONE row
    with two thumbs and the pair's own advisory numbers (silhouette deltas, identity ncc).

    v1 records (no `lane` key) become `{"kind": "v1", "thumbs": [png], ...}` -- the flat record,
    unchanged, so a v1 root can be read by the same function. Lane B becomes
    `{"kind": <asset kind or "fit">, "thumbs": [png], ...}`.

    `export` is always the stem(s) `collect_wrought_picks.py` resolves: `<root>/<dir>/<stem>`, with
    `<stem>` taken from each PNG's own filename (never reconstructed from the index) -- a Lane-A
    row exports BOTH `NNN_skin` and, when it rendered, `NNN_suit`.
    """
    rows: list[dict] = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        for j in sorted(d.glob("[0-9][0-9][0-9].json")):
            rec = json.loads(j.read_text(encoding="utf-8"))
            lane = rec.get("lane")
            if lane == "a":
                files = rec.get("files") or {}
                skin_png = d / files["skin"] if files.get("skin") else None
                suit_png = d / files["suit"] if files.get("suit") else None
                # `export` is built from the SAME exists()-checked paths as `thumbs` below -- a
                # `files.suit` name recorded at write time but a PNG since gone (or never written
                # despite the key surviving) must not export a stem that isn't there to collect.
                skin_png = skin_png if skin_png and skin_png.exists() else None
                suit_png = suit_png if suit_png and suit_png.exists() else None
                export = [f"{root.name}/{d.name}/{p.stem}" for p in (skin_png, suit_png) if p is not None]
                measures_ = rec.get("measures") or {}
                rows.append({**rec, "kind": "a", "root": root.name, "dir": d.name,
                             "thumbs": [skin_png, suit_png],
                             "silhouette": measures_.get("silhouette"),
                             "identity": measures_.get("identity"),
                             "gate": rec.get("gate") or {}, "export": export})
            elif lane == "b":
                png = d / rec["file"] if rec.get("file") else None
                stem = png.stem if png is not None else j.stem
                rows.append({**rec, "kind": rec.get("kind", "fit"), "root": root.name, "dir": d.name,
                             "thumbs": [png if png is not None and png.exists() else None],
                             "export": [f"{root.name}/{d.name}/{stem}"]})
            else:
                png = j.with_suffix(".png")
                rows.append({**rec, "kind": "v1", "root": root.name, "dir": d.name,
                             "thumbs": [png if png.exists() else None],
                             "export": [f"{root.name}/{d.name}/{j.stem}"]})
    return rows


def v2_thumb(root_name: str, dir_name: str, png: Path | None) -> str | None:
    if png is None or not png.exists():
        return None
    dst = OUT / "thumbs" / f"{root_name}__{dir_name}__{png.stem}.jpg"
    thumb(png, dst)
    return f"thumbs/{dst.name}"


def v2_card(row: dict) -> dict:
    root, d, idx = row["root"], row["dir"], row.get("index", 0)
    card_id = f"{root}/{d}/{idx:03d}"
    if row["kind"] == "a":
        skin_png, suit_png = row["thumbs"]
        sil = row.get("silhouette") or {}
        ident = row.get("identity") or {}
        gate = row.get("gate") or {}
        gate_skin = (gate.get("skin") or {}).get("gate")
        gate_suit = (gate.get("suit") or {}).get("gate")
        overall = "WROUGHT" if gate_skin == "WROUGHT" and gate_suit in ("WROUGHT", None) else "OFF-STYLE"
        return {"id": card_id, "kind": "a", "root": root, "dir": d, "idx": idx, "export": row["export"],
                "thumbs": [v2_thumb(root, d, skin_png), v2_thumb(root, d, suit_png)],
                "fulls": [f"../../../{root}/{d}/{skin_png.name}" if skin_png else None,
                          f"../../../{root}/{d}/{suit_png.name}" if suit_png else None],
                "gate_skin": gate_skin, "gate_suit": gate_suit, "gate": overall,
                "waist_delta": sil.get("waist_delta_px"), "hip_delta": sil.get("hip_delta_px"),
                "sil_ok": sil.get("ok"), "ncc": ident.get("ncc")}
    png = row["thumbs"][0]
    return {"id": card_id, "kind": row["kind"], "root": root, "dir": d, "idx": idx, "export": row["export"],
            "thumbs": [v2_thumb(root, d, png)],
            "fulls": [f"../../../{root}/{d}/{png.name}" if png else None],
            "caption": row.get("caption") or "", "gate": row.get("gate")}


def v2_sections() -> tuple[list[dict], dict]:
    merged: dict[str, list[dict]] = {}
    for root in V2_ROOTS:
        if not root.exists():
            continue
        for row in rows_for(root):
            merged.setdefault(row["dir"], []).extend([row])
    sections = []
    frames = 0
    for dir_name, rows in sorted(merged.items()):
        rows.sort(key=lambda r: (r["root"], r.get("index", 0)))
        cards = [v2_card(r) for r in rows]
        frames += len(cards)
        sections.append({"dir": dir_name, "cards": cards})
    return sections, {"frames": frames, "dirs": len(sections)}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    merged: dict[str, list[dict]] = {}
    for root in ROOTS:
        for race, recs in records_for(root).items():
            merged.setdefault(race, []).extend(recs)

    races_js = []
    totals = {"frames": 0, "gate": 0, "claude": 0, "jarvis": 0, "both": 0}
    for race, recs in sorted(merged.items()):
        recs.sort(key=lambda r: (r["_root"], r["index"]))
        spk = sorted(r.get("_speckle", 0) for r in recs)
        spk_limit = max(SPECKLE_FLAG, SPECKLE_RELATIVE * (spk[len(spk) // 2] if spk else 0))
        jv = load_jarvis(race)
        cards = []
        for r in recs:
            root, idx = r["_root"], r["index"]
            rel_png = f"../../../{root}/{race}_woman/{idx:03d}.png"
            th = OUT / "thumbs" / f"{root}__{race}_{idx:03d}.jpg"
            thumb(r["_png"], th)
            m = r.get("metrics", {})
            face = m.get("face_fine_over_meso")
            speckled = r.get("_speckle", 0) > spk_limit
            gate_ok = r.get("gate") == "WROUGHT"
            if race in CLAUDE_CURATED:
                claude = gate_ok and idx in CLAUDE_CURATED[race]
            else:
                claude = (gate_ok and not speckled and idx not in CLAUDE_REJECTS.get(race, set())
                          and (race in FACE_EXEMPT or face is None or face <= 0.60))
            j = jv.get(f"{root}/{idx:03d}") or jv.get(f"{idx:03d}") or {}
            jarvis_keep = j.get("keep") is True
            v = r["variation"]
            cards.append({
                "id": f"{root}/{race}_woman/{idx:03d}", "root": root, "dir": f"{race}_woman", "idx": idx,
                "thumb": f"thumbs/{root}__{race}_{idx:03d}.jpg", "full": rel_png,
                "gate": r.get("gate"), "failed": r.get("failed", []),
                "face": face, "speckle": round(r.get("_speckle", 0), 3), "speckled": speckled,
                "claude": claude, "jarvis": jarvis_keep,
                "jscore": j.get("score"), "jstyle": j.get("style"), "jnote": j.get("note") or "",
                "jfails": j.get("fails") or [],
                "age": v.get("age", ""), "build": v.get("build", ""), "tier": v.get("tier", ""),
                "skin": v.get("skin", ""), "hair": v.get("hair", ""), "framing": v.get("framing", ""),
                "lineage": (v.get("lineage") or "").split(" ")[0],
            })
            totals["frames"] += 1; totals["gate"] += gate_ok; totals["claude"] += claude
            totals["jarvis"] += jarvis_keep; totals["both"] += (claude and jarvis_keep)
        races_js.append({"race": race, "cards": cards,
                         "counts": {"frames": len(cards), "gate": sum(c["gate"] == "WROUGHT" for c in cards),
                                    "claude": sum(c["claude"] for c in cards),
                                    "jarvis": sum(c["jarvis"] for c in cards),
                                    "both": sum(c["claude"] and c["jarvis"] for c in cards)}})

    v2_secs, totals2 = v2_sections()

    data = json.dumps(races_js).replace("</", "<\\/")
    data2 = json.dumps(v2_secs).replace("</", "<\\/")
    page = (TEMPLATE.replace("__DATA__", data).replace("__TOTALS__", json.dumps(totals))
            .replace("__DATA2__", data2).replace("__TOTALS2__", json.dumps(totals2)))
    (OUT / "index.html").write_text(page, encoding="utf-8")
    print(f"{totals} -> {OUT / 'index.html'}  |  v2: {totals2}")
    return 0


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Wrought night picker</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#141416;--card:#1c1c20;--line:#2a2a30;--ink:#e6e6ea;--mute:#9a9aa4;--ok:#8fd69a;--bad:#e6a878;--c:#7db8ff;--j:#f0c36a;--own:#c29cff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.4 Segoe UI,system-ui,sans-serif}
header{position:sticky;top:0;z-index:5;background:#101012;border-bottom:1px solid var(--line);padding:10px 16px;display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center}
header h1{font-size:16px;margin:0 12px 0 0;font-weight:600}
header button,header select{background:#232328;color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:5px 10px;cursor:pointer}
header button.on{outline:2px solid var(--c)}
.legend span{display:inline-block;margin-right:12px;color:var(--mute)}
.badge{display:inline-block;padding:1px 7px;border-radius:10px;font-size:12px;font-weight:600;margin-right:4px}
.badge.c{background:#1d3a5c;color:var(--c)}.badge.j{background:#4a3a12;color:var(--j)}.badge.own{background:#3a2a5c;color:var(--own)}
.badge.gate-ok{background:#1f3a24;color:var(--ok)}.badge.gate-bad{background:#4a2c1c;color:var(--bad)}.badge.spk{background:#5a1f2a;color:#ff9aa8}
.badge.kind{background:#232840;color:#9fd0ff;text-transform:uppercase}
section{padding:8px 16px 24px}section h2{margin:18px 0 8px;font-size:18px}
section h2 small{color:var(--mute);font-weight:400;font-size:13px;margin-left:10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden;position:relative}
.card.own{border-color:var(--own);box-shadow:0 0 0 1px var(--own) inset}
.card img{display:block;width:100%;aspect-ratio:2/3;object-fit:cover;background:#000;cursor:zoom-in}
.pair{display:flex;gap:1px;background:var(--line)}
.pair img{width:50%}
.card .meta{padding:7px 9px;font-size:12px;color:var(--mute)}
.card .meta .row{display:flex;justify-content:space-between;align-items:center;gap:6px;margin-bottom:4px}
.card .idx{color:var(--ink);font-weight:600;font-size:13px}
.card .note{color:#c9c9d0;font-style:italic;margin-top:4px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.card label{position:absolute;top:8px;right:8px;background:rgba(0,0,0,.6);border-radius:6px;padding:4px 8px;cursor:pointer;color:var(--ink)}
.card input{transform:scale(1.2);margin-right:4px}
#lightbox{position:fixed;inset:0;background:rgba(0,0,0,.92);display:none;align-items:center;justify-content:center;z-index:9}
#lightbox img{max-width:96vw;max-height:96vh}
#exportbox{position:fixed;right:16px;bottom:16px;width:min(560px,92vw);background:#101012;border:1px solid var(--line);border-radius:8px;padding:10px;display:none;z-index:6}
#exportbox textarea{width:100%;height:200px;background:#0b0b0d;color:var(--ink);border:1px solid var(--line);font:12px monospace}
.hidden{display:none!important}
</style></head><body>
<header>
  <h1>Wrought night picker</h1>
  <span id="totals" class="legend"></span>
  <span class="legend" title="C = rule for the six identity-axis races (gate, no speckle, face in band); a curated dozen for orc / goblin / dark elf, which are one face a hundred times. J = Jarvis's per-frame verdict (gemma vision, PICK.md + 002 same-game test)."><span class="badge c">C</span>Claude keeps <span class="badge j">J</span>Jarvis keeps <span class="badge own">★</span>your pick</span>
  <span>Show:</span>
  <button data-f="v2">v2 only</button><button data-f="all" class="on">all</button><button data-f="both">C + J</button><button data-f="claude">C</button><button data-f="jarvis">J</button><button data-f="own">★ mine</button><button data-f="fail">gate fail</button><button data-f="spk">speckle</button>
  <select id="race"><option value="">every race</option></select>
  <button id="export">Export picks</button><button id="clear">Clear my picks</button>
</header>
<div id="sections"></div>
<div id="lightbox"><img alt=""></div>
<div id="exportbox"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px"><b id="exportcount"></b><span><button id="copy">Copy</button> <button id="closex">Close</button></span></div><textarea id="exporttext" readonly></textarea><div style="color:#9a9aa4;font-size:12px;margin-top:6px">Save as picks.txt → <code>collect_wrought_picks.py picks.txt</code></div></div>
<script>
const DATA=__DATA__, TOTALS=__TOTALS__, DATA2=__DATA2__, TOTALS2=__TOTALS2__, KEY="wrought_night_picks_v1";
let picks=new Set(); try{picks=new Set(JSON.parse(localStorage.getItem(KEY)||"[]"))}catch(e){}
function save(){try{localStorage.setItem(KEY,JSON.stringify([...picks]))}catch(e){}}
// The owner is picking v2 now: land on the v2 rows when any exist (the night frames are one click away).
let filter=(typeof TOTALS2!=="undefined"&&TOTALS2.frames)?"v2":"all", raceSel="";
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
// EXPORT_MAP: pick id -> the export line(s) it stands for. v1 ids ARE their own export line
// (one frame, one stem); a v2 Lane-A id stands for a PAIR and expands to both stems on export.
const EXPORT_MAP={};
$("#totals").textContent=`${TOTALS.frames} frames · gate ${TOTALS.gate} · C ${TOTALS.claude} · J ${TOTALS.jarvis} · both ${TOTALS.both}` +
  (TOTALS2.frames?` — v2: ${TOTALS2.frames} rows across ${TOTALS2.dirs} dirs`:"");
for(const r of DATA){const o=document.createElement("option");o.value=r.race;o.textContent=r.race.replace("_"," ");$("#race").appendChild(o)}
function card(c){
  const gate=c.gate==="WROUGHT"?`<span class="badge gate-ok">gate</span>`:`<span class="badge gate-bad" title="${c.failed.join(", ")}">${c.failed.join(",")||"off"}</span>`;
  const spk=c.speckled?`<span class="badge spk" title="speckle ${c.speckle}">speckle</span>`:"";
  const face=c.face==null?"":` · face ${c.face}`;
  const jinfo=c.jstyle?` · J: ${c.jstyle}${c.jscore?" "+c.jscore+"/10":""}`:"";
  return `<div class="card${picks.has(c.id)?" own":""}" data-id="${c.id}" data-root="${c.root}" data-dir="${c.dir}" data-c="${c.claude}" data-j="${c.jarvis}" data-gate="${c.gate}" data-spk="${c.speckled}">
    <img loading="lazy" src="${c.thumb}" data-full="${c.full}" alt="${c.id}">
    <label><input type="checkbox" ${picks.has(c.id)?"checked":""}> ★</label>
    <div class="meta"><div class="row"><span class="idx">${c.idx.toString().padStart(3,"0")} <span style="color:#666">${c.root.endsWith("_b")?"5090":"node"}</span></span><span>${c.claude?'<span class="badge c">C</span>':""}${c.jarvis?'<span class="badge j">J</span>':""}${gate}${spk}</span></div>
    <div>${c.lineage?c.lineage+" · ":""}${c.tier} · ${c.framing.split(",")[0]}${face}${jinfo}</div>
    <div>${c.skin}${c.hair?" · "+c.hair.split(", ").slice(-1)[0]:""} · ${c.age.split(",")[0]}</div>
    ${c.jnote?`<div class="note" title="${c.jnote.replace(/"/g,"&quot;")}">J: ${c.jnote}</div>`:""}</div></div>`}
// A v2 Lane-A row is a skin/suit PAIR judged as one identity: two thumbs side by side, both gate
// verdicts, and the pair's own advisory numbers (silhouette deltas, identity ncc) -- not per-frame
// Claude/Jarvis marks, which don't exist yet for v2. Everything else (Lane B: outfit/asset/fit) is
// one thumb with its kind as the badge.
function cardV2(c){
  const gateBadge=(g)=>g==="WROUGHT"?`<span class="badge gate-ok">${g}</span>`:g?`<span class="badge gate-bad">${g}</span>`:"";
  if(c.kind==="a"){
    const sil=c.sil_ok===true?`<span class="badge gate-ok">sil ok</span>`:c.sil_ok===false?`<span class="badge gate-bad">sil</span>`:"";
    return `<div class="card${picks.has(c.id)?" own":""}" data-id="${c.id}" data-root="${c.root}" data-dir="${c.dir}" data-c="false" data-j="false" data-gate="${c.gate}" data-spk="false">
    <div class="pair"><img loading="lazy" src="${c.thumbs[0]||""}" data-full="${c.fulls[0]||""}" alt="skin"><img loading="lazy" src="${c.thumbs[1]||""}" data-full="${c.fulls[1]||""}" alt="suit"></div>
    <label><input type="checkbox" ${picks.has(c.id)?"checked":""}> ★</label>
    <div class="meta"><div class="row"><span class="idx">${c.idx.toString().padStart(3,"0")} <span class="badge kind">pair</span></span><span>${gateBadge(c.gate_skin)}${gateBadge(c.gate_suit)}${sil}</span></div>
    <div>waist Δ${c.waist_delta??"-"} · hip Δ${c.hip_delta??"-"} · identity ncc ${c.ncc??"-"}</div></div></div>`;
  }
  return `<div class="card${picks.has(c.id)?" own":""}" data-id="${c.id}" data-root="${c.root}" data-dir="${c.dir}" data-c="false" data-j="false" data-gate="${c.gate||""}" data-spk="false">
    <img loading="lazy" src="${c.thumbs[0]||""}" data-full="${c.fulls[0]||""}" alt="${c.kind}">
    <label><input type="checkbox" ${picks.has(c.id)?"checked":""}> ★</label>
    <div class="meta"><div class="row"><span class="idx">${c.idx.toString().padStart(3,"0")}</span><span><span class="badge kind">${c.kind}</span>${gateBadge(c.gate)}</span></div>
    ${c.caption?`<div class="note" title="${c.caption.replace(/"/g,"&quot;")}">${c.caption}</div>`:""}</div></div>`;
}
function render(){
  const host=$("#sections"); host.innerHTML="";
  for(const r of DATA){ if(raceSel&&r.race!==raceSel) continue;
    const k=r.counts; const sec=document.createElement("section"); sec.className="v1";
    sec.innerHTML=`<h2>${r.race.replace("_"," ")}<small>${k.frames} frames · gate ${k.gate} · C ${k.claude} · J ${k.jarvis} · both ${k.both} · ★ <span class="own-count" data-race="${r.race}">0</span></small></h2><div class="grid">${r.cards.map(card).join("")}</div>`;
    host.appendChild(sec);
    for(const c of r.cards) EXPORT_MAP[c.id]=[c.id]}
  for(const r of DATA2){
    const sec=document.createElement("section"); sec.className="v2";
    sec.innerHTML=`<h2>${r.dir.replace("_"," ")}<small>${r.cards.length} rows · v2 · ★ <span class="own-count2" data-dir="${r.dir}">0</span></small></h2><div class="grid">${r.cards.map(cardV2).join("")}</div>`;
    host.appendChild(sec);
    for(const c of r.cards) EXPORT_MAP[c.id]=c.export}
  applyFilter(); ownCounts();
}
function applyFilter(){ for(const s of $$("section.v1")) s.classList.toggle("hidden",filter==="v2");
  for(const el of $$(".card")){ const c=el.dataset.c==="true", j=el.dataset.j==="true", own=picks.has(el.dataset.id);
  const show=filter==="all"||(filter==="both"&&c&&j)||(filter==="claude"&&c)||(filter==="jarvis"&&j)||(filter==="own"&&own)||(filter==="fail"&&el.dataset.gate!=="WROUGHT")||(filter==="spk"&&el.dataset.spk==="true")||(filter==="v2"&&el.closest("section.v2")!==null);
  el.classList.toggle("hidden",!show)}}
// Anchored on root+dir, not a bare substring: an unanchored `/${dir}/` match let a v2 pick
// (e.g. "wrought_v2/beastfolk_woman/000_skin") also satisfy the v1 "beastfolk" section's filter,
// because v1 Lane-A dirs and v2 Lane-A dirs both end in "_woman" -- the same race name landed in
// both a night root and a v2 root double-counted its stars in both sections. Anchors are read off
// the section's OWN rendered cards (their real `data-root`/`data-dir`), so a section only ever
// matches the exact root/dir pairs it actually contains.
function countOwn(sec){
  const anchors=new Set([...sec.querySelectorAll(".card")].map(el=>`${el.dataset.root}/${el.dataset.dir}/`));
  let n=0; for(const id of picks){ for(const a of anchors){ if(id.startsWith(a)){ n++; break } } }
  return n;
}
function ownCounts(){
  for(const el of $$(".own-count")) el.textContent=countOwn(el.closest("section"));
  for(const el of $$(".own-count2")) el.textContent=countOwn(el.closest("section"));
  $("#export").textContent=`Export picks (${picks.size})`;
}
document.addEventListener("change",e=>{ if(e.target.type!=="checkbox")return; const el=e.target.closest(".card"); const id=el.dataset.id;
  e.target.checked?picks.add(id):picks.delete(id); el.classList.toggle("own",e.target.checked); save(); ownCounts(); if(filter==="own")applyFilter()});
document.addEventListener("click",e=>{ if(e.target.tagName==="IMG"&&e.target.dataset.full){ $("#lightbox img").src=e.target.dataset.full; $("#lightbox").style.display="flex"} });
$("#lightbox").addEventListener("click",()=>{$("#lightbox").style.display="none";$("#lightbox img").src=""});
for(const x of $$("header button[data-f]")) x.classList.toggle("on",x.dataset.f===filter);
for(const b of $$("header button[data-f]")) b.addEventListener("click",()=>{ filter=b.dataset.f; for(const x of $$("header button[data-f]")) x.classList.toggle("on",x===b); applyFilter()});
$("#race").addEventListener("change",e=>{raceSel=e.target.value;render()});
$("#export").addEventListener("click",()=>{ const lines=[...picks].flatMap(id=>EXPORT_MAP[id]||[id]).sort(); $("#exporttext").value=lines.join("\n"); $("#exportcount").textContent=`${lines.length} picks`; $("#exportbox").style.display="block"});
$("#copy").addEventListener("click",()=>{ $("#exporttext").select(); document.execCommand("copy") });
$("#closex").addEventListener("click",()=>{$("#exportbox").style.display="none"});
$("#clear").addEventListener("click",()=>{ if(confirm("Clear all your picks?")){picks.clear();save();render()} });
render();
</script></body></html>
"""

if __name__ == "__main__":
    raise SystemExit(main())
