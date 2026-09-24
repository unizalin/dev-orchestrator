import Foundation

public extension JSONDecoder {
    static var usageDecoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let value = try container.decode(String.self)
            guard let date = UsageISO8601Date.parse(value) else {
                throw DecodingError.dataCorruptedError(
                    in: container,
                    debugDescription: "Expected an ISO-8601 timestamp with a timezone"
                )
            }
            return date
        }
        return decoder
    }
}

private enum UsageISO8601Date {
    private static var utcCalendar: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.locale = Locale(identifier: "en_US_POSIX")
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        return calendar
    }()

    static func parse(_ value: String) -> Date? {
        let bytes = Array(value.utf8)
        guard bytes.count >= 20,
              bytes[4] == 45,
              bytes[7] == 45,
              bytes[10] == 84,
              bytes[13] == 58,
              bytes[16] == 58
        else {
            return nil
        }

        let timezoneStart: Int
        let offsetSeconds: Int
        if bytes.last == 90 || bytes.last == 122 { // Z / z
            timezoneStart = bytes.count - 1
            offsetSeconds = 0
        } else {
            guard let sign = bytes[19...].firstIndex(where: { $0 == 43 || $0 == 45 }) else {
                return nil
            }
            let timezone = Array(bytes[sign...])
            guard timezone.count == 6 || timezone.count == 5,
                  timezone[0] == 43 || timezone[0] == 45
            else {
                return nil
            }

            let hasColon = timezone.count == 6
            let hourIndex = 1
            let minuteIndex = hasColon ? 4 : 3
            if hasColon && timezone[3] != 58 {
                return nil
            }
            guard let hour = parseInteger(timezone, start: hourIndex, count: 2),
                  let minute = parseInteger(timezone, start: minuteIndex, count: 2),
                  hour <= 23,
                  minute <= 59
            else {
                return nil
            }
            timezoneStart = sign
            let magnitude = hour * 60 * 60 + minute * 60
            offsetSeconds = timezone[0] == 45 ? -magnitude : magnitude
        }

        guard timezoneStart >= 19 else { return nil }
        let fractionDigits: ArraySlice<UInt8>
        if timezoneStart > 19 {
            guard bytes[19] == 46, timezoneStart > 20 else { return nil }
            fractionDigits = bytes[20..<timezoneStart]
            guard fractionDigits.allSatisfy({ $0 >= 48 && $0 <= 57 }) else { return nil }
        } else {
            fractionDigits = []
        }

        guard let year = parseInteger(bytes, start: 0, count: 4),
              let month = parseInteger(bytes, start: 5, count: 2),
              let day = parseInteger(bytes, start: 8, count: 2),
              let hour = parseInteger(bytes, start: 11, count: 2),
              let minute = parseInteger(bytes, start: 14, count: 2),
              let second = parseInteger(bytes, start: 17, count: 2)
        else {
            return nil
        }

        var components = DateComponents()
        components.year = year
        components.month = month
        components.day = day
        components.hour = hour
        components.minute = minute
        components.second = second
        components.nanosecond = nanoseconds(from: fractionDigits)

        guard let date = utcCalendar.date(from: components) else { return nil }
        return date.addingTimeInterval(-TimeInterval(offsetSeconds))
    }

    private static func parseInteger<C: Collection>(_ bytes: C, start: Int, count: Int) -> Int? where C.Element == UInt8 {
        let values = Array(bytes)
        guard start >= 0, start + count <= values.count else { return nil }
        var value = 0
        for byte in values[start..<(start + count)] {
            guard byte >= 48 && byte <= 57 else { return nil }
            value = value * 10 + Int(byte - 48)
        }
        return value
    }

    private static func nanoseconds(from digits: ArraySlice<UInt8>) -> Int {
        guard !digits.isEmpty else { return 0 }
        var value = 0
        var count = 0
        for byte in digits {
            guard count < 9 else { break }
            value = value * 10 + Int(byte - 48)
            count += 1
        }
        while count < 9 {
            value *= 10
            count += 1
        }
        return value
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
