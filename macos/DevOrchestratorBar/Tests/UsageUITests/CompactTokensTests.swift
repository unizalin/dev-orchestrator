import XCTest
@testable import UsageUI

final class CompactTokensTests: XCTestCase {
    func testCompactTokensUsesPythonCompatibleBoundaries() {
        XCTAssertEqual(compactTokens(nil), nil)
        XCTAssertEqual(compactTokens(999), "999")
        XCTAssertEqual(compactTokens(1_000), "1K")
        XCTAssertEqual(compactTokens(1_250), "1.3K")
        XCTAssertEqual(compactTokens(999_950), "1M")
    }
}
