import Foundation

/// Formats a token count using the compact notation used by the Python report.
///
/// Counts below one thousand are rendered exactly. Larger counts are rendered
/// with at most one fractional digit and a K/M/B suffix; a value that would
/// round to 1000K is promoted to 1M instead.
public func compactTokens(_ value: Int?) -> String? {
    guard let value else { return nil }
    guard value >= 1_000 else { return String(value) }

    let scales: [(divisor: Int, suffix: String)] = [
        (1_000_000_000, "B"),
        (1_000_000, "M"),
        (1_000, "K"),
    ]

    for scale in scales where value >= scale.divisor {
        // Round the displayed tenth with integer half-up arithmetic. This
        // mirrors the Python formatter without binary floating point or
        // banker's rounding (so 1,250 becomes 1.3K).
        let tenths = (value * 10 + scale.divisor / 2) / scale.divisor
        if scale.suffix == "K" && tenths >= 10_000 {
            return "1M"
        }
        let whole = tenths / 10
        let remainder = tenths % 10
        return remainder == 0
            ? "\(whole)\(scale.suffix)"
            : "\(whole).\(remainder)\(scale.suffix)"
    }

    return String(value)
}
