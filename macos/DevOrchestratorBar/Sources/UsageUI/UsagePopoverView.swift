import SwiftUI
import UsageClient

/// Pure visibility rules used by the popover. Keeping these decisions out of
/// the view makes it possible to test that unavailable fields and sections are
/// not rendered without launching a SwiftUI scene.
public struct Presentation: Equatable, Sendable {
    public let snapshot: UsageSnapshot?
    public let loadState: LoadState
    public let hasStoredSnapshot: Bool

    public init(
        snapshot: UsageSnapshot?,
        loadState: LoadState = .idle,
        hasStoredSnapshot: Bool = false
    ) {
        self.snapshot = snapshot
        self.loadState = loadState
        self.hasStoredSnapshot = hasStoredSnapshot
    }

    public var contentState: UsagePopoverContentState {
        if snapshot == nil {
            if loadState == .loading && !hasStoredSnapshot {
                return .loading
            }
            return .unavailable
        }
        return showsEmptyState ? .empty : .content
    }

    public var showsInput: Bool { showsDetail("input_tokens", at: \.inputTokens) }
    public var showsCache: Bool { showsDetail("cache_tokens", at: \.cacheTokens) }
    public var showsOutput: Bool { showsDetail("output_tokens", at: \.outputTokens) }
    public var showsThinking: Bool { showsDetail("thinking_tokens", at: \.thinkingTokens) }
    public var showsTotal: Bool { showsDetail("total_tokens", at: \.totalTokens) }

    // More explicit aliases keep call sites readable and make the rendering
    // contract discoverable to clients that do not use the short names.
    public var showsInputTokens: Bool { showsInput }
    public var showsCacheTokens: Bool { showsCache }
    public var showsOutputTokens: Bool { showsOutput }
    public var showsThinkingTokens: Bool { showsThinking }
    public var showsTotalTokens: Bool { showsTotal }

    public var showsDiagnostics: Bool {
        (snapshot?.diagnostics.malformedEventCount ?? 0) > 0
    }

    public var showsEmptyState: Bool {
        snapshot != nil && (snapshot?.rows.isEmpty ?? true)
    }

    public var showsSummary: Bool {
        snapshot?.selectedScopeWindowTotal != nil
    }

    public var showsCumulative: Bool {
        snapshot?.currentProjectCumulativeTotal != nil
    }

    private func showsDetail(_ field: String, at keyPath: KeyPath<UsageTokens, Int?>) -> Bool {
        guard let snapshot,
              snapshot.availableDetailFields.contains(field)
        else { return false }
        return snapshot.rows.contains { $0.usage[keyPath: keyPath] != nil }
    }
}

public enum UsagePopoverContentState: Equatable, Sendable {
    case loading
    case unavailable
    case empty
    case content
}

/// Pure menu-bar label rules keep the nil-title accessibility behavior
/// testable without rendering a MenuBarExtra scene.
public struct MenuBarLabelPresentation: Equatable, Sendable {
    public let title: String?

    public init(title: String?) {
        self.title = title
    }

    public var showsTitle: Bool { title != nil }

    public var accessibilityLabel: String {
        guard let title else { return "開啟追蹤用量" }
        return "追蹤用量：\(title)"
    }
}

public struct UsagePopoverView: View {
    @ObservedObject public var model: UsageViewModel
    @Binding private var launchAtLogin: Bool
    private let launchAtLoginError: String?
    private let onLaunchAtLoginChange: ((Bool) -> Void)?

    public init(
        model: UsageViewModel,
        launchAtLogin: Binding<Bool> = .constant(false),
        launchAtLoginError: String? = nil,
        onLaunchAtLoginChange: ((Bool) -> Void)? = nil
    ) {
        self.model = model
        _launchAtLogin = launchAtLogin
        self.launchAtLoginError = launchAtLoginError
        self.onLaunchAtLoginChange = onLaunchAtLoginChange
    }

    public var body: some View {
        ScrollView(.vertical) {
            VStack(alignment: .leading, spacing: 14) {
                controls

                if model.isStale {
                    staleNotice
                }

                content

                Divider()
                Toggle("登入時啟動", isOn: Binding(
                    get: { launchAtLogin },
                    set: { value in
                        launchAtLogin = value
                        onLaunchAtLoginChange?(value)
                    }
                ))
                if let launchAtLoginError {
                    Text(launchAtLoginError)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(16)
        }
        .frame(width: 360)
    }

    private var controls: some View {
        VStack(alignment: .leading, spacing: 10) {
            Picker("範圍", selection: $model.scope) {
                Text("目前專案").tag(ProjectScope.currentProject)
                Text("全部專案").tag(ProjectScope.allProjects)
            }
            .pickerStyle(.segmented)

            Picker("帳號", selection: $model.selectedAccount) {
                Text("全部帳號").tag(String?.none)
                ForEach(model.accounts, id: \.self) { account in
                    Text(account).tag(Optional(account))
                }
            }

            Toggle("自動更新（30 秒）", isOn: $model.autoRefresh)
            Button("立即更新") {
                Task { await model.refresh() }
            }
            .buttonStyle(.bordered)
        }
    }

    @ViewBuilder
    private var content: some View {
        let presentation = Presentation(
            snapshot: model.displaySnapshot,
            loadState: model.state,
            hasStoredSnapshot: model.snapshot != nil
        )
        if presentation.contentState == .loading {
            ProgressView("載入追蹤用量…")
                .frame(maxWidth: .infinity, alignment: .center)
        } else if presentation.contentState == .empty {
            unavailable(
                title: "尚無追蹤用量",
                icon: "tray",
                description: "未找到已記錄的任務用量；完成下一個編排任務後會顯示在這裡。"
            )
        } else if presentation.contentState == .unavailable {
            unavailable(
                title: "無法載入追蹤用量",
                icon: "exclamationmark.triangle",
                description: failureDescription
            )
        } else {
            VStack(alignment: .leading, spacing: 12) {
                totals

                if presentation.showsDiagnostics {
                    Label(
                        "略過 \(model.displaySnapshot?.diagnostics.malformedEventCount ?? 0) 筆格式錯誤資料",
                        systemImage: "exclamationmark.triangle"
                    )
                    .font(.caption)
                    .foregroundStyle(.orange)
                }

                ForEach(model.rowGroups) { group in
                    rowGroup(group, presentation: presentation)
                }
            }
        }
    }

    @ViewBuilder
    private var totals: some View {
        let presentation = Presentation(snapshot: model.displaySnapshot)
        if presentation.showsSummary || presentation.showsCumulative {
            VStack(alignment: .leading, spacing: 8) {
                if presentation.showsSummary,
                   let selectedTotal = model.selectedScopeWindowTotal,
                   let formatted = compactTokens(selectedTotal) {
                    Text("近 5 小時已追蹤用量")
                        .font(.headline)
                    Text(formatted)
                        .font(.system(.title2, design: .rounded).weight(.semibold))
                }

                if presentation.showsCumulative,
                   let cumulative = model.currentProjectCumulativeTotal,
                   let formatted = compactTokens(cumulative) {
                    LabeledContent("專案累計", value: formatted)
                }
                if let refreshedAt = model.refreshedAt {
                    LabeledContent("上次更新", value: Self.dateFormatter.string(from: refreshedAt))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private func rowGroup(_ group: UsageRowGroup, presentation: Presentation) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(group.displayLabel)
                .font(.subheadline.weight(.semibold))
                .fixedSize(horizontal: false, vertical: true)

            ForEach(Array(group.rows.enumerated()), id: \.offset) { _, row in
                VStack(alignment: .leading, spacing: 3) {
                    if presentation.showsInput,
                       let value = row.usage.inputTokens {
                        detail("輸入", value: value)
                    }
                    if presentation.showsCache,
                       let value = row.usage.cacheTokens {
                        detail("快取", value: value)
                    }
                    if presentation.showsOutput,
                       let value = row.usage.outputTokens {
                        detail("輸出", value: value)
                    }
                    if presentation.showsThinking,
                       let value = row.usage.thinkingTokens {
                        detail("思考", value: value)
                    }
                    if presentation.showsTotal,
                       let value = row.usage.totalTokens {
                        detail("合計", value: value)
                    }
                }
                .font(.caption)
                .padding(.leading, 8)
            }
        }
    }

    private func detail(_ label: String, value: Int) -> some View {
        LabeledContent(label, value: compactTokens(value) ?? "—")
    }

    private var staleNotice: some View {
        VStack(alignment: .leading, spacing: 3) {
            Label("顯示上次成功更新的資料", systemImage: "clock.badge.exclamationmark")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.orange)
            if case let .failed(message) = model.state {
                Text(message)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var failureDescription: String {
        if case let .failed(message) = model.state {
            return message
        }
        return "請確認追蹤功能已完成設定，且 App 內含 UsageCLI 輔助程式。"
    }

    @ViewBuilder
    private func unavailable(title: String, icon: String, description: String) -> some View {
        if #available(macOS 14.0, *) {
            ContentUnavailableView {
                Label(title, systemImage: icon)
            } description: {
                Text(description)
            }
        } else {
            VStack(spacing: 6) {
                Label(title, systemImage: icon)
                    .font(.headline)
                Text(description)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
            .frame(maxWidth: .infinity)
        }
    }

    private static let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_TW")
        formatter.dateStyle = .short
        formatter.timeStyle = .short
        return formatter
    }()
}
