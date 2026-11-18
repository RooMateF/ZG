# 《末日第十四天》本機接手

2026-11-18。倉庫為 `RooMateF/ZG`，Godot 專案入口是 `hd2d/project.godot`。

## 取得專案

在本機用有倉庫權限的 GitHub 帳號執行 `git clone https://github.com/RooMateF/ZG.git`。已有 `ZG` 的話，在該資料夾執行 `git pull --ff-only`。一樓貼圖與交接文件都隨這次提交取得。Windows 的 Godot 安裝與開發環境設定見[換機說明](../NEW_MACHINE.md)。

## 目前進度

- 客廳 1.35 倍家具、角色 A 組轉身圖及 32 種行屍外觀已匯入 Godot。`05d04a2` 加入角色並排檢查。
- 一樓第一批 63 張 PNG 已通過獨立美術與技術複審，位於 `hd2d/art/inbox/house_ground_floor/`，待 Claude 匯入。包含廚房地磚、門窗、車庫鐵捲門、樓梯、廚房與一樓臥室家具。門由程式旋轉同一片門板。餐桌、餐椅與單人床採拆件組裝，床底留空給陳水木藏身。尺寸及組裝位置見[美術交接](art_to_eng.md)。
- 初版範圍是一棟透天厝及門口巷子，從第一天玩到天亮。陳水木出場，沈以美留到後續藥局。美術選定的四種初版行屍為 `walker`、`walker_05`、`walker_office_02`、`walker_police_01`。這四組以及許晏、陳水木、疾走者的 B 走路和 C 戰鬥圖仍待製作，陳水木另缺 D 立繪。
- 先核對工程回覆和一樓匯入結果，再續做二樓、三樓與巷子。場景燈光、景深及實機流暢度仍待 Godot 驗證。[初版工作清單](../FIRST_BUILD.md)

## 開新的本機 Codex session

用桌面版 Codex 開啟本機 `ZG` 資料夾，選 **Work in → This computer**。將以下這段交給新 session。

> 請以《末日第十四天》的美術總監身分接手。先讀 `CLAUDE.md`、`docs/FIRST_BUILD.md`、`docs/ART_DIRECTOR.md`、`docs/ART_TRACKER.md`，以及 `docs/handoff/eng_to_art.md` 和 `docs/handoff/art_to_eng.md` 的最新一則。確認一樓 `house_ground_floor` 的素材和匯入狀態，再依優先序接續。沿用 HD-2D 像素密度、現代台灣都市風格及 1.35 倍家具尺寸。交圖前安排獨立美術和技術複審。美術檔放在 `hd2d/art/inbox/`，由 Claude 匯入 Godot。依專案規則在使用者指示時提交和推送。
