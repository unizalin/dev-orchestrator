import Foundation

public struct CommandResult: Sendable {
    public let status: Int32
    public let stdout: Data
    public let stderr: Data

    public init(status: Int32, stdout: Data, stderr: Data) {
        self.status = status
        self.stdout = stdout
        self.stderr = stderr
    }
}

public protocol CommandRunning: Sendable {
    func run(executable: URL, arguments: [String], environment: [String: String], timeout: TimeInterval) async throws -> CommandResult
}

public protocol UsageLoading: Sendable {
    func load(_ request: UsageRequest) async throws -> UsageSnapshot
}

public enum UsageClientError: Error, Equatable, Sendable {
    case commandFailed(status: Int32, stderr: String)
    case invalidJSON(String)
    case unsupportedSchema(Int)
    case timeout
    case executionFailed(String)
}

private enum ProcessCommandError: Error {
    case timedOut
}

private final class ProcessCompletion: @unchecked Sendable {
    private let lock = NSLock()
    private var completed = false
    private let continuation: CheckedContinuation<CommandResult, Error>

    init(_ continuation: CheckedContinuation<CommandResult, Error>) {
        self.continuation = continuation
    }

    func finish(_ result: Result<CommandResult, Error>) {
        lock.lock()
        guard !completed else { lock.unlock(); return }
        completed = true
        lock.unlock()
        continuation.resume(with: result)
    }
}

private struct ProcessCommandRunner: CommandRunning {
    func run(executable: URL, arguments: [String], environment: [String: String], timeout: TimeInterval) async throws -> CommandResult {
        try await withCheckedThrowingContinuation { continuation in
            let completion = ProcessCompletion(continuation)
            let process = Process()
            process.executableURL = executable
            process.arguments = arguments
            process.environment = environment
            let stdoutPipe = Pipe()
            let stderrPipe = Pipe()
            process.standardOutput = stdoutPipe
            process.standardError = stderrPipe

            process.terminationHandler = { process in
                let result = CommandResult(status: process.terminationStatus, stdout: stdoutPipe.fileHandleForReading.readDataToEndOfFile(), stderr: stderrPipe.fileHandleForReading.readDataToEndOfFile())
                completion.finish(.success(result))
            }

            do {
                try process.run()
            } catch {
                completion.finish(.failure(error))
                return
            }

            DispatchQueue.global().asyncAfter(deadline: .now() + timeout) {
                guard process.isRunning else { return }
                process.terminate()
                completion.finish(.failure(ProcessCommandError.timedOut))
            }
        }
    }
}

public final class ProcessUsageClient: UsageLoading, @unchecked Sendable {
    public static let timeout: TimeInterval = 5
    public static let allowedPathPrefix = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

    private let executable: URL
    private let runner: any CommandRunning
    private let baseEnvironment: [String: String]

    public init(executable: URL, runner: any CommandRunning, baseEnvironment: [String: String] = ProcessInfo.processInfo.environment) {
        self.executable = executable
        self.runner = runner
        self.baseEnvironment = baseEnvironment
    }

    public convenience init(executable: URL, baseEnvironment: [String: String] = ProcessInfo.processInfo.environment) {
        self.init(executable: executable, runner: ProcessCommandRunner(), baseEnvironment: baseEnvironment)
    }

    public convenience init(executable: URL, commandRunner: any CommandRunning, environment: [String: String] = ProcessInfo.processInfo.environment) {
        self.init(executable: executable, runner: commandRunner, baseEnvironment: environment)
    }

    public convenience init(helperURL: URL, runner: any CommandRunning, baseEnvironment: [String: String] = ProcessInfo.processInfo.environment) {
        self.init(executable: helperURL, runner: runner, baseEnvironment: baseEnvironment)
    }

    public convenience init(helperURL: URL, baseEnvironment: [String: String] = ProcessInfo.processInfo.environment) {
        self.init(executable: helperURL, runner: ProcessCommandRunner(), baseEnvironment: baseEnvironment)
    }

    public convenience init(helperURL: URL, commandRunner: any CommandRunning, environment: [String: String] = ProcessInfo.processInfo.environment) {
        self.init(executable: helperURL, runner: commandRunner, baseEnvironment: environment)
    }

    public func load(_ request: UsageRequest) async throws -> UsageSnapshot {
        var environment = baseEnvironment
        let existingPath = environment["PATH"] ?? ""
        environment["PATH"] = existingPath.isEmpty ? Self.allowedPathPrefix : Self.allowedPathPrefix + ":" + existingPath

        let result: CommandResult
        do {
            result = try await runner.run(executable: executable, arguments: request.arguments, environment: environment, timeout: Self.timeout)
        } catch let error as UsageClientError {
            throw error
        } catch ProcessCommandError.timedOut {
            throw UsageClientError.timeout
        } catch {
            throw UsageClientError.executionFailed(String(describing: error))
        }

        guard result.status == 0 else {
            throw UsageClientError.commandFailed(status: result.status, stderr: Self.boundedStderr(result.stderr))
        }
        let snapshot: UsageSnapshot
        do {
            snapshot = try JSONDecoder.usageDecoder.decode(UsageSnapshot.self, from: result.stdout)
        } catch {
            throw UsageClientError.invalidJSON(String(describing: error))
        }
        guard snapshot.schemaVersion == 1 else {
            throw UsageClientError.unsupportedSchema(snapshot.schemaVersion)
        }
        return snapshot
    }

    private static func boundedStderr(_ data: Data) -> String {
        let bounded = data.prefix(4096)
        return String(decoding: bounded, as: UTF8.self)
    }
}
