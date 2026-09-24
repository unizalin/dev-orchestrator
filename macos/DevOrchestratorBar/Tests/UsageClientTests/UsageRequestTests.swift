import XCTest
@testable import UsageClient

final class UsageRequestTests: XCTestCase {
    func testBuildsSummaryArgumentsForAccount() {
        XCTAssertEqual(
            UsageRequest(scope: .allProjects, account: "work").arguments,
            ["summary", "--scope", "all_projects", "--window", "5h", "--account", "work"]
        )
    }

    func testOmitsEmptyOptionalArguments() {
        let request = UsageRequest(scope: .currentProject, window: "1h", account: "", projectPath: "")
        XCTAssertEqual(request.arguments, ["summary", "--scope", "current_project", "--window", "1h"])
    }
}
