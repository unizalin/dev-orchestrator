import Foundation
import AppKit
import Combine
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

@MainActor
public final class StatusItemController: NSObject, NSApplicationDelegate {
    public let model = UsageViewModel(loader: AppDependencies.usageClient())
    public let launchAtLogin = LaunchAtLogin()

    private var statusItem: NSStatusItem?
    private var popover: NSPopover?
    private var refreshTask: Task<Void, Never>?
    private var cancellables = Set<AnyCancellable>()

    public func applicationDidFinishLaunching(_ notification: Notification) {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem = item

        if let button = item.button {
            button.image = NSImage(
                systemSymbolName: "chart.bar.xaxis",
                accessibilityDescription: "追蹤用量"
            )
            button.imagePosition = .imageLeading
            button.target = self
            button.action = #selector(togglePopover(_:))
            button.toolTip = "開啟追蹤用量"
            button.setAccessibilityLabel("開啟追蹤用量")
        }

        let panel = NSPopover()
        panel.behavior = .transient
        panel.animates = true
        panel.contentSize = NSSize(width: 392, height: 620)
        panel.contentViewController = NSHostingController(rootView: usageView())
        popover = panel

        cancellables.insert(
            model.$snapshot.sink { [weak self] _ in
                self?.updateStatusItem()
            }
        )

        refreshTask = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                if self.model.autoRefresh {
                    await self.model.refresh()
                }
                try? await Task.sleep(for: .seconds(30))
            }
        }
        Task { await model.refresh() }
    }

    public func applicationWillTerminate(_ notification: Notification) {
        refreshTask?.cancel()
        cancellables.removeAll()
    }

    public func usageView() -> UsagePopoverView {
        UsagePopoverView(
            model: model,
            launchAtLogin: Binding(
                get: { self.launchAtLogin.isEnabled },
                set: { self.launchAtLogin.setEnabled($0) }
            ),
            launchAtLoginError: launchAtLogin.errorMessage
        )
    }

    private func updateStatusItem() {
        guard let button = statusItem?.button else { return }
        let title = model.menuBarTitle
        button.title = title ?? ""
        button.imagePosition = title == nil ? .imageOnly : .imageLeading
        let label = MenuBarLabelPresentation(title: title).accessibilityLabel
        button.toolTip = label
        button.setAccessibilityLabel(label)
    }

    @objc private func togglePopover(_ sender: Any?) {
        guard let button = statusItem?.button, let popover else { return }
        if popover.isShown {
            popover.performClose(sender)
            return
        }
        NSApp.activate(ignoringOtherApps: true)
        popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
    }
}

@main
public struct DevOrchestratorBarApp: App {
    @NSApplicationDelegateAdaptor(StatusItemController.self)
    private var controller

    public init() {}

    public var body: some Scene {
        Window("Dev Orchestrator 用量", id: "usage-dashboard") {
            controller.usageView()
        }
        .defaultSize(width: 392, height: 620)
    }
}
