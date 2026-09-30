import Foundation
import AppKit

class LabelGenerator {
    /// Spustí Scripts/generate_label.py a vrátí (náhled, nil), nebo (nil, text chyby)
    /// (stderr Pythonu / důvod, proč se proces nespustil).
    /// Argumenty skriptu: code name length_mm output_path dpi600(0/1) weee(0/1) serial importer
    /// – pořadí prvních 8 se nesmí měnit, starší skripty 9. argument ignorují.
    static func generate(code: String, name: String, lengthMM: Int, dpi600: Bool = true, weee: Bool = true,
                         serial: String? = nil, importer: String? = nil) async -> (NSImage?, String?) {
        let safeCode = code.replacingOccurrences(of: "/", with: "_")
        let ts = Int(Date().timeIntervalSince1970)
        let tmpURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("stitek_\(safeCode)_\(lengthMM)_\(ts).png")

        guard let python = Paths.python else {
            return (nil, "Python nenalezen")
        }

        return await withCheckedContinuation { continuation in
            let proc = Process()
            proc.executableURL = URL(fileURLWithPath: python)
            proc.arguments = [Paths.script("generate_label.py"), code, name, "\(lengthMM)", tmpURL.path,
                              dpi600 ? "1" : "0", weee ? "1" : "0", serial ?? "", importer ?? ""]
            let errPipe = Pipe()
            proc.standardError = errPipe
            proc.terminationHandler = { p in
                let stderr = String(data: errPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
                    .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                if p.terminationStatus != 0 {
                    continuation.resume(returning: (nil,
                        stderr.isEmpty ? "generate_label.py skončil s kódem \(p.terminationStatus)" : stderr))
                    return
                }
                if let data = try? Data(contentsOf: tmpURL), let image = NSImage(data: data) {
                    continuation.resume(returning: (image, nil))
                } else {
                    continuation.resume(returning: (nil,
                        stderr.isEmpty ? "Náhled se nevytvořil (\(tmpURL.lastPathComponent))" : stderr))
                }
            }
            do {
                try proc.run()
            } catch {
                continuation.resume(returning: (nil, "Nelze spustit Python: \(error.localizedDescription)"))
            }
        }
    }
}
