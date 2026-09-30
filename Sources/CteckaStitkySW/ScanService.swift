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

    func start() {
        guard !isRunning else { return }
        events.removeAll()
        guard let python = Paths.python else {
            events.insert(ScanEvent(status: .error, msg: "Python nenalezen"), at: 0)
            return
        }
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: python)
        proc.arguments = [Paths.script("scan_print.py")]

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

        do {
            try proc.run()
        } catch {
            events.insert(ScanEvent(status: .error, msg: "Nelze spustit scan_print.py: \(error.localizedDescription)"), at: 0)
            isRunning = false
            return
        }
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
