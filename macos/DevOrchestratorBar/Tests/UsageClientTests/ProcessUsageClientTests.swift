import XCTest
@testable import UsageClient
#if canImport(Darwin)
import Darwin
#endif

final class ProcessUsageClientTests: XCTestCase {
    private final class CapturedBox: @unchecked Sendable {
        let lock = NSLock()
        var value: (URL, [String], [String: String], TimeInterval)?

        func snapshot() -> (URL, [String], [String: String], TimeInterval)? {
            lock.lock(); defer { lock.unlock() }
            return value
        }
    }

    private struct FakeRunner: CommandRunning {
        let result: Result<CommandResult, Error>
        let onRun: @Sendable (URL, [String], [String: String], TimeInterval) -> Void

        func run(executable: URL, arguments: [String], environment: [String: String], timeout: TimeInterval) async throws -> CommandResult {
            onRun(executable, arguments, environment, timeout)
            return try result.get()
        }
    }

    private let executable = URL(fileURLWithPath: "/tmp/dev-orchestrator-usage")

    private func waitForFile(_ url: URL, timeout: TimeInterval = 2) throws {
        let deadline = Date().addingTimeInterval(timeout)
        while !FileManager.default.fileExists(atPath: url.path) {
            if Date() >= deadline { throw NSError(domain: "UsageClientTests", code: 1) }
            Thread.sleep(forTimeInterval: 0.01)
        }
    }

    private func processIsAlive(_ pid: pid_t) -> Bool {
        #if canImport(Darwin)
        return kill(pid, 0) == 0
        #else
        return false
        #endif
    }

    private func payload(schemaVersion: Int = 1) -> Data {
        "{\"schema_version\":\(schemaVersion),\"generated_at\":\"2026-09-24T10:00:00Z\",\"window\":\"5h\",\"window_started_at\":\"2026-09-24T05:00:00Z\",\"scope\":\"all_projects\",\"current_project\":null,\"selected_account\":null,\"accounts\":[],\"active_account\":null,\"all_projects_window_total\":null,\"selected_scope_window_total\":null,\"current_project_cumulative_total\":null,\"available_detail_fields\":[],\"rows\":[],\"diagnostics\":{\"malformed_event_count\":0}}".data(using: .utf8)!
    }

    func testLoadsSnapshotUsingDirectCommandAndRestrictedPath() async throws {
        let captured = CapturedBox()
        let runner = FakeRunner(result: .success(CommandResult(status: 0, stdout: payload(), stderr: Data()))) {
            captured.lock.lock(); captured.value = ($0, $1, $2, $3); captured.lock.unlock()
        }
        let client = ProcessUsageClient(executable: executable, runner: runner, baseEnvironment: ["PATH": "/custom/bin", "LANG": "en_US"])

        let snapshot = try await client.load(UsageRequest(scope: .allProjects, account: "work"))
        XCTAssertEqual(snapshot.schemaVersion, 1)
        let value = captured.snapshot()
        XCTAssertEqual(value?.0, executable)
        XCTAssertEqual(value?.1, ["summary", "--scope", "all_projects", "--window", "5h", "--account", "work"])
        XCTAssertEqual(value?.2["PATH"], "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/custom/bin")
        XCTAssertEqual(value?.2["LANG"], "en_US")
        XCTAssertEqual(value?.3, 5)
    }

    func testNonzeroExitIncludesBoundedStderr() async {
        let stderr = String(repeating: "x", count: 5000).data(using: .utf8)!
        let runner = FakeRunner(result: .success(CommandResult(status: 7, stdout: Data(), stderr: stderr))) { _, _, _, _ in }
        do {
            _ = try await ProcessUsageClient(executable: executable, runner: runner).load(UsageRequest())
            XCTFail("expected command failure")
        } catch let error as UsageClientError {
            guard case let .commandFailed(status, message) = error else { return XCTFail("unexpected error: \(error)") }
            XCTAssertEqual(status, 7)
            XCTAssertEqual(message.utf8.count, 4096)
        } catch { XCTFail("unexpected error: \(error)") }
    }

    func testMalformedJSONIsMapped() async {
        let runner = FakeRunner(result: .success(CommandResult(status: 0, stdout: Data("not-json".utf8), stderr: Data()))) { _, _, _, _ in }
        do {
            _ = try await ProcessUsageClient(executable: executable, runner: runner).load(UsageRequest())
            XCTFail("expected malformed output")
        } catch let error as UsageClientError {
            guard case .invalidJSON = error else { return XCTFail("unexpected error: \(error)") }
        } catch { XCTFail("unexpected error: \(error)") }
    }

    func testUnsupportedSchemaIsRejected() async {
        let runner = FakeRunner(result: .success(CommandResult(status: 0, stdout: payload(schemaVersion: 2), stderr: Data()))) { _, _, _, _ in }
        do {
            _ = try await ProcessUsageClient(executable: executable, runner: runner).load(UsageRequest())
            XCTFail("expected unsupported schema")
        } catch let error as UsageClientError {
            guard case let .unsupportedSchema(version) = error else { return XCTFail("unexpected error: \(error)") }
            XCTAssertEqual(version, 2)
        } catch { XCTFail("unexpected error: \(error)") }
    }

    func testTimeoutIsPreserved() async {
        let runner = FakeRunner(result: .failure(UsageClientError.timeout)) { _, _, _, _ in }
        do {
            _ = try await ProcessUsageClient(executable: executable, runner: runner).load(UsageRequest())
            XCTFail("expected timeout")
        } catch let error as UsageClientError {
            guard case .timeout = error else { return XCTFail("unexpected error: \(error)") }
        } catch { XCTFail("unexpected error: \(error)") }
    }

    func testRealRunnerDrainsLargeStdoutAndStderrBeforeReturning() async throws {
        let outputSize = 128 * 1024
        let source = #"""
        import sys
        sys.stdout.write("o" * 131072)
        sys.stderr.write("e" * 131072)
        """#
        let operation = Task<Result<CommandResult, Error>, Never> {
            do {
                return .success(try await ProcessCommandRunner().run(
                    executable: URL(fileURLWithPath: "/usr/bin/python3"),
                    arguments: ["-c", source],
                    environment: ProcessInfo.processInfo.environment,
                    timeout: 1
                ))
            } catch {
                return .failure(error)
            }
        }
        let result = await operation.value
        guard case let .success(commandResult) = result else {
            return XCTFail("expected successful process completion, got \(result)")
        }
        XCTAssertEqual(commandResult.status, 0)
        XCTAssertEqual(commandResult.stdout.count, outputSize)
        XCTAssertEqual(commandResult.stderr.count, 4096)
        XCTAssertEqual(commandResult.stdout.first, UInt8(ascii: "o"))
        XCTAssertEqual(commandResult.stderr.first, UInt8(ascii: "e"))
    }

    func testRealRunnerKillsSIGTERMResistantProcessBeforeThrowingTimeout() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("dev-orchestrator-timeout-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let pidFile = directory.appendingPathComponent("pid")
        let source = #"""
        printf '%s' "$$" > "$PID_FILE"
        trap '' TERM
        while :; do :; done
        """#
        defer {
            if let pid = try? Int32(String(contentsOf: pidFile)), processIsAlive(pid_t(pid)) {
                #if canImport(Darwin)
                _ = kill(pid_t(pid), SIGKILL)
                #endif
            }
            try? FileManager.default.removeItem(at: directory)
        }

        let operation = Task<Result<CommandResult, Error>, Never> {
            do {
                let environment = ["PID_FILE": pidFile.path]
                return .success(try await ProcessCommandRunner().run(
                    executable: URL(fileURLWithPath: "/bin/sh"),
                    arguments: ["-c", source],
                    environment: environment,
                    timeout: 0.2
                ))
            } catch {
                return .failure(error)
            }
        }
        try waitForFile(pidFile)
        let result = await operation.value
        guard case let .failure(error) = result else {
            return XCTFail("expected timeout")
        }
        guard case ProcessCommandError.timedOut = error else {
            XCTFail("expected timeout, got \(error)")
            return
        }
        let pid = Int32(try String(contentsOf: pidFile).trimmingCharacters(in: .whitespacesAndNewlines))!
        XCTAssertFalse(processIsAlive(pid_t(pid)), "timed out process is still alive")
    }
}
