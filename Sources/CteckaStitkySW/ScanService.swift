import Foundation
import AppKit

struct ScanEvent: Identifiable {
    enum Status { case ok, error, info }

    let id = UUID()
    let date = Date()
    let status: Status
    let msg: String
    /// Volitelná pole ze scan_print.py (od verze s velkou kartou výsledku).
    var code: String?
    var name: String?
    var source: String?
    var barcode: String?
    /// "qr" | "nenalezen" | "vice" | "tisk" | "offline" (jen u chyb)
    var kind: String?
    var offline = false
}

class ScanService: ObservableObject {
    static let shared = ScanService()

    @Published var isRunning = false
    /// Nejnovější první.
    @Published var events: [ScanEvent] = []
    @Published var soundOn: Bool = UserDefaults.standard.object(forKey: "scanSound") as? Bool ?? true {
        didSet { UserDefaults.standard.set(soundOn, forKey: "scanSound") }
    }

    private var process: Process?
    private var buffer = Data()

    /// Poslední výsledek skenu (vytištěno / chyba) pro velkou kartu.
    var lastResult: ScanEvent? { events.first { $0.status != .info } }
    /// Poslední informační hláška (připojeno, hledám…) pro horní lištu.
    var lastInfo: ScanEvent? { events.first { $0.status == .info } }
    var printedCount: Int { events.filter { $0.status == .ok }.count }
    var errorCount: Int { events.filter { $0.status == .error }.count }

    func start() {
        guard !isRunning else { return }
        events.removeAll()
        buffer.removeAll()
        guard let python = Paths.python else {
            append(ScanEvent(status: .error, msg: "Python nenalezen"))
            return
        }
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: python)
        proc.arguments = [Paths.script("scan_print.py")]

        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = pipe

        // Data z roury chodí po kouscích – skládat do celých řádků, jinak se
        // dlouhý JSON rozpůlí a událost se ztratí.
        pipe.fileHandleForReading.readabilityHandler = { [weak self] fh in
            let data = fh.availableData
            guard !data.isEmpty else { return }
            DispatchQueue.main.async { self?.consume(data) }
        }

        proc.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async { self?.isRunning = false }
        }

        do {
            try proc.run()
        } catch {
            append(ScanEvent(status: .error, msg: "Nelze spustit scan_print.py: \(error.localizedDescription)"))
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

    private func consume(_ data: Data) {
        buffer.append(data)
        while let nl = buffer.firstIndex(of: 0x0A) {
            let lineData = buffer[buffer.startIndex..<nl]
            buffer.removeSubrange(buffer.startIndex...nl)
            if let line = String(data: lineData, encoding: .utf8), let ev = parse(line) {
                append(ev)
            }
        }
    }

    private func append(_ ev: ScanEvent) {
        events.insert(ev, at: 0)
        if events.count > 500 { events.removeLast(events.count - 500) }
        guard soundOn else { return }
        switch ev.status {
        case .ok:    NSSound(named: "Glass")?.play()
        case .error: NSSound(named: "Basso")?.play()
        case .info:  break
        }
    }

    #if DEBUG
    func demoEvents(error: Bool) {
        events.removeAll()
        let lines = [
            #"{"status":"error","msg":"Naskenován QR kód s odkazem (www.wearecasper.com), ne čárový kód produktu","barcode":"http://www.wearecasper.com","kind":"qr"}"#,
            #"{"status":"error","msg":"Produkt nenalezen","barcode":"107282215097","kind":"nenalezen"}"#,
            #"{"status":"ok","msg":"Vytištěno","code":"71065","name":"Tvrzené sklo CASPER Pro | iPhone 6, 6S, 7, 8, SE 2, SE 3","source":"EAN"}"#,
            #"{"status":"ok","msg":"Vytištěno","code":"71065","name":"Tvrzené sklo CASPER Pro | iPhone 6, 6S, 7, 8, SE 2, SE 3","source":"EAN"}"#,
            #"{"status":"ok","msg":"Vytištěno","code":"8508","name":"Opravný home button pro iPhone 7, 8, SE – Černá","source":"kód dodavatele"}"#,
            error
              ? #"{"status":"error","msg":"Produkt nenalezen","barcode":"107282215097","kind":"nenalezen"}"#
              : #"{"status":"ok","msg":"Vytištěno","code":"71022","name":"Tvrzené sklo CASPER Pro | iPhone 12, 12 Pro","source":"EAN"}"#,
        ]
        for l in lines { if let ev = parse(l) { events.insert(ev, at: 0) } }
    }
    #endif

    private func parse(_ line: String) -> ScanEvent? {
        guard let data = line.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let status = obj["status"] as? String, let msg = obj["msg"] as? String else { return nil }
        let s: ScanEvent.Status = status == "ok" ? .ok : status == "error" ? .error : .info
        var ev = ScanEvent(status: s, msg: msg)
        ev.code = obj["code"] as? String
        ev.name = obj["name"] as? String
        ev.source = obj["source"] as? String
        ev.barcode = obj["barcode"] as? String
        ev.kind = obj["kind"] as? String
        ev.offline = (obj["offline"] as? String) == "1"
        return ev
    }
}
