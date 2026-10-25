import SwiftUI
import AppKit
import Combine

struct ContentView: View {
    enum Mode: Hashable { case manual, scan }

    @StateObject private var products = ProductsViewModel()
    @StateObject private var devices = DeviceMonitor()
    @ObservedObject private var scan = ScanService.shared
    @State private var mode: Mode = .manual
    @State private var selected: Product?

    /// Bez internetu se každou minutu tiše zkusí znovu načíst seznam z DB.
    private let retry = Timer.publish(every: 60, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(spacing: 0) {
            banner
            if mode == .manual {
                ManualView(products: products, devices: devices, selected: $selected)
            } else {
                ScanView(scan: scan, onSearchManually: searchManually)
            }
        }
        .frame(minWidth: 920, minHeight: 600)
        .navigationTitle("Štítky")
        .toolbar {
            ToolbarItem(placement: .principal) {
                Picker("Režim", selection: $mode) {
                    Text("Ruční výběr").tag(Mode.manual)
                    Text("Scan mód").tag(Mode.scan)
                }
                .pickerStyle(SegmentedPickerStyle())
                .labelsHidden()
                .frame(width: 230)
            }
            ToolbarItem(placement: .automatic) {
                HStack(spacing: 8) {
                    printerPill
                    if mode == .scan { scannerPill }
                    databasePill
                }
            }
        }
        .onAppear {
            Task {
                await products.load()
                #if DEBUG
                applyDemo()
                #endif
            }
        }
        .onReceive(retry) { _ in
            if case .online = products.source { return }
            if !products.isLoading { Task { await products.load() } }
        }
    }

    // ── Horní lišta: stav zařízení a databáze ──────────────────────────
    private var printerPill: some View {
        switch devices.printerConnected {
        case true?:  return StatusPill(label: "Tiskárna", level: .ok, help: "Brother QL-700 je připojená")
        case false?: return StatusPill(label: "Tiskárna odpojená", level: .error,
                                       help: "Tiskárna Brother nebyla na USB nalezena – zapni ji a zkontroluj kabel")
        case nil:    return StatusPill(label: "Tiskárna", level: .unknown)
        }
    }

    private var scannerPill: some View {
        devices.scannerConnected == true
            ? StatusPill(label: "Čtečka", level: .ok, help: "Čtečka je připojená")
            : StatusPill(label: "Čtečka odpojená", level: .error, help: "Sériový port čtečky nenalezen")
    }

    private var databasePill: some View {
        switch products.source {
        case .online(let d): return StatusPill(label: "Online", level: .ok,
                                               help: "Seznam produktů načten v \(timeFormatter.string(from: d))")
        case .cache:         return StatusPill(label: "Offline", level: .warning, help: "Bez internetu – používá se uložený seznam")
        case .failed:        return StatusPill(label: "Bez dat", level: .error, help: "Seznam produktů se nepodařilo načíst")
        case .none:          return StatusPill(label: "Načítám", level: .unknown)
        }
    }

    // ── Pruh pod lištou, když není internet ───────────────────────────
    @ViewBuilder private var banner: some View {
        switch products.source {
        case .cache(let date):
            BannerView(icon: "wifi.slash", color: Color(NSColor.systemOrange),
                       text: "Bez internetu – používám uložený seznam produktů z \(dayTimeFormatter.string(from: date)). Tisk funguje normálně.",
                       isLoading: products.isLoading) { Task { await products.load() } }
        case .failed:
            BannerView(icon: "exclamationmark.triangle.fill", color: Color(NSColor.systemRed),
                       text: "Seznam produktů se nepodařilo načíst a uložená kopie zatím není. Zkontroluj připojení k internetu.",
                       isLoading: products.isLoading) { Task { await products.load() } }
        default:
            EmptyView()
        }
    }

    #if DEBUG
    /// Jen pro vývoj (do release buildu se nedostane): STITKY_DEMO_SEARCH=kód předvybere
    /// produkt, STITKY_DEMO_MODE=scan přepne na scan s ukázkovými událostmi.
    private func applyDemo() {
        let env = ProcessInfo.processInfo.environment
        if let q = env["STITKY_DEMO_SEARCH"] {
            products.search = q
            selected = products.filtered.first
        }
        if env["STITKY_DEMO_MODE"] == "scan" {
            mode = .scan
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                scan.stop()
                scan.soundOn = false
                scan.demoEvents(error: env["STITKY_DEMO_ERROR"] == "1")
            }
        }
    }
    #endif

    /// Ze scan módu ("Hledat ručně") – přepne na ruční výběr s vyplněným kódem.
    private func searchManually(_ code: String) {
        products.search = code
        let hits = products.filtered
        selected = hits.count == 1 ? hits.first : nil
        mode = .manual
    }
}

struct BannerView: View {
    let icon: String
    let color: Color
    let text: String
    let isLoading: Bool
    let retry: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
            Text(text).fixedSize(horizontal: false, vertical: true)
            Spacer()
            if isLoading {
                ProgressView().scaleEffect(0.5).frame(width: 16, height: 16)
            } else {
                Button("Zkusit znovu", action: retry).buttonStyle(QuietButtonStyle())
            }
        }
        .font(.system(size: 12))
        .foregroundColor(color)
        .padding(.horizontal, 14)
        .padding(.vertical, 7)
        .background(color.opacity(0.12))
    }
}

// ── Ruční výběr ──────────────────────────────────────────────────────
struct ManualView: View {
    @ObservedObject var products: ProductsViewModel
    @ObservedObject var devices: DeviceMonitor
    @Binding var selected: Product?

    var body: some View {
        HSplitView {
            ProductSidebar(products: products, selected: $selected)
                .frame(minWidth: 280, idealWidth: 330, maxWidth: 420)
            Group {
                if let product = selected {
                    ProductDetail(product: product, devices: devices)
                        .id(product.code)       // nový produkt = čistý stav (kopie 1, náhled…)
                } else {
                    EmptyDetail()
                }
            }
            .frame(minWidth: 560, maxWidth: .infinity, maxHeight: .infinity)
        }
    }
}

struct ProductSidebar: View {
    @ObservedObject var products: ProductsViewModel
    @Binding var selected: Product?

    var body: some View {
        let list = products.filtered
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass").foregroundColor(.secondary)
                TextField("Kód, název, EAN nebo kód dodavatele", text: $products.search)
                    .textFieldStyle(PlainTextFieldStyle())
                if !products.search.isEmpty {
                    Button { products.search = "" } label: {
                        Image(systemName: "xmark.circle.fill").foregroundColor(.secondary)
                    }
                    .buttonStyle(PlainButtonStyle())
                }
            }
            .padding(.horizontal, 9)
            .padding(.vertical, 7)
            .background(RoundedRectangle(cornerRadius: 8).fill(Color(NSColor.textBackgroundColor)))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.primary.opacity(0.12), lineWidth: 0.5))
            .padding(10)

            Divider()

            if list.isEmpty && !products.search.isEmpty {
                VStack(spacing: 6) {
                    Text("Nic nenalezeno").font(.headline)
                    Text("Zkus jiná slova, kód nebo EAN.").font(.caption).foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(list, selection: $selected) { product in
                    ProductRow(product: product).tag(product)
                }
                .listStyle(InsetListStyle())
            }

            Divider()
            HStack(spacing: 6) {
                if products.isLoading { ProgressView().scaleEffect(0.5).frame(width: 14, height: 14) }
                Text(footer(count: list.count)).font(.system(size: 11)).foregroundColor(.secondary)
                Spacer()
                Button { Task { await products.load() } } label: { Image(systemName: "arrow.clockwise") }
                    .buttonStyle(PlainButtonStyle())
                    .help("Znovu načíst seznam produktů")
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
        }
    }

    private func footer(count: Int) -> String {
        let total = products.products.count
        let n = products.search.isEmpty ? "\(total) produktů" : "\(count) z \(total)"
        switch products.source {
        case .online(let d): return "\(n) · načteno \(timeFormatter.string(from: d))"
        case .cache(let d):  return "\(n) · uloženo \(dayTimeFormatter.string(from: d))"
        default:             return products.isLoading ? "Načítám…" : n
        }
    }
}

struct ProductRow: View {
    let product: Product

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 5) {
                Text(product.code).font(.system(size: 13, weight: .semibold, design: .monospaced))
                Spacer(minLength: 4)
                if product.isActive {
                    ForEach(product.tags) { Tag(text: $0.text, color: $0.color) }
                } else {
                    Text("není v Shoptetu").font(.system(size: 10)).foregroundColor(.secondary)
                }
            }
            Text(product.name).font(.system(size: 12)).foregroundColor(.secondary).lineLimit(2)
        }
        .padding(.vertical, 3)
        .opacity(product.isActive ? 1 : 0.5)
    }
}

struct EmptyDetail: View {
    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: "tag").font(.system(size: 52)).foregroundColor(.secondary.opacity(0.35))
            Text("Vyber produkt ze seznamu").font(.title3).foregroundColor(.secondary)
            Text("Nebo přepni na Scan mód a štítky se budou tisknout po naskenování.")
                .font(.caption).foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// ── Detail produktu: náhled + tisk ───────────────────────────────────
struct ProductDetail: View {
    let product: Product
    @ObservedObject var devices: DeviceMonitor

    @State private var labelImage: NSImage?
    @State private var previewError: String?
    @State private var isGenerating = false
    @State private var previewTask: Task<Void, Never>?
    @State private var isPrinting = false
    @State private var copies = 1
    @State private var lengthMM = 62
    @State private var weee = true
    @State private var serialNumber = ""
    @State private var result: PrintResult?
    @State private var activeAlert: ActiveAlert?

    enum PrintResult { case printed(count: Int, at: Date), error(String) }
    enum ActiveAlert: Identifiable {
        case weee, serialMissing
        var id: Int { hashValue }
    }

    /// Ruční i scan tisk jedou na 300 DPI (rychlý tisk) – uživatel tak chtěl.
    private let dpi600 = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
                .padding(.horizontal, 18)
                .padding(.top, 16)
                .padding(.bottom, 12)

            preview
                .padding(.horizontal, 18)

            if product.needsSerialNumber {
                HStack(spacing: 8) {
                    Text("Sériové číslo").foregroundColor(.secondary)
                    TextField("sériové číslo jednotky", text: $serialNumber)
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                        .frame(maxWidth: 260)
                    Text("vytiskne se i druhý štítek jen se SN").font(.caption).foregroundColor(.secondary)
                }
                .padding(.horizontal, 18)
                .padding(.top, 12)
            }

            notices
                .padding(.horizontal, 18)
                .padding(.top, 10)

            Divider().padding(.top, 12)
            actionBar
                .padding(.horizontal, 18)
                .padding(.vertical, 12)
        }
        .onAppear {
            lengthMM = product.defaultLength
            weee = WEEEPrefs.shared.get(for: product.code)
            schedulePreview(delay: 0)
        }
        .onChange(of: lengthMM) { _ in schedulePreview() }
        .onChange(of: weee) { _ in schedulePreview() }
        .onChange(of: serialNumber) { _ in schedulePreview(delay: 450_000_000) }
        .onDisappear { previewTask?.cancel() }
        .alert(item: $activeAlert) { alert in
            switch alert {
            case .weee:
                return Alert(
                    title: Text("Zobrazit ikonu přeškrtnuté popelnice (WEEE)?"),
                    message: Text("Volba se uloží pro příští tisky tohoto produktu."),
                    primaryButton: .default(Text("Ano – zobrazit")) { chooseWEEE(true, thenPrint: true) },
                    secondaryButton: .cancel(Text("Ne – nezobrazovat")) { chooseWEEE(false, thenPrint: true) }
                )
            case .serialMissing:
                return Alert(title: Text("Chybí sériové číslo"),
                             message: Text("Před tiskem vepiš sériové číslo této jednotky."),
                             dismissButton: .default(Text("OK")))
            }
        }
    }

    // Název: zařízení velkým písmem, díl nad ním; pod tím kódy.
    private var header: some View {
        let parts = product.nameParts
        return VStack(alignment: .leading, spacing: 5) {
            if let device = parts.device {
                Text(parts.detail).font(.system(size: 13)).foregroundColor(.secondary).lineLimit(2)
                Text(device).font(.system(size: 22, weight: .semibold)).lineLimit(2)
            } else {
                Text(parts.detail).font(.system(size: 20, weight: .semibold)).lineLimit(3)
            }
            HStack(spacing: 6) {
                Tag(text: product.code, color: .primary, mono: true)
                Tag(text: "EAN \(product.ean)", mono: true)
                if let pn = product.part_number, !pn.isEmpty {
                    Tag(text: "dodavatel \(pn)", mono: true)
                }
                Tag(text: product.importerLabel ?? "dovozce podle názvu")
                if product.isDisplay { Tag(text: "Displej", color: Color(NSColor.systemBlue)) }
                if !product.isActive { Tag(text: "není v Shoptetu", color: Color(NSColor.systemOrange)) }
            }
            .padding(.top, 3)
        }
    }

    private var preview: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 10).fill(Color.primary.opacity(0.05))
            if let img = labelImage {
                Image(nsImage: img)
                    .resizable()
                    .interpolation(.high)
                    .scaledToFit()
                    .background(Color.white)
                    .cornerRadius(3)
                    .shadow(color: Color.black.opacity(0.18), radius: 5, x: 0, y: 2)
                    .padding(24)
                    .contextMenu {
                        Button("Uložit PNG…") { savePNG(image: img) }
                    }
            } else if let err = previewError, !isGenerating {
                VStack(spacing: 6) {
                    Image(systemName: "exclamationmark.triangle").font(.system(size: 26))
                    Text("Náhled se nepodařilo vytvořit").font(.headline)
                    Text(err).font(.caption).lineLimit(4).multilineTextAlignment(.center)
                }
                .foregroundColor(Color(NSColor.systemRed))
                .padding()
            }
            if isGenerating {
                VStack {
                    HStack { Spacer(); ProgressView().scaleEffect(0.6).frame(width: 18, height: 18) }
                    Spacer()
                }
                .padding(10)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 200, maxHeight: .infinity)
    }

    // Varování a výsledek tisku – nad spodní lištou, ať se vejde i delší chyba.
    @ViewBuilder private var notices: some View {
        if devices.printerConnected == false {
            Label("Tiskárna není připojená – zapni Brother QL-700 a zkontroluj USB kabel.",
                  systemImage: "exclamationmark.triangle.fill")
                .font(.system(size: 12))
                .foregroundColor(Color(NSColor.systemOrange))
        }
        if case .error(let msg) = result {
            HStack(alignment: .top, spacing: 6) {
                Image(systemName: "xmark.circle.fill")
                Text(msg).lineLimit(5).fixedSize(horizontal: false, vertical: true)
            }
            .font(.system(size: 12))
            .foregroundColor(Color(NSColor.systemRed))
        }
    }

    private var actionBar: some View {
        HStack(spacing: 18) {
            Picker("Délka", selection: $lengthMM) {
                Text("62 mm").tag(62)
                Text("125 mm").tag(125)
            }
            .pickerStyle(SegmentedPickerStyle())
            .labelsHidden()
            .frame(width: 150)
            .help("Délka štítku – 125 mm pro displeje")

            HStack(spacing: 6) {
                Text("Kopií").foregroundColor(.secondary)
                Button { if copies > 1 { copies -= 1 } } label: { Image(systemName: "minus") }
                    .buttonStyle(QuietButtonStyle())
                Text("\(copies)")
                    .font(Font.system(size: 15, weight: .semibold).monospacedDigit())
                    .frame(minWidth: 24)
                Button { if copies < 50 { copies += 1 } } label: { Image(systemName: "plus") }
                    .buttonStyle(QuietButtonStyle())
            }

            Toggle("Ikona WEEE", isOn: Binding(
                get: { weee },
                set: { chooseWEEE($0, thenPrint: false) }
            ))
            .toggleStyle(CheckboxToggleStyle())
            .fixedSize()
            .help("Přeškrtnutá popelnice – volba se uloží pro tento produkt")

            Spacer()

            if case .printed(let count, let at) = result {
                Label("Vytištěno \(count)× · \(timeFormatter.string(from: at))", systemImage: "checkmark.circle.fill")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(Color(NSColor.systemGreen))
            }

            Button(action: printTapped) {
                HStack(spacing: 6) {
                    if isPrinting {
                        ProgressView().scaleEffect(0.5).frame(width: 14, height: 14)
                    } else {
                        Image(systemName: "printer.fill")
                    }
                    Text(isPrinting ? "Tisknu…" : "Tisknout")
                }
                .fixedSize()
            }
            .buttonStyle(PrimaryButtonStyle())
            .keyboardShortcut("p", modifiers: .command)
            .disabled(isPrinting)
            .help("Vytisknout (⌘P)")
        }
    }

    // ── Akce ──────────────────────────────────────────────────────
    private var trimmedSerial: String? {
        let s = serialNumber.trimmingCharacters(in: .whitespaces)
        return s.isEmpty ? nil : s
    }

    private func schedulePreview(delay: UInt64 = 150_000_000) {
        previewTask?.cancel()
        let p = product, length = lengthMM, w = weee, serial = trimmedSerial
        isGenerating = true
        previewTask = Task {
            if delay > 0 { try? await Task.sleep(nanoseconds: delay) }
            if Task.isCancelled { return }
            let (img, err) = await LabelGenerator.generate(
                code: p.code, name: p.name, lengthMM: length, dpi600: false, weee: w,
                serial: serial, importer: p.dovozce)
            if Task.isCancelled { return }
            await MainActor.run {
                if let img = img { labelImage = img }
                previewError = err
                isGenerating = false
            }
        }
    }

    private func chooseWEEE(_ value: Bool, thenPrint: Bool) {
        weee = value
        let code = product.code
        Task { await WEEEPrefs.shared.set(value, for: code) }
        if thenPrint { Task { await doPrint() } }
    }

    private func printTapped() {
        if product.needsSerialNumber && trimmedSerial == nil {
            activeAlert = .serialMissing
            return
        }
        if !WEEEPrefs.shared.hasChoice(for: product.code) {
            activeAlert = .weee
            return
        }
        Task { await doPrint() }
    }

    private func doPrint() async {
        await MainActor.run { isPrinting = true; result = nil }
        let n = copies
        let (ok, err) = await PrintService.shared.print(
            code: product.code, name: product.name, lengthMM: lengthMM, copies: n, dpi600: dpi600, weee: weee,
            serial: trimmedSerial, importer: product.dovozce)
        await MainActor.run {
            isPrinting = false
            result = ok ? .printed(count: n, at: Date()) : .error(err ?? "Neznámá chyba")
        }
    }

    private func savePNG(image: NSImage) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "stitek_\(product.code.replacingOccurrences(of: "/", with: "_")).png"
        panel.allowedFileTypes = ["png"]
        panel.begin { resp in
            guard resp == .OK, let url = panel.url,
                  let tiff = image.tiffRepresentation,
                  let rep = NSBitmapImageRep(data: tiff),
                  let data = rep.representation(using: .png, properties: [:]) else { return }
            try? data.write(to: url)
        }
    }
}

// ── Scan mód ─────────────────────────────────────────────────────────
struct ScanView: View {
    @ObservedObject var scan: ScanService
    let onSearchManually: (String) -> Void

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Circle()
                    .fill(scan.isRunning ? Color(NSColor.systemGreen) : Color.secondary.opacity(0.4))
                    .frame(width: 9, height: 9)
                Text(scan.isRunning ? "Připraveno – naskenuj produkt, štítek se vytiskne sám" : "Scan mód je zastavený")
                    .foregroundColor(scan.isRunning ? .primary : .secondary)
                Spacer()
                Button { scan.soundOn.toggle() } label: {
                    Image(systemName: scan.soundOn ? "speaker.wave.2.fill" : "speaker.slash.fill")
                }
                .buttonStyle(QuietButtonStyle())
                .help(scan.soundOn ? "Zvuk zapnutý – kliknutím vypneš" : "Zvuk vypnutý – kliknutím zapneš")
                Button {
                    if scan.isRunning { scan.stop() } else { scan.start() }
                } label: {
                    Label(scan.isRunning ? "Zastavit" : "Spustit",
                          systemImage: scan.isRunning ? "stop.fill" : "play.fill")
                }
                .buttonStyle(QuietButtonStyle())
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 10)

            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    ScanResultCard(event: scan.lastResult, onSearchManually: onSearchManually)

                    if !historyRows.isEmpty {
                        HStack {
                            Text("Historie").font(.headline)
                            Spacer()
                            Text("Od spuštění: \(scan.printedCount) vytištěno · \(scan.errorCount) chyb")
                                .font(.caption).foregroundColor(.secondary)
                        }
                        .padding(.top, 4)

                        VStack(spacing: 0) {
                            ForEach(historyRows) { row in
                                ScanHistoryRow(row: row)
                                if row.id != historyRows.last?.id { Divider() }
                            }
                        }
                        .background(RoundedRectangle(cornerRadius: 10).fill(Color.primary.opacity(0.03)))
                        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.primary.opacity(0.1), lineWidth: 0.5))
                    }
                }
                .padding(18)
            }
        }
        .onAppear { if !scan.isRunning { scan.start() } }
    }

    /// Výsledky skenů (bez info hlášek); stejný produkt naskenovaný víckrát za sebou = jeden řádek ×N.
    private var historyRows: [ScanHistoryRow.Row] {
        var rows: [ScanHistoryRow.Row] = []
        for ev in scan.events where ev.status != .info {
            if let last = rows.last, ev.status == .ok, last.event.status == .ok,
               last.event.code != nil, last.event.code == ev.code,
               abs(last.event.date.timeIntervalSince(ev.date)) < 120 {
                rows[rows.count - 1].count += 1
            } else {
                rows.append(ScanHistoryRow.Row(event: ev))
            }
            if rows.count >= 150 { break }
        }
        return rows
    }
}

struct ScanResultCard: View {
    let event: ScanEvent?
    let onSearchManually: (String) -> Void

    var body: some View {
        if let ev = event {
            HStack(alignment: .center, spacing: 16) {
                ZStack {
                    Circle().fill(Color(NSColor.windowBackgroundColor)).frame(width: 56, height: 56)
                    Image(systemName: icon(ev)).font(.system(size: 26, weight: .bold)).foregroundColor(color(ev))
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text(caption(ev)).font(.system(size: 12, weight: .medium)).foregroundColor(color(ev))
                    Text(title(ev)).font(.system(size: 20, weight: .semibold)).lineLimit(3)
                        .fixedSize(horizontal: false, vertical: true)
                    if let sub = subtitle(ev) {
                        Text(sub)
                            .font(ev.status == .ok ? .system(size: 12, design: .monospaced) : .system(size: 12))
                            .foregroundColor(.secondary)
                    }
                }
                Spacer()
                if ev.status == .error, let code = ev.barcode, ev.kind != "qr" {
                    Button { onSearchManually(code) } label: {
                        Label("Hledat ručně", systemImage: "magnifyingglass")
                    }
                    .buttonStyle(QuietButtonStyle())
                }
            }
            .padding(20)
            .background(RoundedRectangle(cornerRadius: 12).fill(color(ev).opacity(0.13)))
        } else {
            VStack(spacing: 10) {
                Image(systemName: "barcode.viewfinder").font(.system(size: 54)).foregroundColor(.secondary.opacity(0.4))
                Text("Naskenuj produkt").font(.title3)
                Text("EAN, náš kód i kód dodavatele (MobileSentrix, Apple). Štítek se vytiskne automaticky.")
                    .font(.caption).foregroundColor(.secondary)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 40)
            .background(RoundedRectangle(cornerRadius: 12).fill(Color.primary.opacity(0.04)))
        }
    }

    private func isQR(_ e: ScanEvent) -> Bool { e.kind == "qr" }

    private func color(_ e: ScanEvent) -> Color {
        if e.status == .ok { return Color(NSColor.systemGreen) }
        return isQR(e) ? Color(NSColor.systemOrange) : Color(NSColor.systemRed)
    }

    private func icon(_ e: ScanEvent) -> String {
        if e.status == .ok { return "checkmark" }
        return isQR(e) ? "qrcode" : "xmark"
    }

    private func caption(_ e: ScanEvent) -> String {
        let t = timeSecFormatter.string(from: e.date)
        switch e.status {
        case .ok: return "Vytištěno · \(t)" + (e.offline ? " · bez internetu" : "")
        default:
            switch e.kind {
            case "qr": return "QR kód · \(t)"
            case "nenalezen": return "Nenalezeno · \(t)"
            case "vice": return "Více produktů · \(t)"
            case "tisk": return "Tisk selhal · \(t)"
            case "offline": return "Bez internetu · \(t)"
            default: return "Chyba · \(t)"
            }
        }
    }

    private func title(_ e: ScanEvent) -> String {
        if e.status == .ok, let name = e.name { return name }
        if e.kind == "nenalezen", let b = e.barcode { return "Kód \(b) není v databázi" }
        return e.msg
    }

    private func subtitle(_ e: ScanEvent) -> String? {
        if e.status == .ok, let code = e.code {
            return e.source.map { "\(code) · nalezeno přes \($0)" } ?? code
        }
        if e.kind == "nenalezen" { return "Doplň ho v Shoptetu jako part number, nebo vyber produkt ručně" }
        if e.kind == "tisk", let name = e.name { return name }
        return nil
    }
}

struct ScanHistoryRow: View {
    private func text(_ ev: ScanEvent) -> String {
        if ev.status == .ok { return ev.name ?? ev.msg }
        switch ev.kind {
        case "nenalezen": return "Nenalezeno v databázi"
        case "vice": return "Kód patří více produktům – vyber ručně"
        case "tisk": return "Tisk selhal" + (ev.name.map { ": \($0)" } ?? "")
        default: return ev.msg
        }
    }

    struct Row: Identifiable {
        let event: ScanEvent
        var count = 1
        var id: UUID { event.id }
    }

    let row: Row

    var body: some View {
        let ev = row.event
        return HStack(spacing: 10) {
            Text(timeFormatter.string(from: ev.date))
                .font(.system(size: 12, design: .monospaced))
                .foregroundColor(.secondary)
                .frame(width: 44, alignment: .leading)
            Image(systemName: ev.status == .ok ? "checkmark" : (ev.kind == "qr" ? "qrcode" : "xmark"))
                .foregroundColor(ev.status == .ok ? Color(NSColor.systemGreen)
                                 : (ev.kind == "qr" ? Color(NSColor.systemOrange) : Color(NSColor.systemRed)))
                .frame(width: 16)
            Text(text(ev)).lineLimit(1)
            if row.count > 1 {
                Text("×\(row.count)").foregroundColor(.secondary)
            }
            Spacer()
            if let code = ev.code ?? (ev.kind == "qr" ? nil : ev.barcode) {
                Text(code).font(.system(size: 12, design: .monospaced)).foregroundColor(.secondary)
            }
        }
        .font(.system(size: 13))
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
    }
}
