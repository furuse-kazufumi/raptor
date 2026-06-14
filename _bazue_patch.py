#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Add Snack Bus Eko (スナックバス江) manga panels to a Qiita article and PATCH it.

Single self-contained script (steps 1-6 of the task).
"""
import io
import json
import sys
import urllib.request
import urllib.error

# Force UTF-8 stdout regardless of cp932 console.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ITEM_ID = "24ac90fb12c4e332d2b5"
API = f"https://qiita.com/api/v2/items/{ITEM_ID}"
RAW_BASE = (
    "https://raw.githubusercontent.com/furuse-kazufumi/fullsense/"
    "main/docs/articles/assets/bazue_all/"
)

# ----------------------------------------------------------------------------
# 1. token
# ----------------------------------------------------------------------------
sys.path.insert(0, r"D:/projects/fullsense/tools")
from qiita_public_post import get_token  # noqa: E402

tok = get_token()
if not tok:
    print("NOTE: no Qiita token", file=sys.stderr)
    sys.exit(2)


def http_json(url, method="GET", payload=None):
    headers = {"Authorization": "Bearer " + tok}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as r:
        return r.status, json.load(r)


def raw_ok(panel):
    """Return True if the raw image for NNN returns HTTP 200."""
    url = RAW_BASE + panel + ".jpg"
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req) as r:
            return r.status == 200, url
    except urllib.error.HTTPError as e:
        return False, f"{url} HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return False, f"{url} {e}"


# ----------------------------------------------------------------------------
# 2. GET current article
# ----------------------------------------------------------------------------
status, item = http_json(API, "GET")
body = item["body"]
title = item["title"]
tags = [{"name": t["name"], "versions": t.get("versions", [])} for t in item["tags"]]
private = item["private"]
print(f"GET status={status} bodylen={len(body)} private={private}")

# ----------------------------------------------------------------------------
# 3-4. choose panels matching the article theme + build insert blocks
#   This article = 15h marathon, 進化型 GA(個体群進化), 全編 honest disclosure。
#   196 = 「嘘は良くない」honest/over-claim 戒め  -> honest disclosure 見出し直後
#   069 = アフターマン(空想進化)・進化系の挿絵    -> 進化 GA メタファ直後
# ----------------------------------------------------------------------------
def block(panel, alt, line):
    img = f"![{alt}]({RAW_BASE}{panel}.jpg)"
    return f"\n{img}\n> 🗒️ *{line}*（© Forbidden shibukawa / SHUEISHA・スナックバス江）\n"


insertions = [
    {
        # honest disclosure 見出し直後（記事最大のテーマ＝誇張しない誠実さ）
        "panel": "196",
        "anchor": "### honest disclosure (重要)\n",
        "after": True,
        "block": block(
            "196",
            "「嘘は良くない」と諭すスナックバス江のワンシーン",
            "「嘘は良くない」— mock の 5,389,354 tok/s を「速い」と言わないのが honest disclosure の核。",
        ),
    },
    {
        # 進化メタファ（歩いてないロボット5体を並べる）直後＝進化型 GA の挿絵
        "panel": "069",
        "anchor": "ロボット歩行進化の比喩で言うと: **「歩いてないロボット 5 体を同じトラックに\n並べる」段階**. 走らせるのは 2 日強の追加作業.\n",
        "after": True,
        "block": block(
            "069",
            "空想進化（アフターマン）的な進化系の挿絵",
            "進化型 GA の個体群＝まだ走らないロボット 5 体。選択圧をかければ「歩く個体」が残っていく。",
        ),
    },
]

# ----------------------------------------------------------------------------
# verify raw 200 BEFORE editing; skip a panel if not reachable
# ----------------------------------------------------------------------------
used_panels = []
notes = []
for ins in insertions:
    ok, info = raw_ok(ins["panel"])
    print(f"raw {ins['panel']}: ok={ok} {info}")
    if not ok:
        notes.append(f"panel {ins['panel']} raw not 200 ({info}); skipped")
        ins["skip"] = True

# apply insertions (idempotent: skip if the image URL already present)
new_body = body
for ins in insertions:
    if ins.get("skip"):
        continue
    img_marker = f"{RAW_BASE}{ins['panel']}.jpg"
    if img_marker in new_body:
        notes.append(f"panel {ins['panel']} already present; skipped")
        continue
    anchor = ins["anchor"]
    idx = new_body.find(anchor)
    if idx < 0:
        notes.append(f"anchor for panel {ins['panel']} not found; skipped")
        continue
    pos = idx + len(anchor)
    new_body = new_body[:pos] + ins["block"] + new_body[pos:]
    used_panels.append(ins["panel"])

print(f"used_panels={used_panels} notes={notes}")
print(f"new bodylen={len(new_body)} (delta {len(new_body) - len(body)})")

if not used_panels:
    print("NOTE: nothing to insert; not sending PATCH")
    result = {
        "id": ITEM_ID,
        "status": "fail" if notes else "ok",
        "http": "n/a",
        "panels": used_panels,
        "note": "; ".join(notes) or "no change",
    }
    print("RESULT_JSON " + json.dumps(result, ensure_ascii=False))
    sys.exit(0)

# ----------------------------------------------------------------------------
# 5. PATCH
# ----------------------------------------------------------------------------
payload = {"body": new_body, "title": title, "tags": tags, "private": private}
try:
    pstatus, _ = http_json(API, "PATCH", payload)
    print(f"PATCH status={pstatus}")
    result = {
        "id": ITEM_ID,
        "status": "ok" if pstatus == 200 else "fail",
        "http": str(pstatus),
        "panels": used_panels,
        "note": ("; ".join(notes) if notes else f"inserted {len(used_panels)} panel(s)"),
    }
except urllib.error.HTTPError as e:
    detail = e.read().decode("utf-8", "replace")
    print(f"PATCH HTTPError {e.code}: {detail}", file=sys.stderr)
    result = {
        "id": ITEM_ID,
        "status": "fail",
        "http": str(e.code),
        "panels": used_panels,
        "note": f"PATCH failed: {detail[:300]}",
    }

print("RESULT_JSON " + json.dumps(result, ensure_ascii=False))
