import XCTest
@testable import UsageUI

final class CompactTokensTests: XCTestCase {
    func testCompactTokensUsesPythonCompatibleBoundaries() {
        XCTAssertEqual(compactTokens(nil), nil)
        XCTAssertEqual(compactTokens(999), "999")
        XCTAssertEqual(compactTokens(1_000), "1K")
        XCTAssertEqual(compactTokens(1_249), "1.2K")
        XCTAssertEqual(compactTokens(1_250), "1.3K")
        XCTAssertEqual(compactTokens(1_251), "1.3K")
        XCTAssertEqual(compactTokens(999_949), "999.9K")
        XCTAssertEqual(compactTokens(999_950), "1M")
        XCTAssertEqual(compactTokens(999_951), "1M")
    }
}
