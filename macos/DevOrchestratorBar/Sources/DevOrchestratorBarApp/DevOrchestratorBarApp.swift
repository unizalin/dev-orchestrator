import Foundation
import SwiftUI
import UsageClient
import UsageUI

private struct MissingUsageClient: UsageLoading {
    let expectedPath: String

    func load(_: UsageRequest) async throws -> UsageSnapshot {
        throw UsageClientError.executionFailed("找不到 UsageCLI：\(expectedPath)")
    }
}

public enum AppDependencies {
    /// Return the helper embedded in the app bundle. Deliberately do not
    /// search PATH: a release app must invoke only its version-matched helper.
    public static func usageHelperURL(bundle: Bundle = .main) -> URL? {
        bundle.url(
            forResource: "dev-orchestrator-usage",
            withExtension: nil,
            subdirectory: "UsageCLI"
        )
    }

    public static func usageClient(bundle: Bundle = .main) -> any UsageLoading {
        if let helperURL = usageHelperURL(bundle: bundle) {
            return ProcessUsageClient(executable: helperURL)
        }

        let path = bundle.bundleURL
            .appendingPathComponent("Contents", isDirectory: true)
            .appendingPathComponent("Resources", isDirectory: true)
            .appendingPathComponent("UsageCLI", isDirectory: true)
            .appendingPathComponent("dev-orchestrator-usage", isDirectory: false)
            .path
        return MissingUsageClient(expectedPath: path)
    }
}

@main
public struct DevOrchestratorBarApp: App {
    @StateObject private var model = UsageViewModel(loader: AppDependencies.usageClient())
    @StateObject private var launchAtLogin = LaunchAtLogin()

    public init() {}

    public var body: some Scene {
        Window("Dev Orchestrator 用量", id: "usage-dashboard") {
            UsagePopoverView(
                model: model,
                launchAtLogin: Binding(
                    get: { launchAtLogin.isEnabled },
                    set: { launchAtLogin.setEnabled($0) }
                ),
                launchAtLoginError: launchAtLogin.errorMessage
            )
        }
        .defaultSize(width: 392, height: 620)

        MenuBarExtra {
            UsagePopoverView(
                model: model,
                launchAtLogin: Binding(
                    get: { launchAtLogin.isEnabled },
                    set: { launchAtLogin.setEnabled($0) }
                ),
                launchAtLoginError: launchAtLogin.errorMessage
            )
        } label: {
            menuBarLabel(model: model)
                .task {
                    await model.refresh()
                }
                .task(id: model.autoRefresh) {
                    while model.autoRefresh && !Task.isCancelled {
                        try? await Task.sleep(for: .seconds(30))
                        guard !Task.isCancelled else { return }
                        await model.refresh()
                    }
                }
        }
        .menuBarExtraStyle(.window)
    }

    @ViewBuilder
    private func menuBarLabel(model: UsageViewModel) -> some View {
        let presentation = MenuBarLabelPresentation(title: model.menuBarTitle)
        if let title = presentation.title {
            Label {
                Text(title)
            } icon: {
                Image(systemName: "chart.bar.xaxis")
            }
            .accessibilityLabel(presentation.accessibilityLabel)
        } else {
            Image(systemName: "chart.bar.xaxis")
                .accessibilityLabel(presentation.accessibilityLabel)
        }
    }
}
