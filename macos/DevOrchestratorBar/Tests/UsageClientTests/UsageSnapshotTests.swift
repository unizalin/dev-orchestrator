import XCTest
@testable import UsageClient

final class UsageSnapshotTests: XCTestCase {
    func testDecodesPythonISO8601FractionalSecondsAndOffset() throws {
        let fixture = #"""
        {
          "schema_version": 1,
          "generated_at": "2026-09-24T10:00:00.123456+00:00",
          "window": "5h",
          "window_started_at": "2026-09-24T05:00:00+00:00",
          "scope": "all_projects",
          "current_project": null,
          "selected_account": null,
          "accounts": [],
          "active_account": null,
          "all_projects_window_total": null,
          "selected_scope_window_total": null,
          "current_project_cumulative_total": null,
          "available_detail_fields": [],
          "rows": [],
          "diagnostics": {"malformed_event_count": 0}
        }
        """#.data(using: .utf8)!

        let snapshot = try JSONDecoder.usageDecoder.decode(UsageSnapshot.self, from: fixture)
        XCTAssertEqual(snapshot.generatedAt.timeIntervalSince1970, 1_790_244_000.123456, accuracy: 0.000001)
        XCTAssertEqual(snapshot.windowStartedAt.timeIntervalSince1970, 1_790_226_000, accuracy: 0.000001)
    }

    func testDecodesPythonISO8601NonFractionalOffset() throws {
        let fixture = #"{"schema_version":1,"generated_at":"2026-09-24T18:00:00+08:00","window":"5h","window_started_at":"2026-09-24T13:00:00+08:00","scope":"all_projects","current_project":null,"selected_account":null,"accounts":[],"active_account":null,"all_projects_window_total":null,"selected_scope_window_total":null,"current_project_cumulative_total":null,"available_detail_fields":[],"rows":[],"diagnostics":{"malformed_event_count":0}}"#.data(using: .utf8)!

        let snapshot = try JSONDecoder.usageDecoder.decode(UsageSnapshot.self, from: fixture)
        XCTAssertEqual(snapshot.generatedAt.timeIntervalSince1970, 1_790_244_000, accuracy: 0.000001)
        XCTAssertEqual(snapshot.windowStartedAt.timeIntervalSince1970, 1_790_226_000, accuracy: 0.000001)
    }

    func testDecodesSummaryContract() throws {
        let fixture = #"""
        {
          "schema_version": 1,
          "generated_at": "2026-09-24T10:00:00Z",
          "window": "5h",
          "window_started_at": "2026-09-24T05:00:00Z",
          "scope": "all_projects",
          "current_project": {"key": "repo", "label": "Repository"},
          "selected_account": "work",
          "accounts": ["personal", "work"],
          "active_account": "work",
          "all_projects_window_total": 160,
          "selected_scope_window_total": 160,
          "current_project_cumulative_total": 120,
          "available_detail_fields": ["input_tokens", "output_tokens"],
          "rows": [
            {"project_key":"repo","project_label":"Repository","account_alias":"work","role":"implement","provider":"openai","model":"gpt","precision":"exact","usage":{"input_tokens":100,"cache_tokens":null,"output_tokens":20,"thinking_tokens":null,"total_tokens":120}},
            {"project_key":"other","project_label":"Other","account_alias":"personal","role":"review","provider":"openai","model":"gpt","precision":"unavailable","usage":{"input_tokens":null,"cache_tokens":null,"output_tokens":null,"thinking_tokens":null,"total_tokens":40}}
          ],
          "diagnostics": {"malformed_event_count": 1}
        }
        """#.data(using: .utf8)!

        let snapshot = try JSONDecoder.usageDecoder.decode(UsageSnapshot.self, from: fixture)
        XCTAssertEqual(snapshot.schemaVersion, 1)
        XCTAssertEqual(snapshot.allProjectsWindowTotal, 160)
        XCTAssertNil(snapshot.rows[1].usage.inputTokens)
        XCTAssertEqual(snapshot.diagnostics.malformedEventCount, 1)
        XCTAssertEqual(snapshot.scope, .allProjects)
        XCTAssertEqual(snapshot.accounts, ["personal", "work"])
    }
}
