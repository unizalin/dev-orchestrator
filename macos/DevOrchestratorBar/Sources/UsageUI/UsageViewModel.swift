import Combine
import Foundation
import UsageClient

public enum LoadState: Equatable, Sendable {
    case idle
    case loading
    case loaded
    case failed(String)
}

/// A presentation-facing grouping of usage rows. Rows are already aggregated
/// by the reporting helper; this type keeps the grouping key available to the
/// popover without asking the UI to recompute any totals.
public struct UsageRowGroup: Identifiable, Equatable, Sendable {
    public let id: UsageGroupIdentity
    public let rows: [UsageRow]

    public init(id: UsageGroupIdentity, rows: [UsageRow]) {
        self.id = id
        self.rows = rows
    }

    /// Human-readable grouping label kept separate from the stable identity.
    /// The project key remains in `id` even when labels collide.
    public var displayLabel: String {
        guard let row = rows.first else { return id.projectLabel }
        return [row.projectLabel, row.accountAlias, row.role, row.provider, row.model]
            .joined(separator: " / ")
    }
}

/// Structural identity for a row group. Keeping each component separate
/// avoids delimiter collisions (for example, `a / b` + `c` vs `a` + `b / c`).
public struct UsageGroupIdentity: Hashable, Sendable {
    public let projectKey: String
    public let projectLabel: String
    public let accountAlias: String
    public let role: String
    public let provider: String
    public let model: String

    public init(projectKey: String, projectLabel: String, accountAlias: String, role: String, provider: String, model: String) {
        self.projectKey = projectKey
        self.projectLabel = projectLabel
        self.accountAlias = accountAlias
        self.role = role
        self.provider = provider
        self.model = model
    }
}

@MainActor
public final class UsageViewModel: ObservableObject {
    @Published public var scope: ProjectScope = .currentProject {
        didSet { selectionDidChange() }
    }
    @Published public var selectedAccount: String? {
        didSet { selectionDidChange() }
    }
    @Published public var autoRefresh = true
    @Published public private(set) var snapshot: UsageSnapshot?
    @Published public private(set) var state: LoadState = .idle
    @Published public private(set) var isStale = false
    @Published public private(set) var refreshedAt: Date?

    private let loader: any UsageLoading
    private var refreshInFlight = false
    private var refreshRequested = false
    private var inFlightRequest: UsageRequest?
    public private(set) var snapshotRequest: UsageRequest?

    public init(loader: any UsageLoading) {
        self.loader = loader
    }

    public func refresh() async {
        if refreshInFlight {
            // A second request for the same selector is already covered by
            // the active load. A changed selector, however, must be queued.
            if currentRequest != inFlightRequest {
                refreshRequested = true
            }
            return
        }
        refreshRequested = true
        refreshInFlight = true
        defer {
            refreshInFlight = false
            inFlightRequest = nil
        }

        while refreshRequested {
            refreshRequested = false
            let request = currentRequest
            inFlightRequest = request
            if displaySnapshot == nil {
                state = .loading
            }

            do {
                let loaded = try await loader.load(request)
                // A selector can change while the helper is running. Never
                // expose a response for the old selector; queue one more
                // pass for the latest request instead.
                guard request == currentRequest else {
                    refreshRequested = true
                    continue
                }
                snapshot = loaded
                snapshotRequest = request
                state = .loaded
                isStale = false
                refreshedAt = Date()
            } catch {
                guard request == currentRequest else {
                    refreshRequested = true
                    continue
                }
                state = .failed(error.localizedDescription)
                isStale = snapshot != nil && snapshotRequest == request
            }
        }
    }

    /// The request represented by the current controls. Keeping this value
    /// derived prevents an old snapshot from being mistaken for current data.
    public var currentRequest: UsageRequest {
        UsageRequest(scope: scope, account: selectedAccount)
    }

    /// Snapshot data is safe for the popover only when it matches the current
    /// scope/account selection. The last successful snapshot remains stored so
    /// the global menu title can continue to show its unfiltered total.
    public var displaySnapshot: UsageSnapshot? {
        guard snapshotRequest == currentRequest else { return nil }
        return snapshot
    }

    /// The menu bar title always reflects the global five-hour total. It is
    /// intentionally independent of the active scope and account filters.
    public var menuBarTitle: String? {
        compactTokens(snapshot?.allProjectsWindowTotal)
    }

    public var selectedTotal: Int? { displaySnapshot?.selectedScopeWindowTotal }
    public var selectedWindowTotal: Int? { displaySnapshot?.selectedScopeWindowTotal }
    public var selectedScopeTotal: Int? { displaySnapshot?.selectedScopeWindowTotal }
    public var selectedScopeWindowTotal: Int? { displaySnapshot?.selectedScopeWindowTotal }
    public var globalTotal: Int? { snapshot?.allProjectsWindowTotal }
    public var globalWindowTotal: Int? { snapshot?.allProjectsWindowTotal }
    public var allProjectsTotal: Int? { snapshot?.allProjectsWindowTotal }
    public var allProjectsWindowTotal: Int? { snapshot?.allProjectsWindowTotal }
    public var currentProjectCumulativeTotal: Int? { displaySnapshot?.currentProjectCumulativeTotal }

    public var accounts: [String] { displaySnapshot?.accounts ?? [] }
    public var currentProject: ProjectInfo? { displaySnapshot?.currentProject }
    public var activeAccount: String? { displaySnapshot?.activeAccount }
    public var rows: [UsageRow] { displaySnapshot?.rows ?? [] }
    public var visibleDetailFields: [String] { displaySnapshot?.availableDetailFields ?? [] }
    public var availableDetailFields: [String] { visibleDetailFields }

    /// Group rows by their complete display identity. The key is stable and
    /// human-readable, while the original rows remain authoritative.
    var groupedRows: [UsageGroupIdentity: [UsageRow]] {
        Dictionary(grouping: rows) { row in
            Self.groupKey(for: row)
        }
    }

    public var rowGroups: [UsageRowGroup] {
        groupedRows.keys.sorted(by: Self.groupIdentitySort).map { key in
            UsageRowGroup(id: key, rows: groupedRows[key] ?? [])
        }
    }

    public var isLoading: Bool { state == .loading }
    /// Whether the current controls have a matching snapshot suitable for
    /// display. The raw snapshot may still contain the previous selection so
    /// it must not drive popover content decisions.
    public var hasSnapshot: Bool { displaySnapshot != nil }
    public var hasRows: Bool { !rows.isEmpty }
    public var isEmpty: Bool { displaySnapshot != nil && rows.isEmpty }
    public var isEmptyState: Bool { isEmpty }
    public var hasNoData: Bool { isEmpty }
    public var showsEmptyState: Bool { isEmpty && state != .loading }

    private func selectionDidChange() {
        guard snapshotRequest != currentRequest || snapshot != nil else { return }
        refreshRequested = true
        state = .loading
        isStale = false

        // Property changes can originate from SwiftUI bindings as well as
        // callers. Schedule a refresh immediately; refresh() coalesces this
        // task with any in-flight load and always uses the latest selection.
        Task { [weak self] in
            await self?.refresh()
        }
    }

    private static func groupKey(for row: UsageRow) -> UsageGroupIdentity {
        UsageGroupIdentity(
            projectKey: row.projectKey,
            projectLabel: row.projectLabel,
            accountAlias: row.accountAlias,
            role: row.role,
            provider: row.provider,
            model: row.model
        )
    }

    private static func groupIdentitySort(_ lhs: UsageGroupIdentity, _ rhs: UsageGroupIdentity) -> Bool {
        [lhs.projectKey, lhs.projectLabel, lhs.accountAlias, lhs.role, lhs.provider, lhs.model]
            .lexicographicallyPrecedes([rhs.projectKey, rhs.projectLabel, rhs.accountAlias, rhs.role, rhs.provider, rhs.model])
    }
}
