import Foundation

/// Cesty odvozené od umístění binárky. Appka se spouští přes `Spustit.command`
/// (`exec "$DIR/CteckaStitkySW"`), takže vedle binárky leží `Scripts/`, `venv/`
/// a `Spustit.command`. Fallback na ~/Desktop/CteckaStitkySW je jen pro spouštění
/// z Xcode / `swift run`, kde binárka leží v .build/.
enum Paths {
    /// Složka, kde leží binárka (a vedle ní Scripts/, venv/, Spustit.command).
    static let appDir: URL = {
        let fm = FileManager.default
        let exe = URL(fileURLWithPath: CommandLine.arguments[0]).resolvingSymlinksInPath()
        let dir = exe.deletingLastPathComponent()
        if fm.fileExists(atPath: dir.appendingPathComponent("Scripts").path) {
            return dir
        }
        return URL(fileURLWithPath: ("~/Desktop/CteckaStitkySW" as NSString).expandingTildeInPath)
    }()

    static var scriptsDir: URL { appDir.appendingPathComponent("Scripts") }

    static func script(_ name: String) -> String {
        scriptsDir.appendingPathComponent(name).path
    }

    /// První existující: appDir/venv/bin/python3, /usr/local/bin/python3.11,
    /// /usr/local/bin/python3, /opt/homebrew/bin/python3, /usr/bin/python3
    static var python: String? {
        let candidates = [
            appDir.appendingPathComponent("venv/bin/python3").path,
            "/usr/local/bin/python3.11",
            "/usr/local/bin/python3",
            "/opt/homebrew/bin/python3",
            "/usr/bin/python3",
        ]
        return candidates.first { FileManager.default.fileExists(atPath: $0) }
    }
}
