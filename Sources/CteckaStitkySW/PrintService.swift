import Foundation

class PrintService {
    static let shared = PrintService()

    /// Spustí Scripts/print_label.py. Vrací (úspěch, text chyby).
    /// Argumenty skriptu: code name length_mm copies dpi600(0/1) weee(0/1) serial importer
    /// – pořadí prvních 8 se nesmí měnit, starší skripty 9. argument ignorují.
    func print(code: String, name: String, lengthMM: Int, copies: Int, dpi600: Bool = true, weee: Bool = true,
               serial: String? = nil, importer: String? = nil) async -> (Bool, String?) {
        guard let python = Paths.python else { return (false, "Python nenalezen") }
        return await withCheckedContinuation { cont in
            let proc = Process()
            proc.executableURL = URL(fileURLWithPath: python)
            proc.arguments = [Paths.script("print_label.py"), code, name, "\(lengthMM)", "\(copies)",
                              dpi600 ? "1" : "0", weee ? "1" : "0", serial ?? "", importer ?? ""]
            let errPipe = Pipe()
            proc.standardError = errPipe
            proc.terminationHandler = { p in
                if p.terminationStatus == 0 {
                    cont.resume(returning: (true, nil))
                } else {
                    let msg = String(data: errPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
                        .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                    cont.resume(returning: (false, msg.isEmpty ? "print_label.py skončil s kódem \(p.terminationStatus)" : msg))
                }
            }
            do {
                try proc.run()
            } catch {
                cont.resume(returning: (false, "Nelze spustit Python: \(error.localizedDescription)"))
            }
        }
    }
}
