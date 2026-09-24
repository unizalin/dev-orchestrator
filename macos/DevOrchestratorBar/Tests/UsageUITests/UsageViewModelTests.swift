import XCTest
import UsageClient
@testable import UsageUI

final class UsageViewModelTests: XCTestCase {
    private enum SampleError: Error, Equatable {
        case failed
    }

    private final class QueuedLoader: UsageLoading, @unchecked Sendable {
        private let lock = NSLock()
        private var queue: [Result<UsageSnapshot, Error>]
        private var requestsStorage: [UsageRequest] = []
        private let delayNanoseconds: UInt64

        init(_ queue: [Result<UsageSnapshot, Error>] = [], delayNanoseconds: UInt64 = 0) {
            self.queue = queue
            self.delayNanoseconds = delayNanoseconds
        }

        func enqueue(_ result: Result<UsageSnapshot, Error>) {
            lock.lock()
            queue.append(result)
            lock.unlock()
        }

        func load(_ request: UsageRequest) async throws -> UsageSnapshot {
            let result = dequeue(request)
            if delayNanoseconds > 0 {
                try await Task.sleep(nanoseconds: delayNanoseconds)
            }
            guard let result else {
                throw SampleError.failed
            }
            return try result.get()
        }

        private func dequeue(_ request: UsageRequest) -> Result<UsageSnapshot, Error>? {
            lock.lock()
            requestsStorage.append(request)
            let result = queue.isEmpty ? nil : queue.removeFirst()
            lock.unlock()
            return result
        }

        var requests: [UsageRequest] {
            lock.lock()
            defer { lock.unlock() }
            return requestsStorage
        }
    }

    private func snapshot(
        allProjectsTotal: Int? = 999,
        selectedTotal: Int? = 10,
        scope: ProjectScope = .currentProject,
        selectedAccount: String? = nil,
        rows: [UsageRow]? = nil
    ) -> UsageSnapshot {
        UsageSnapshot(
            schemaVersion: 1,
            generatedAt: Date(timeIntervalSince1970: 1),
            window: "5h",
            windowStartedAt: Date(timeIntervalSince1970: 0),
            scope: scope,
            currentProject: ProjectInfo(key: "demo", label: "Demo"),
            selectedAccount: selectedAccount,
            accounts: ["personal", "work"],
            activeAccount: "work",
            allProjectsWindowTotal: allProjectsTotal,
            selectedScopeWindowTotal: selectedTotal,
            currentProjectCumulativeTotal: 11,
            availableDetailFields: ["input_tokens", "output_tokens"],
            rows: rows ?? [
                UsageRow(
                    projectKey: "demo",
                    projectLabel: "Demo",
                    accountAlias: "work",
                    role: "build",
                    provider: "openai",
                    model: "gpt",
                    precision: "exact",
                    usage: UsageTokens(inputTokens: 5, cacheTokens: nil, outputTokens: 5, thinkingTokens: nil, totalTokens: 10)
                )
            ],
            diagnostics: UsageDiagnostics(malformedEventCount: 0)
        )
    }

    @MainActor
    func testRefreshKeepsLastGoodSnapshotAndMarksItStaleAfterFailure() async {
        let first = snapshot()
        let loader = QueuedLoader([.success(first)])
        let model = UsageViewModel(loader: loader)

        await model.refresh()
        XCTAssertEqual(model.snapshot, first)
        XCTAssertEqual(model.state, .loaded)
        loader.enqueue(.failure(SampleError.failed))
        await model.refresh()
        XCTAssertEqual(model.snapshot, first)
        XCTAssertTrue(model.isStale)
        XCTAssertEqual(model.state, .failed(SampleError.failed.localizedDescription))
    }

    @MainActor
    func testDefaultsAndFilterChangesBuildRequests() async {
        let first = snapshot()
        let loader = QueuedLoader([.success(first), .success(first), .success(first)])
        let model = UsageViewModel(loader: loader)
        XCTAssertEqual(model.scope, .currentProject)
        XCTAssertNil(model.selectedAccount)

        await model.refresh()
        model.scope = .allProjects
        model.selectedAccount = "work"
        await model.refresh()
        XCTAssertEqual(loader.requests.last, UsageRequest(scope: .allProjects, account: "work"))
    }

    @MainActor
    func testOverlappingRefreshesAreIgnored() async {
        let first = snapshot()
        let loader = QueuedLoader([.success(first)], delayNanoseconds: 50_000_000)
        let model = UsageViewModel(loader: loader)
        async let firstRefresh: Void = model.refresh()
        try? await Task.sleep(nanoseconds: 1_000_000)
        async let secondRefresh: Void = model.refresh()
        _ = await (firstRefresh, secondRefresh)
        XCTAssertEqual(loader.requests.count, 1)
    }

    @MainActor
    func testMenuBarTitleUsesGlobalTotalRegardlessOfSelectedScope() async {
        let loader = QueuedLoader([.success(snapshot(allProjectsTotal: 1_250, selectedTotal: 10))])
        let model = UsageViewModel(loader: loader)
        await model.refresh()
        XCTAssertEqual(model.menuBarTitle, "1.3K")
    }

    @MainActor
    func testPresentationDerivationsUseSnapshotFieldsWithoutRecomputingTotals() async {
        let loaded = snapshot(allProjectsTotal: 120, selectedTotal: 12)
        let loader = QueuedLoader([.success(loaded)])
        let model = UsageViewModel(loader: loader)
        await model.refresh()

        XCTAssertEqual(model.selectedTotal, 12)
        XCTAssertEqual(model.globalTotal, 120)
        XCTAssertEqual(model.accounts, ["personal", "work"])
        XCTAssertEqual(model.visibleDetailFields, ["input_tokens", "output_tokens"])
        XCTAssertEqual(model.groupedRows.count, 1)
        XCTAssertFalse(model.isEmpty)

        let empty = snapshot(rows: [])
        let emptyLoader = QueuedLoader([.success(empty)])
        let emptyModel = UsageViewModel(loader: emptyLoader)
        await emptyModel.refresh()
        XCTAssertTrue(emptyModel.isEmpty)
        XCTAssertTrue(emptyModel.showsEmptyState)
    }
}
