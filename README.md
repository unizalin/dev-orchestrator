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

Token usage tracking is opt-in, local-only, and non-blocking. Privacy is preserved: it never stores prompts, responses, credentials, or tool output. State lives outside the repository (by default under `~/.codex`); set `DEV_ORCHESTRATOR_STATE_DIR` to choose another local directory, or set the policy mode to `off` for opt-out.

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
