import Foundation
import AppKit

class LabelGenerator {
    static func generate(code: String, name: String, lengthMM: Int, dpi600: Bool = true, weee: Bool = true) async -> NSImage? {
        let safeCode = code.replacingOccurrences(of: "/", with: "_")
        let ts = Int(Date().timeIntervalSince1970)
        let tmpURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("stitek_\(safeCode)_\(lengthMM)_\(ts).png")

        let script = ("~/Desktop/CteckaStitkySW/Scripts/generate_label.py" as NSString).expandingTildeInPath

        // Zkus najít Python
        let pythons = ["/usr/local/bin/python3.11", "/usr/local/bin/python3",
                       "/opt/homebrew/bin/python3", "/usr/bin/python3"]
        guard let python = pythons.first(where: { FileManager.default.fileExists(atPath: $0) }) else {
            return nil
        }

        return await withCheckedContinuation { continuation in
            let proc = Process()
            proc.executableURL = URL(fileURLWithPath: python)
            proc.arguments = [script, code, name, "\(lengthMM)", tmpURL.path, dpi600 ? "1" : "0", weee ? "1" : "0"]
            proc.terminationHandler = { _ in
                if let data = try? Data(contentsOf: tmpURL),
                   let image = NSImage(data: data) {
                    continuation.resume(returning: image)
                } else {
                    continuation.resume(returning: nil)
                }
            }
            try? proc.run()
        }
    }
}
