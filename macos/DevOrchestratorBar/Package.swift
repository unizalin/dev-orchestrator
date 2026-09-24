// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "DevOrchestratorBar",
    platforms: [.macOS(.v13)],
    products: [
        .library(name: "UsageClient", targets: ["UsageClient"]),
        .library(name: "UsageUI", targets: ["UsageUI"]),
        .executable(name: "DevOrchestratorBar", targets: ["DevOrchestratorBar"]),
    ],
    targets: [
        .target(name: "UsageClient"),
        .target(name: "UsageUI"),
        .executableTarget(name: "DevOrchestratorBar", dependencies: ["UsageUI"]),
        .testTarget(name: "UsageClientTests", dependencies: ["UsageClient"]),
    ]
)
