import Foundation

public extension JSONDecoder {
    static var usageDecoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }
}

public enum ProjectScope: String, CaseIterable, Sendable, Codable {
    case currentProject = "current_project"
    case allProjects = "all_projects"
}

public struct ProjectInfo: Decodable, Equatable, Sendable {
    public let key: String
    public let label: String

    public init(key: String, label: String) {
        self.key = key
        self.label = label
    }
}

public struct UsageTokens: Decodable, Equatable, Sendable {
    public let inputTokens: Int?
    public let cacheTokens: Int?
    public let outputTokens: Int?
    public let thinkingTokens: Int?
    public let totalTokens: Int?

    public init(inputTokens: Int?, cacheTokens: Int?, outputTokens: Int?, thinkingTokens: Int?, totalTokens: Int?) {
        self.inputTokens = inputTokens
        self.cacheTokens = cacheTokens
        self.outputTokens = outputTokens
        self.thinkingTokens = thinkingTokens
        self.totalTokens = totalTokens
    }
}

public struct UsageRow: Decodable, Equatable, Sendable {
    public let projectKey: String
    public let projectLabel: String
    public let accountAlias: String
    public let role: String
    public let provider: String
    public let model: String
    public let precision: String
    public let usage: UsageTokens

    public init(projectKey: String, projectLabel: String, accountAlias: String, role: String, provider: String, model: String, precision: String, usage: UsageTokens) {
        self.projectKey = projectKey
        self.projectLabel = projectLabel
        self.accountAlias = accountAlias
        self.role = role
        self.provider = provider
        self.model = model
        self.precision = precision
        self.usage = usage
    }
}

public struct UsageDiagnostics: Decodable, Equatable, Sendable {
    public let malformedEventCount: Int

    public init(malformedEventCount: Int) {
        self.malformedEventCount = malformedEventCount
    }
}

public struct UsageSnapshot: Decodable, Equatable, Sendable {
    public let schemaVersion: Int
    public let generatedAt: Date
    public let window: String
    public let windowStartedAt: Date
    public let scope: ProjectScope
    public let currentProject: ProjectInfo?
    public let selectedAccount: String?
    public let accounts: [String]
    public let activeAccount: String?
    public let allProjectsWindowTotal: Int?
    public let selectedScopeWindowTotal: Int?
    public let currentProjectCumulativeTotal: Int?
    public let availableDetailFields: [String]
    public let rows: [UsageRow]
    public let diagnostics: UsageDiagnostics

    public init(schemaVersion: Int, generatedAt: Date, window: String, windowStartedAt: Date, scope: ProjectScope, currentProject: ProjectInfo?, selectedAccount: String?, accounts: [String], activeAccount: String?, allProjectsWindowTotal: Int?, selectedScopeWindowTotal: Int?, currentProjectCumulativeTotal: Int?, availableDetailFields: [String], rows: [UsageRow], diagnostics: UsageDiagnostics) {
        self.schemaVersion = schemaVersion
        self.generatedAt = generatedAt
        self.window = window
        self.windowStartedAt = windowStartedAt
        self.scope = scope
        self.currentProject = currentProject
        self.selectedAccount = selectedAccount
        self.accounts = accounts
        self.activeAccount = activeAccount
        self.allProjectsWindowTotal = allProjectsWindowTotal
        self.selectedScopeWindowTotal = selectedScopeWindowTotal
        self.currentProjectCumulativeTotal = currentProjectCumulativeTotal
        self.availableDetailFields = availableDetailFields
        self.rows = rows
        self.diagnostics = diagnostics
    }
}

public typealias TokenUsage = UsageTokens
