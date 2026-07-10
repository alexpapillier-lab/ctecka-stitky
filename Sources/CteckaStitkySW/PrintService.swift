import Foundation

class PrintService {
    static let shared = PrintService()

    private func python() -> String? {
        let candidates = ["/usr/local/bin/python3.11", "/usr/local/bin/python3",
                          "/opt/homebrew/bin/python3", "/usr/bin/python3"]
        return candidates.first { FileManager.default.fileExists(atPath: $0) }
    }

    private func scriptPath(_ name: String) -> String {
        ("~/Desktop/CteckaStitkySW/Scripts/\(name)" as NSString).expandingTildeInPath
    }

    func print(code: String, name: String, lengthMM: Int, copies: Int, dpi600: Bool = true, weee: Bool = true) async -> (Bool, String?) {
        guard let python = python() else { return (false, "Python nenalezen") }
        return await withCheckedContinuation { cont in
            let proc = Process()
            proc.executableURL = URL(fileURLWithPath: python)
            proc.arguments = [scriptPath("print_label.py"), code, name, "\(lengthMM)", "\(copies)", dpi600 ? "1" : "0", weee ? "1" : "0"]
            let errPipe = Pipe()
            proc.standardError = errPipe
            proc.terminationHandler = { p in
                if p.terminationStatus == 0 {
                    cont.resume(returning: (true, nil))
                } else {
                    let msg = String(data: errPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)
                        ?? "Neznámá chyba"
                    cont.resume(returning: (false, msg.trimmingCharacters(in: .whitespacesAndNewlines)))
                }
            }
            try? proc.run()
        }
    }
}
