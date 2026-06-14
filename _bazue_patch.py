# -*- coding: utf-8 -*-
"""スナックバス江コマ挿絵を Qiita 記事 da2a2822dabe7b17b8c8 に追加し PATCH 反映する単発スクリプト。"""
import sys, io, json, urllib.request

# stdout を UTF-8 に (Windows cp932 回避)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 1. トークン取得
sys.path.insert(0, r"D:/projects/fullsense/tools")
from qiita_public_post import get_token  # noqa: E402
tok = get_token()

ITEM_ID = "da2a2822dabe7b17b8c8"
API = "https://qiita.com/api/v2/items/" + ITEM_ID
RAW_BASE = "https://raw.githubusercontent.com/furuse-kazufumi/fullsense/main/docs/articles/assets/bazue_all/"

note = []


def fail(msg):
    print(json.dumps({"status": "fail", "note": msg}, ensure_ascii=False))
    sys.exit(1)


# 2. GET 現状取得
req = urllib.request.Request(API, headers={"Authorization": "Bearer " + tok})
try:
    with urllib.request.urlopen(req) as r:
        item = json.load(r)
except Exception as e:  # noqa: BLE001
    fail("GET failed: %r" % e)

body = item["body"]
title = item["title"]
private = item["private"]
tags = [{"name": t["name"], "versions": t.get("versions", [])} for t in item["tags"]]
print("GET ok: title=%s body_len=%d private=%s" % (title, len(body), private))

# 3. コマ選定 (記事テーマに最適):
#   137 = 記憶/忘れない -> 「なぜ開発履歴を残すか」(後から文脈を読めるように残す)
#   196 = honest/over-claim 戒め -> 「Honest disclosure 事件」(変に速い結果を疑い正直に開示)
PANELS = [
    {
        "num": "137",
        "alt": "何を話そうとしたか忘れてしまうコマ",
        "quote": "あれ 何を話そうとしたんだっけ",
        "ctx": "だから 5 日間の判断と失敗を時系列で残す。忘れる前に書く、が開発履歴の本質",
    },
    {
        "num": "196",
        "alt": "嘘は良くないと戒めるコマ",
        "quote": "嘘は 良くないよ",
        "ctx": "「変に速い」数字に飛びつかず疑って正直に再開示した、まさにこの教訓",
    },
]

# 画像 200 事前確認
for p in PANELS:
    url = RAW_BASE + p["num"] + ".jpg"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD")) as resp:
            code = resp.status
    except urllib.error.HTTPError as he:  # HEAD 非対応なら GET で確認
        try:
            with urllib.request.urlopen(url) as resp2:
                code = resp2.status
        except Exception as e2:  # noqa: BLE001
            fail("image %s not reachable: %r" % (p["num"], e2))
    except Exception as e:  # noqa: BLE001
        fail("image %s check error: %r" % (p["num"], e))
    if code != 200:
        fail("image %s HTTP %s" % (p["num"], code))
    print("image %s.jpg -> HTTP %s" % (p["num"], code))


def block(p):
    url = RAW_BASE + p["num"] + ".jpg"
    return (
        "![%s](%s)\n"
        "> 🗒️ *「%s」— %s*（© Forbidden shibukawa / SHUEISHA・スナックバス江）\n"
        % (p["alt"], url, p["quote"], p["ctx"])
    )


used = []

# 4. 挿入: 137 = 導入「なぜ開発履歴を残すか」の最初の段落直後
intro_anchor = (
    "- 翌日以降の自分 (および Claude Opus 4.7 ccr 経由) が文脈を読めるように\n"
)
if intro_anchor in body:
    body = body.replace(intro_anchor, intro_anchor + "\n" + block(PANELS[0]) + "\n", 1)
    used.append(PANELS[0]["num"])
else:
    note.append("intro anchor not found, skipped 137")

# 196 = 「### Honest disclosure 事件」見出し直後
hd_anchor = "### Honest disclosure 事件\n"
if hd_anchor in body:
    body = body.replace(hd_anchor, hd_anchor + "\n" + block(PANELS[1]) + "\n", 1)
    used.append(PANELS[1]["num"])
else:
    note.append("honest-disclosure anchor not found, skipped 196")

if not used:
    fail("no insertion anchors matched; nothing changed. " + "; ".join(note))

print("inserted panels: %s" % used)

# 5. PATCH 送信
payload = json.dumps(
    {"body": body, "title": title, "tags": tags, "private": private},
    ensure_ascii=False,
).encode("utf-8")
patch_req = urllib.request.Request(
    API,
    data=payload,
    method="PATCH",
    headers={
        "Authorization": "Bearer " + tok,
        "Content-Type": "application/json",
    },
)
http_code = None
try:
    with urllib.request.urlopen(patch_req) as resp:
        http_code = resp.status
        resp.read()
except urllib.error.HTTPError as he:
    http_code = he.code
    note.append("PATCH HTTPError body: " + he.read().decode("utf-8", "replace")[:500])
except Exception as e:  # noqa: BLE001
    fail("PATCH failed: %r" % e)

print("PATCH HTTP %s" % http_code)

# 6. 結果
status = "ok" if http_code == 200 else "fail"
result = {
    "status": status,
    "http": str(http_code),
    "panels": used,
    "note": "; ".join(note) if note else "panels 137(memory/keep-record) + 196(honest-disclosure) inserted at intro + Honest disclosure section",
}
print("RESULT_JSON=" + json.dumps(result, ensure_ascii=False))
