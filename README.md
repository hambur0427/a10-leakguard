# LeakGuard — 作業 10 範例專案

```
00_三角色計畫.md          三個角色的步驟
01_PM_任務1/              團隊、責任表、issue 清單、時程
02_開發者_任務2/          安全設計、架構圖、dependabot.yml、ci.yml
03_維運QA_任務3/          假設、開關、Flask 範例、測試
```

## 執行

```bash
cd 03_維運QA_任務3
pip install -r requirements.txt
pytest -q                      # 跑測試（23 個）
SECRET_KEY=$(python3 -c "import secrets;print(secrets.token_hex(32))") python app.py
```

開啟 http://127.0.0.1:5000

## 截 ON 與 OFF 的畫面

1. 瀏覽器開 `/login/bob`，再開 `/alerts`：這是 **ON**，有「一鍵撤銷」按鈕，通知管道依嚴重度分級
2. 編輯 `flags.json`，把兩個 `enabled` 改成 `false`，重新整理 `/alerts`：這是 **OFF**，沒有按鈕，通知全部即時
3. 開關 OFF 時，用 curl 直接打撤銷 API，會得到 404，這是「伺服器端也被擋」的證據
4. 換 `/login/dana`（一般成員）與 `/login/chen`（別的 repo 負責人）比較差異

## 示範帳號

| 帳號 | 角色 | repo |
|---|---|---|
| alice | admin | 全部 |
| bob | repo_owner | team/api |
| chen | repo_owner | team/web |
| dana | member | 無 |

## 限制（誠實標示）

- 登入是簡化版，正式版規劃改用 GitHub OAuth / OIDC
- 資料與稽核紀錄在記憶體，重啟即消失
- 「撤銷」只改狀態，未真的呼叫各服務的撤銷 API
- Dependabot 處理表是範本，需用你們 repo 的實際警示填寫

## 團隊與目標（Task 1）

LeakGuard 掃描團隊 GitHub repo 中外洩的 API 金鑰或 token，通知 repo 負責人，並協助撤銷與輪替，以縮短外洩到處理的時間。

本次以功能開關驗證兩項功能：

- `one_click_revoke`：一鍵撤銷並產生輪替清單
- `severity_notify`：依嚴重度分級通知

| 成員 | GitHub 帳號 | 角色 | 任務／負責部分 | 期限 |
|---|---|---|---|---|
| A | `hambur0427` | PM | 任務 1：名單、目標、責任表、GitHub Project、時程 | 11/18 |
| B | 待確認 | 開發者 | 任務 2：驗證與授權、SCA（Dependabot）、機密管理 | 11/21 |
| C | 待確認 | QA（兼設計） | 任務 3：假設、功能開關、ON/OFF 畫面、測試 | 11/22 |

B、C 尚未提供 GitHub 帳號，確認後再邀請並指派 issue。完整分工、交接點與時程見 [`01_PM_任務1/分工表.md`](01_PM_任務1/分工表.md)。
