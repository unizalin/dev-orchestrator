# Task-scoped overrides

Overrides affect the current task only unless the user explicitly says “以後都這樣”, “永久改設定”, or “更新 config”. Permanent changes require editing `config.yaml` and/or core policy, followed by install/export.

Recognize equivalent wording, not only these exact phrases.

| Override | Behavior |
|---|---|
| `AUTO` | Use default classification and minimum-role routing. |
| `省額度` | Prefer low/medium effort; skip optional external calls and independent review. |
| `品質優先` | Raise reasoning and verification where useful; keep the Sol gate and distinct-information rule. |
| `OpenAI-only` | Disable all Antigravity roles. Root Codex performs investigation/review locally. |
| `不要外部模型` | Same as OpenAI-only for this task. |
| `External-first investigation` | Start unfamiliar-system or bug analysis with `investigate`, then hand evidence to implementation. |
| `Gemini 只分析` | Gemini is advisory/read-only; implementation and writes remain in Codex. |
| `Gemini 分析 Luna 寫` | Run one bounded `investigate`, hand its artifact to `implement`, then let root Codex integrate and verify. |
| `Analysis only` | Do not write repository files, apply patches, commit, or run commands with material side effects. |
| `先不要改 code` | Same as Analysis only. |
| `No Sol` | Disable `escalate` regardless of failure count. |
| `不要用 Sol` | Same as No Sol. |
| `Force Sol High` | Explicitly use `escalate` at high effort and bypass the failure threshold for this task. |
| `直接 Sol High` | Same as Force Sol High. |
| `Luna implementation` | Require `implement` and `quick_implement` to run on the configured Luna model; pause if the active picker is another OpenAI model. |
| `Astra 先設計` | Run `spec` before investigation/implementation; it does not grant write access. |
| `不要 review` | Skip optional review roles; required verification and project-mandated checks remain. |
| `加強 review` | Add the smallest review set that covers distinct named risks; do not run every reviewer. |

Compatible overrides combine. Read-only and safety constraints remain binding. A negative constraint such as No Sol or Analysis only wins over an automatic route until the user changes it.
