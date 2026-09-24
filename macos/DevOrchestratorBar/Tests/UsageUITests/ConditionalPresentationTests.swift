import XCTest
import UsageClient
@testable import UsageUI

final class ConditionalPresentationTests: XCTestCase {
    private func snapshot(
        detailFields: [String] = [],
        rows: [UsageRow] = [],
        malformedEventCount: Int = 0
    ) -> UsageSnapshot {
        UsageSnapshot(
            schemaVersion: 1,
            generatedAt: Date(timeIntervalSince1970: 1),
            window: "5h",
            windowStartedAt: Date(timeIntervalSince1970: 0),
            scope: .currentProject,
            currentProject: nil,
            selectedAccount: nil,
            accounts: [],
            activeAccount: nil,
            allProjectsWindowTotal: nil,
            selectedScopeWindowTotal: nil,
            currentProjectCumulativeTotal: nil,
            availableDetailFields: detailFields,
            rows: rows,
            diagnostics: UsageDiagnostics(malformedEventCount: malformedEventCount)
        )
    }

    private func row(input: Int? = nil, output: Int? = nil) -> UsageRow {
        UsageRow(
            projectKey: "demo",
            projectLabel: "Demo",
            accountAlias: "personal",
            role: "build",
            provider: "openai",
            model: "gpt",
            precision: "exact",
            usage: UsageTokens(
                inputTokens: input,
                cacheTokens: nil,
                outputTokens: output,
                thinkingTokens: nil,
                totalTokens: nil
            )
        )
    }

    func testHidesInputWhenNoUsefulInputDetailExists() {
        let noDetails = snapshot(detailFields: [], rows: [row(output: 12)])
        XCTAssertFalse(Presentation(snapshot: noDetails).showsInput)
    }

    func testShowsInputWhenAtLeastOneRowHasInputDetail() {
        let mixedDetails = snapshot(detailFields: ["input_tokens"], rows: [row(input: 12), row(output: 8)])
        XCTAssertTrue(Presentation(snapshot: mixedDetails).showsInput)
    }

    func testHidesDiagnosticsForCleanSnapshot() {
        let clean = snapshot(rows: [row(output: 12)])
        XCTAssertFalse(Presentation(snapshot: clean).showsDiagnostics)
    }

    func testShowsDiagnosticsForMalformedSnapshot() {
        let malformed = snapshot(rows: [row(output: 12)], malformedEventCount: 1)
        XCTAssertTrue(Presentation(snapshot: malformed).showsDiagnostics)
    }

    func testShowsEmptyStateForEmptySnapshot() {
        let empty = snapshot()
        XCTAssertTrue(Presentation(snapshot: empty).showsEmptyState)
    }
}
