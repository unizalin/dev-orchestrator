import Combine
import Foundation
import UsageClient

public enum LoadState: Equatable {
    case idle
    case loading
    case loaded
    case failed(String)
}

/// A presentation-facing grouping of usage rows. Rows are already aggregated
/// by the reporting helper; this type keeps the grouping key available to the
/// popover without asking the UI to recompute any totals.
public struct UsageRowGroup: Identifiable, Equatable, Sendable {
    public let id: String
    public let rows: [UsageRow]

    public init(id: String, rows: [UsageRow]) {
        self.id = id
        self.rows = rows
    }
}

@MainActor
public final class UsageViewModel: ObservableObject {
    @Published public var scope: ProjectScope = .currentProject
    @Published public var selectedAccount: String?
    @Published public var autoRefresh = true
    @Published public private(set) var snapshot: UsageSnapshot?
    @Published public private(set) var state: LoadState = .idle
    @Published public private(set) var isStale = false
    @Published public private(set) var refreshedAt: Date?

    private let loader: any UsageLoading
    private var refreshInFlight = false

    public init(loader: any UsageLoading) {
        self.loader = loader
    }

    public func refresh() async {
        guard !refreshInFlight else { return }
        refreshInFlight = true
        defer { refreshInFlight = false }

        if snapshot == nil {
            state = .loading
        }

        do {
            let loaded = try await loader.load(UsageRequest(scope: scope, account: selectedAccount))
            snapshot = loaded
            state = .loaded
            isStale = false
            refreshedAt = Date()
        } catch {
            state = .failed(error.localizedDescription)
            isStale = snapshot != nil
        }
    }

    /// The menu bar title always reflects the global five-hour total. It is
    /// intentionally independent of the active scope and account filters.
    public var menuBarTitle: String? {
        compactTokens(snapshot?.allProjectsWindowTotal)
    }

    public var selectedTotal: Int? { snapshot?.selectedScopeWindowTotal }
    public var selectedWindowTotal: Int? { snapshot?.selectedScopeWindowTotal }
    public var selectedScopeTotal: Int? { snapshot?.selectedScopeWindowTotal }
    public var selectedScopeWindowTotal: Int? { snapshot?.selectedScopeWindowTotal }
    public var globalTotal: Int? { snapshot?.allProjectsWindowTotal }
    public var globalWindowTotal: Int? { snapshot?.allProjectsWindowTotal }
    public var allProjectsTotal: Int? { snapshot?.allProjectsWindowTotal }
    public var allProjectsWindowTotal: Int? { snapshot?.allProjectsWindowTotal }
    public var currentProjectCumulativeTotal: Int? { snapshot?.currentProjectCumulativeTotal }

    public var accounts: [String] { snapshot?.accounts ?? [] }
    public var currentProject: ProjectInfo? { snapshot?.currentProject }
    public var activeAccount: String? { snapshot?.activeAccount }
    public var rows: [UsageRow] { snapshot?.rows ?? [] }
    public var visibleDetailFields: [String] { snapshot?.availableDetailFields ?? [] }
    public var availableDetailFields: [String] { visibleDetailFields }

    /// Group rows by their complete display identity. The key is stable and
    /// human-readable, while the original rows remain authoritative.
    public var groupedRows: [String: [UsageRow]] {
        Dictionary(grouping: rows) { row in
            Self.groupKey(for: row)
        }
    }

    public var rowGroups: [UsageRowGroup] {
        groupedRows.keys.sorted().map { key in
            UsageRowGroup(id: key, rows: groupedRows[key] ?? [])
        }
    }

    public var isLoading: Bool { state == .loading }
    public var hasSnapshot: Bool { snapshot != nil }
    public var hasRows: Bool { !rows.isEmpty }
    public var isEmpty: Bool { snapshot != nil && rows.isEmpty }
    public var isEmptyState: Bool { isEmpty }
    public var hasNoData: Bool { isEmpty }
    public var showsEmptyState: Bool { isEmpty && state != .loading }

    private static func groupKey(for row: UsageRow) -> String {
        [row.projectLabel, row.accountAlias, row.role, row.provider, row.model]
            .joined(separator: " / ")
    }
}
