import Foundation
#if canImport(Darwin)
import Darwin
#endif

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

internal enum ProcessCommandError: Error, Equatable, Sendable {
    case timedOut
}

private final class ProcessCommandRunState: @unchecked Sendable {
    private let lock = NSLock()
    private let process: Process
    private let stdoutHandle: FileHandle
    private let stderrHandle: FileHandle
    private let continuation: CheckedContinuation<CommandResult, Error>
    private var didStartDraining = false
    private var didTerminate = false
    private var terminationStatus: Int32 = 0
    private var stdoutFinished = false
    private var stderrFinished = false
    private var stdout = Data()
    private var stderr = Data()
    private var timedOut = false
    private var completed = false
    private var timeoutWorkItem: DispatchWorkItem?
    private var graceWorkItem: DispatchWorkItem?

    init(
        process: Process,
        stdoutHandle: FileHandle,
        stderrHandle: FileHandle,
        continuation: CheckedContinuation<CommandResult, Error>
    ) {
        self.process = process
        self.stdoutHandle = stdoutHandle
        self.stderrHandle = stderrHandle
        self.continuation = continuation
    }

    func startDraining(timeout: TimeInterval) {
        let timeoutWorkItem = DispatchWorkItem { [weak self] in
            self?.timeoutFired()
        }

        lock.lock()
        didStartDraining = true
        self.timeoutWorkItem = timeoutWorkItem
        let processAlreadyTerminated = didTerminate
        lock.unlock()

        DispatchQueue.global(qos: .userInitiated).async { [self] in
            let data = Self.drain(stdoutHandle, retainingAtMost: nil)
            stdoutDidFinish(data)
        }
        DispatchQueue.global(qos: .userInitiated).async { [self] in
            let data = Self.drain(stderrHandle, retainingAtMost: 4096)
            stderrDidFinish(data)
        }

        if processAlreadyTerminated {
            timeoutWorkItem.cancel()
        } else {
            let delay = max(0, timeout)
            DispatchQueue.global(qos: .userInitiated).asyncAfter(
                deadline: .now() + delay,
                execute: timeoutWorkItem
            )
        }
        finishIfReady()
    }

    func processDidTerminate(status: Int32) {
        lock.lock()
        didTerminate = true
        terminationStatus = status
        lock.unlock()
        finishIfReady()
    }

    private func stdoutDidFinish(_ data: Data) {
        lock.lock()
        stdout = data
        stdoutFinished = true
        lock.unlock()
        finishIfReady()
    }

    private func stderrDidFinish(_ data: Data) {
        lock.lock()
        stderr = data
        stderrFinished = true
        lock.unlock()
        finishIfReady()
    }

    private func timeoutFired() {
        lock.lock()
        guard !completed, !didTerminate else {
            lock.unlock()
            return
        }
        guard process.isRunning else {
            lock.unlock()
            return
        }
        timedOut = true
        let graceWorkItem = DispatchWorkItem { [weak self] in
            self?.gracePeriodExpired()
        }
        self.graceWorkItem = graceWorkItem
        lock.unlock()

        process.terminate()
        DispatchQueue.global(qos: .userInitiated).asyncAfter(
            deadline: .now() + 0.25,
            execute: graceWorkItem
        )
        finishIfReady()
    }

    private func gracePeriodExpired() {
        lock.lock()
        guard !completed, !didTerminate else {
            lock.unlock()
            return
        }
        let shouldKill = process.isRunning
        lock.unlock()

        guard shouldKill else { return }
        #if canImport(Darwin)
        _ = kill(process.processIdentifier, SIGKILL)
        #else
        process.terminate()
        #endif
    }

    private func finishIfReady() {
        let result: Result<CommandResult, Error>?

        lock.lock()
        guard !completed, didStartDraining, didTerminate, stdoutFinished, stderrFinished else {
            lock.unlock()
            return
        }
        completed = true
        timeoutWorkItem?.cancel()
        graceWorkItem?.cancel()
        if timedOut {
            result = .failure(ProcessCommandError.timedOut)
        } else {
            result = .success(CommandResult(status: terminationStatus, stdout: stdout, stderr: stderr))
        }
        lock.unlock()

        process.terminationHandler = nil
        continuation.resume(with: result!)
    }

    private static func drain(_ handle: FileHandle, retainingAtMost limit: Int?) -> Data {
        var retained = Data()
        while true {
            let chunk = handle.readData(ofLength: 64 * 1024)
            guard !chunk.isEmpty else { break }

            guard let limit else {
                retained.append(chunk)
                continue
            }

            let remaining = limit - retained.count
            guard remaining > 0 else { continue }
            retained.append(chunk.prefix(remaining))
        }
        return retained
    }
}

internal struct ProcessCommandRunner: CommandRunning {
    func run(executable: URL, arguments: [String], environment: [String: String], timeout: TimeInterval) async throws -> CommandResult {
        try await withCheckedThrowingContinuation { continuation in
            let process = Process()
            process.executableURL = executable
            process.arguments = arguments
            process.environment = environment
            let stdoutPipe = Pipe()
            let stderrPipe = Pipe()
            process.standardOutput = stdoutPipe
            process.standardError = stderrPipe
            let state = ProcessCommandRunState(
                process: process,
                stdoutHandle: stdoutPipe.fileHandleForReading,
                stderrHandle: stderrPipe.fileHandleForReading,
                continuation: continuation
            )

            process.terminationHandler = { process in
                state.processDidTerminate(status: process.terminationStatus)
            }

            do {
                try process.run()
            } catch {
                process.terminationHandler = nil
                stdoutPipe.fileHandleForReading.closeFile()
                stderrPipe.fileHandleForReading.closeFile()
                continuation.resume(throwing: error)
                return
            }

            // The parent must close its write ends so the drainers observe EOF
            // once the child closes its descriptors.
            stdoutPipe.fileHandleForWriting.closeFile()
            stderrPipe.fileHandleForWriting.closeFile()
            state.startDraining(timeout: timeout)
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
