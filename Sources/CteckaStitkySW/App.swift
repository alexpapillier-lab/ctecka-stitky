import SwiftUI
import AppKit

/// Appka se spouští jako holá binárka (ne .app bundle), takže ji macOS bere jako
/// background proces – okno nakreslí a myš funguje, ale klávesnici nikdy nedostane.
/// Bez tohohle nejde psát do vyhledávacího pole.
class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }
}

@main
struct CteckaStitkySWApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .windowToolbarStyle(UnifiedWindowToolbarStyle())
        .commands {
            CommandGroup(replacing: .newItem) {}
            // ⌘P patří tlačítku Tisknout, ne systémové položce Tisk…
            CommandGroup(replacing: .printItem) {}
        }
    }
}
