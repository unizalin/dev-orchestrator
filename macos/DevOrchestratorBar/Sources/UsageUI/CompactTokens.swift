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
        // The product's compact formatter rounds a half tenth away from zero
        // (so 1,250 becomes 1.3K), rather than relying on binary floating
        // point formatting's tie-breaking behavior.
        if scale.suffix == "K" && value >= 999_950 {
            return "1M"
        }
        let tenths = Int((Double(value) * 10.0 / Double(scale.divisor)).rounded(.toNearestOrAwayFromZero))
        let whole = tenths / 10
        let remainder = tenths % 10
        return remainder == 0
            ? "\(whole)\(scale.suffix)"
            : "\(whole).\(remainder)\(scale.suffix)"
    }

    return String(value)
}
