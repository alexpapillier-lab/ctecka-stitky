import Foundation
import Combine

struct ScanEvent: Identifiable {
    let id = UUID()
    let status: ScanStatus
    let msg: String

    enum ScanStatus { case ok, error, info }
}

class ScanService: ObservableObject {
    static let shared = ScanService()

    @Published var isRunning = false
    @Published var events: [ScanEvent] = []

    private var process: Process?

    private func python() -> String? {
        let candidates = ["/usr/local/bin/python3.11", "/usr/local/bin/python3",
                          "/opt/homebrew/bin/python3", "/usr/bin/python3"]
        return candidates.first { FileManager.default.fileExists(atPath: $0) }
    }

    private var scriptPath: String {
        ("~/Desktop/CteckaStitkySW/Scripts/scan_print.py" as NSString).expandingTildeInPath
    }

    func start() {
        guard !isRunning, let python = python() else { return }
        events.removeAll()
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: python)
        proc.arguments = [scriptPath]

        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = pipe

        pipe.fileHandleForReading.readabilityHandler = { [weak self] fh in
            let data = fh.availableData
            guard !data.isEmpty, let self else { return }
            let lines = String(data: data, encoding: .utf8)?.components(separatedBy: "\n") ?? []
            for line in lines where !line.isEmpty {
                if let ev = self.parse(line) {
                    DispatchQueue.main.async { self.events.insert(ev, at: 0) }
                }
            }
        }

        proc.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async { self?.isRunning = false }
        }

        try? proc.run()
        process = proc
        isRunning = true
    }

    func stop() {
        process?.terminate()
        process = nil
        isRunning = false
    }

    private func parse(_ line: String) -> ScanEvent? {
        guard let data = line.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: String],
              let status = obj["status"], let msg = obj["msg"] else { return nil }
        let s: ScanEvent.ScanStatus = status == "ok" ? .ok : status == "error" ? .error : .info
        return ScanEvent(status: s, msg: msg)
    }
}
