# Portable Dev Orchestrator

Portable Dev Orchestrator 是一套把「需求釐清、程式實作、測試、審查與交接」串起來的開發流程。`VERSION`、`config.yaml`、`core/` 與 `adapters/` 是唯一的維護來源；安裝到 Codex 或匯出給 ChatGPT 的內容都由 scripts 產生。

## 誰負責什麼

- **ChatGPT**：討論需求、釐清限制、產生 SPEC 與 acceptance criteria；收到 DEV HANDOFF 後做規格符合性審查。
- **Codex**：檢查 repository、修改檔案、整合、build、test、verification，並擁有最終 repository 狀態。
- **Gemini**：透過 Antigravity 做唯讀 codebase investigation、dependency／impact analysis 與快速 diff review。
- **Luna**：主要 implementation worker；小修改用低 reasoning，一般實作用 medium，困難任務再提高。
- **Sol**：escalation engineer，不是預設 developer。除非使用者直接指定，至少兩次獨立且有 evidence 的失敗後才允許使用。
- **Astra**：大型、高風險、架構性或模糊需求的 SPEC／architecture 角色。
- **Claude**：高風險或明確要求時的獨立唯讀 reviewer，不會每次都呼叫。

## 完整流程

```text
ChatGPT
  ↓
SPEC + Acceptance Criteria
  ↓
Codex Orchestrator
  ↓
Gemini / Luna / Astra / Sol / Claude（只選有不同工作價值的角色）
  ↓
Build + Tests + Verification
  ↓
DEV HANDOFF
  ↓
ChatGPT SPEC Review
  ↓
ACCEPTED / NEEDS ITERATION
```

## Terminal 與 Codex Desktop

第一次安裝或同步：

```bash
~/Projects/dev-orchestrator/scripts/install_codex.sh
```

驗證 portable source、已安裝 Skill 與 13 個 routing／handoff 測試：

```bash
~/Projects/dev-orchestrator/scripts/validate.sh
```

需要重新確認 Antigravity 模型時：

```bash
~/Projects/dev-orchestrator/scripts/validate.sh --live-agy
```

在 Codex CLI 或 Codex Desktop 可直接描述開發工作，或明確輸入 `$dev-orchestrator`。完整實作任務結束時，Codex 會輸出 DEV HANDOFF 與可貼回 ChatGPT 的 RETURN 區塊。

## macOS 選單列 App（2.2.1）

若要在 macOS 上快速查看本機已追蹤的用量，可執行：

```bash
./scripts/install_macos_app.sh
```

腳本會建立 release app、放入匹配版本的 usage helper，並安裝到 `~/Applications/DevOrchestratorBar.app`（可用 `DEV_ORCHESTRATOR_APP_DIR` 指定其他使用者 Applications 目錄）。啟動後會直接打開「Dev Orchestrator 用量」視窗，右上角選單列也會保留快速入口；這是 `LSUIElement` 選單列 App，因此不會在 Dock 顯示一般應用程式圖示。

選單列標題顯示目前所有專案的五小時追蹤總量。彈出視窗可在「目前專案」與「所有專案」間切換，也可選擇「所有帳號」或單一帳號。這些帳號／專案篩選只套用於本機 ledger 報表：不會切換 Codex、Gemini 或其他 provider 的登入帳號、session 或認證狀態；同一專案的不同帳號資料可合計，也可依帳號篩選。目前專案是最近一次成功追蹤事件所屬的最新專案，而不是檔案系統中任意猜測的資料夾。若沒有目前專案或尚未有事件，介面會顯示清楚的 setup／empty state，提示先啟用追蹤並完成一個任務。

這裡的五小時數字是本工具依已追蹤事件計算的本地統計，不是 OpenAI 或其他 provider 的官方 quota 百分比；不同帳號的 quota 不會合併。自動刷新每 30 秒只讀取本地 ledger、消耗零 model token，也不會重新執行模型請求。未啟用追蹤、未被記錄的歷史，以及啟用前的舊任務，都無法由 App 回填或推算。

追蹤資料只留在本機 usage state directory（macOS 預設 `~/Library/Application Support/dev-orchestrator/usage`；其他平台使用 `$XDG_STATE_HOME/dev-orchestrator/usage`，若未設定則使用 `~/.local/state/dev-orchestrator/usage`；可用 `DEV_ORCHESTRATOR_STATE_DIR` 變更）。這與 Codex Skill 的安裝路徑 `~/.codex/skills/dev-orchestrator` 分開；不會儲存 prompt、response、credential 或 tool output。停用 `usage_tracking` 或移除本機 state 即可停止／清除本機統計。選單列 App 是 optional：不安裝或不啟動它，不影響 CLI、Codex Skill 或 ChatGPT export 的流程。

### macOS 開發建置與測試

```bash
./scripts/build_macos_app.sh debug
swift test --package-path macos/DevOrchestratorBar
./scripts/validate.sh --skip-installed
```

`build_macos_app.sh release` 會在 `dist/DevOrchestratorBar.app` 產生簽署的 app；`install_macos_app.sh` 會先備份既有安裝再原子替換。非 macOS 主機仍可執行 portable 與 Python 驗證，驗證腳本會明確略過 macOS Swift 測試。

## ChatGPT 與 ChatGPT Work

ChatGPT 不會因為 Mac 上存在 `~/.codex/skills/dev-orchestrator/` 就自動取得這套流程。先匯出：

```bash
~/Projects/dev-orchestrator/scripts/export_chatgpt.sh
```

輸出位於 `dist/chatgpt/`：

- `dev-orchestrator-chatgpt-skill.zip`：正式 Agent Skill package，可在支援 Skill 上傳的 ChatGPT／Workspace Agent 使用「Add skill」加入。
- `INSTRUCTIONS.md`：一般聊天無法安裝 Skill 時的貼上版 instructions。
- `SPEC_TEMPLATE.md`：需求討論完成後產生 implementation package。
- `HANDOFF_REVIEW.md`：實作完成後審查 DEV HANDOFF。
- `CORE_WORKFLOW_SUMMARY.md`：核心工作流程摘要。

ChatGPT adapter 不會宣稱能讀本機 repository、`~/.codex/skills` 或執行 `agy`；只有當該聊天真的提供對應工具時才可使用。

## 調整模型與政策

所有模型綁定只改根目錄 `config.yaml`，再重新執行 install/export。不要直接修改安裝目錄，否則下次同步會被 portable source 覆蓋。

- 換 implementation 模型：修改 `roles.implement.model`。
- 改 Sol 門檻：修改 `limits.sol_min_failed_attempts`。
- 本次不要 Sol：在任務中說「不要用 Sol」或 `No Sol`。
- 本次只用 OpenAI：說 `OpenAI-only` 或「不要外部模型」。
- 永久關閉 Sol：把政策改進 core/config 前，請明確要求「永久改設定」；一般 override 只影響本次任務。

## Token usage（Codex opt-in）

Token usage tracking is opt-in, local-only, and non-blocking. Privacy is preserved: it never stores prompts, responses, credentials, or tool output. Usage state lives outside the repository: on macOS it defaults to `~/Library/Application Support/dev-orchestrator/usage`, while other platforms use `$XDG_STATE_HOME/dev-orchestrator/usage` or, when unset, `~/.local/state/dev-orchestrator/usage`. The installed Skill remains under `~/.codex/skills/dev-orchestrator`; set `DEV_ORCHESTRATOR_STATE_DIR` to choose another local state directory, or set the policy mode to `off` for opt-out.

```bash
~/.codex/skills/dev-orchestrator/scripts/dev-orchestrator-usage setup --account personal
dev-orchestrator-usage current --window 5h
dev-orchestrator-usage all --window 5h
dev-orchestrator-usage accounts
dev-orchestrator-usage accounts set work
```

Rows show exact token counts when the provider supplies them; unavailable values are `N/A`. A token detail column is shown only when at least one selected row has useful data, while `TOTAL` always appears. Actual token totals may be summed across accounts, but quota percentages are kept separate and are never added together. `tokscale` is optional and detected at runtime; it is not installed automatically.

The reporting shape is inspired by TokenBar and tokscale, while this project keeps its ledger local and provider-specific.

## 安全同步

`install_codex.sh` 會先驗證 source，將現有 Skill 移到 `~/.codex/backups/dev-orchestrator/` 備份，再原子式換入新版本。它不使用 symlink、不修改其他 Skills，也不會建立 remote 或 push。

## License

本專案採用 [MIT License](LICENSE)。
