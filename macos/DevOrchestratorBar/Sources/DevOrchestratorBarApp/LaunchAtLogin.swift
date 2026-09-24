import Combine
import ServiceManagement

@MainActor
public final class LaunchAtLogin: ObservableObject {
    @Published public private(set) var isEnabled = SMAppService.mainApp.status == .enabled
    @Published public private(set) var errorMessage: String?

    public init() {}

    public func setEnabled(_ enabled: Bool) {
        do {
            if enabled {
                try SMAppService.mainApp.register()
            } else {
                try SMAppService.mainApp.unregister()
            }
            isEnabled = SMAppService.mainApp.status == .enabled
            errorMessage = nil
        } catch {
            // Keep the switch aligned with the system registration state and
            // expose the failure in the popover instead of hiding it.
            isEnabled = SMAppService.mainApp.status == .enabled
            errorMessage = error.localizedDescription
        }
    }
}
