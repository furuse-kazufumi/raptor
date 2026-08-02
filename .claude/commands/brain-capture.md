---
description: 第二の脳に素早くメモを投げる — 生テキストを brain の 00_Inbox にタイムスタンプ付きノートとして保存(捕捉→整理ループの入力路)
---

# /brain-capture — 第二の脳への即時捕捉

思いついたことを失わないよう private brain repo (`C:/dev/projects/brain`) の `00_Inbox/` へ
生ノートとして書き出す。organizer(`/brain-maintain`)が後で orphan として拾い、リンク/昇格の
対象にする。設計 = `2ndbrain/docs/superpowers/specs/2026-08-01-second-brain-sp3-*`(SP2 入力路)。

## 手順

1. ユーザーの発話(または指定テキスト)を捕捉:
   ```
   cd C:/dev/projects/brain && PYTHONUTF8=1 py -3.11 tools/brain_capture.py --vault . --text "<メモ本文>"
   ```
   任意で `--title "<見出し>"`。
2. 生成パス(`00_Inbox/<日時>-<slug>.md`)を 1 行で報告。
3. 「次に `/brain-maintain` で整理対象に上がる」ことだけ添える(自動 push しない)。

## 規律

- **捕捉は追記のみ**(既存を上書きしない・衝突は `-N` で回避)。**削除しない**。
- 生ノートは `00_Inbox/`(人間層)。昇格(→10_Journal/50_MOC)は将来の `/mature`(別 SP・独自 spec)。
- **push は human-gate**(private repo)。
