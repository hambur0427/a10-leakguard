# Task 2 驗收證據（2026-11-18）

本目錄只保存可重查的技術驗證，不是個人作業報告。

## 本機驗證

- `pytest-task2.txt`：33 passed；涵蓋 RBAC、repo 範圍、CSRF、ON/OFF、直接 API、稽核及環境讀取。
- `pytest-pr-3.txt`、`pytest-pr-4.txt`：以各 PR 的原始 head SHA 取出程式並依各自 requirements 安裝，均 23 passed。
- `local-verification.json`：退出碼、實際版本與 PR SHA。測試共用隔離 venv、程式與 flags 位於分開的目錄；非所有版本排列的測試。
- 重現：Python 3.12，進入 `03_維運QA_任務3`，`pip install -r requirements.txt`，`python -m pytest -v`。

## GitHub Actions

測試程式版本：`b7b61c4b2fed042c4746d9c874a9a11ae3b4fe31`。

| 事件 | 結果 | Secret 工作 | Run |
|---|---|---|---|
| push | 33 passed in 0.35s；checkout v7、setup-python v7、安裝與 pytest 均成功 | success；確認非空，沒有輸出值 | https://github.com/hambur0427/a10-leakguard/actions/runs/44133028576 |
| pull_request | 33 passed in 0.37s | skipped，符合 PR 不使用環境機密的設計 | https://github.com/hambur0427/a10-leakguard/actions/runs/44133092959 |

`ci-verification.json` 保存 job／step 結果與測試摘要，未發布 raw 環境 log。此後若只有證據文件變更，請同時查看 PR 最新 head 的 Checks，不把舊 SHA 的 run 說成最新 SHA。

## GitHub 安全狀態

`github-snapshot.json` 以 yu1234552026 帳號的已授權 API 讀取：

- Dependabot open alerts 與所有狀態皆 `[]`，成功查詢；不是 404，也未編造 CVE／CVSS。
- staging 已存在，SECRET_KEY 名稱已存在；Repository Secrets 空；未取得或修改機密值。
- Environment 清單僅 staging；production 未建立且本次未修改。
- push=true、admin=false；Secret Scanning API 404，security_and_analysis 無資料，因此 Secret Scanning／Push Protection 狀態【待人工處理】。
- 最新上游發行、PR #1–#4 狀態與版本更新說明均保留；普通更新與真實警示分開記錄於安全設計文件。

## 提交邊界

app.py 與 flags.json 未修改；沒有真實金鑰撤銷／輪替；未合併任何 PR；未關閉 Issue 或修改其他成員進度。未加入快取、venv、截圖草稿或個人報告。

Issue #6 的設計與驗證在 PR 分支完成；Issue #7 的可執行部分完成，保護設定仍需管理員提供證據。管理員應檢查 Settings → Code security 的 Secret Scanning 與 Push Protection，必要時啟用並記錄真實結果，不需傳遞機密值。
