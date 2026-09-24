import Foundation

public struct UsageRequest: Equatable, Sendable {
    public var scope: ProjectScope = .currentProject
    public var window = "5h"
    public var account: String?
    public var projectPath: String?

    public init(scope: ProjectScope = .currentProject, window: String = "5h", account: String? = nil, projectPath: String? = nil) {
        self.scope = scope
        self.window = window
        self.account = account
        self.projectPath = projectPath
    }

    public var arguments: [String] {
        var value = ["summary", "--scope", scope.rawValue, "--window", window]
        if let account, !account.isEmpty { value += ["--account", account] }
        if let projectPath, !projectPath.isEmpty { value += ["--project-path", projectPath] }
        return value
    }
}
