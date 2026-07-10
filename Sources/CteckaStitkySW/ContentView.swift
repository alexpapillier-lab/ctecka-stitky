import SwiftUI
import AppKit

struct ContentView: View {
    @State private var mode: AppMode = .manual

    enum AppMode { case manual, scan }

    var body: some View {
        VStack(spacing: 0) {
            // ── Tab bar ──────────────────────────────────────────
            HStack(spacing: 0) {
                ModeTab(title: "Ruční výběr", icon: "hand.tap", selected: mode == .manual) {
                    mode = .manual
                }
                ModeTab(title: "Scan mód", icon: "barcode.viewfinder", selected: mode == .scan) {
                    mode = .scan
                }
            }
            .background(Color(NSColor.windowBackgroundColor))

            Divider()

            if mode == .manual {
                ManualView()
            } else {
                ScanView()
            }
        }
        .frame(minWidth: 820, minHeight: 540)
    }
}

// ── Tab tlačítko ─────────────────────────────────────────────────
struct ModeTab: View {
    let title: String
    let icon: String
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                Text(title)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 10)
            .background(selected ? Color.accentColor.opacity(0.12) : Color.clear)
            .foregroundColor(selected ? .accentColor : .secondary)
        }
        .buttonStyle(.plain)
        .overlay(
            Group {
                if selected {
                    VStack { Spacer(); Rectangle().frame(height: 2).foregroundColor(.accentColor) }
                }
            }
        )
    }
}

// ── Ruční výběr ──────────────────────────────────────────────────
struct ManualView: View {
    @StateObject private var vm = ProductsViewModel()
    @State private var selected: Product?
    @State private var labelImage: NSImage?
    @State private var isGenerating = false
    @State private var isPrinting = false
    @State private var copies = 1
    @State private var lengthMM = 62
    @State private var dpi600 = true
    @State private var savedPath: String?
    @State private var printResult: PrintResult?
    @State private var showWEEEDialog = false
    @State private var pendingAction: PendingAction?

    enum PendingAction { case generate, print }

    enum PrintResult { case ok, error(String) }

    var body: some View {
        HSplitView {
            // Levý panel – seznam
            VStack(spacing: 0) {
                HStack {
                    Image(systemName: "magnifyingglass").foregroundColor(.secondary)
                    TextField("Hledat kód nebo název…", text: $vm.search).textFieldStyle(.plain)
                    if !vm.search.isEmpty {
                        Button { vm.search = "" } label: {
                            Image(systemName: "xmark.circle.fill").foregroundColor(.secondary)
                        }.buttonStyle(.plain)
                    }
                }
                .padding(10)
                .background(Color(NSColor.controlBackgroundColor))

                Divider()

                List(vm.filtered, selection: $selected) { product in
                    ProductRow(product: product).tag(product)
                }
                .listStyle(.inset)

                Divider()
                HStack {
                    if vm.isLoading { ProgressView().scaleEffect(0.6) }
                    Text(vm.isLoading ? "Načítám…" : "\(vm.products.count) produktů")
                        .font(.caption).foregroundColor(.secondary)
                    Spacer()
                    Button { Task { await vm.load() } } label: {
                        Image(systemName: "arrow.clockwise")
                    }.buttonStyle(.plain)
                }
                .padding(.horizontal, 10).padding(.vertical, 6)
            }
            .frame(minWidth: 280, maxWidth: 380)

            // Pravý panel – náhled + tisk
            VStack(spacing: 0) {
                if let product = selected {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(product.code).font(.headline)
                                Text(product.name).font(.subheadline).foregroundColor(.secondary).lineLimit(2)
                            }
                            Spacer()
                            if product.isDisplay {
                                Label("Displej", systemImage: "rectangle.fill")
                                    .font(.caption)
                                    .padding(.horizontal, 8).padding(.vertical, 3)
                                    .background(Color.blue.opacity(0.15))
                                    .foregroundColor(.blue)
                                    .cornerRadius(6)
                            }
                        }

                        HStack(spacing: 16) {
                            HStack {
                                Text("Délka:").foregroundColor(.secondary)
                                TextField("", text: Binding(
                                    get: { "\(lengthMM)" },
                                    set: { if let v = Int($0) { lengthMM = v } }
                                ))
                                .frame(width: 60).textFieldStyle(.roundedBorder)
                                Text("mm").foregroundColor(.secondary)
                            }
                            HStack {
                                Text("Kopií:").foregroundColor(.secondary)
                                Stepper("\(copies)", value: $copies, in: 1...50).frame(width: 100)
                            }
                            Picker("", selection: $dpi600) {
                                Text("300 DPI").tag(false)
                                Text("600 DPI").tag(true)
                            }
                            .pickerStyle(.segmented)
                            .frame(width: 140)
                            .help("Kvalita tisku – 600 DPI je ostřejší, ale pomalejší")
                            Spacer()
                            Button {
                                Task { await generate(product: product) }
                            } label: {
                                Label("Náhled", systemImage: "eye")
                            }
                            .buttonStyle(.bordered)
                            .disabled(isGenerating || isPrinting)

                            Button {
                                Task { await doPrint(product: product) }
                            } label: {
                                if isPrinting {
                                    ProgressView().scaleEffect(0.7).frame(width: 16, height: 16)
                                } else {
                                    Label("Tisknout", systemImage: "printer")
                                }
                            }
                            .buttonStyle(.bordered)
                            .disabled(isGenerating || isPrinting)
                        }

                        // Výsledek tisku
                        if let r = printResult {
                            HStack(spacing: 6) {
                                switch r {
                                case .ok:
                                    Image(systemName: "checkmark.circle.fill").foregroundColor(.green)
                                    Text("Vytištěno").foregroundColor(.green)
                                case .error(let msg):
                                    Image(systemName: "xmark.circle.fill").foregroundColor(.red)
                                    Text(msg).foregroundColor(.red).lineLimit(2)
                                }
                            }
                            .font(.caption)
                        }
                    }
                    .padding(16)
                    .background(Color(NSColor.controlBackgroundColor))

                    Divider()

                    ZStack {
                        Color(NSColor.windowBackgroundColor)
                        if isGenerating {
                            VStack(spacing: 12) {
                                ProgressView()
                                Text("Generuji náhled…").foregroundColor(.secondary)
                            }
                        } else if let img = labelImage {
                            VStack(spacing: 16) {
                                Image(nsImage: img)
                                    .resizable().scaledToFit()
                                    .padding(20)
                                    .background(Color.white)
                                    .cornerRadius(8)
                                    .shadow(color: .black.opacity(0.12), radius: 8, x: 0, y: 2)
                                    .padding()

                                HStack(spacing: 12) {
                                    if let path = savedPath {
                                        Label(path, systemImage: "checkmark.circle.fill")
                                            .font(.caption).foregroundColor(.green)
                                            .lineLimit(1).truncationMode(.middle)
                                    }
                                    Spacer()
                                    Button { savePNG(image: img, code: product.code) } label: {
                                        Label("Uložit PNG", systemImage: "square.and.arrow.down")
                                    }.buttonStyle(.bordered)
                                }
                                .padding(.horizontal, 20).padding(.bottom, 16)
                            }
                        } else {
                            VStack(spacing: 8) {
                                Image(systemName: "tag")
                                    .font(.system(size: 48)).foregroundColor(.secondary.opacity(0.4))
                                Text("Klikni Náhled nebo rovnou Tisknout")
                                    .foregroundColor(.secondary)
                            }
                        }
                    }
                } else {
                    VStack(spacing: 12) {
                        Image(systemName: "tag.fill")
                            .font(.system(size: 64)).foregroundColor(.secondary.opacity(0.25))
                        Text("Vyber produkt ze seznamu")
                            .font(.title3).foregroundColor(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Color(NSColor.windowBackgroundColor))
                }
            }
            .frame(minWidth: 500)
        }
        .onAppear { Task { await vm.load() } }
        .alert(isPresented: $showWEEEDialog) {
            Alert(
                title: Text("Zobrazit ikonu přeškrtnuté popelnice (WEEE)?"),
                message: Text("Volba se uloží pro příští tisky tohoto produktu."),
                primaryButton: .default(Text("Ano – zobrazit")) {
                    if let p = selected {
                        Task { await WEEEPrefs.shared.set(true, for: p.code) }
                        runPendingAction(product: p)
                    }
                },
                secondaryButton: .cancel(Text("Ne – nezobrazovat")) {
                    if let p = selected {
                        Task { await WEEEPrefs.shared.set(false, for: p.code) }
                        runPendingAction(product: p)
                    }
                }
            )
        }
        .onChange(of: selected) { product in
            labelImage = nil
            savedPath = nil
            printResult = nil
            if let p = product { lengthMM = p.defaultLength }
        }
    }

    private func generate(product: Product) async {
        if !WEEEPrefs.shared.hasChoice(for: product.code) {
            await MainActor.run {
                pendingAction = .generate
                showWEEEDialog = true
            }
            return
        }
        await doGenerate(product: product)
    }

    private func doGenerate(product: Product) async {
        isGenerating = true
        labelImage = nil
        let weee = WEEEPrefs.shared.get(for: product.code)
        labelImage = await LabelGenerator.generate(code: product.code, name: product.name, lengthMM: lengthMM, dpi600: dpi600, weee: weee)
        isGenerating = false
    }

    private func doPrint(product: Product) async {
        if !WEEEPrefs.shared.hasChoice(for: product.code) {
            await MainActor.run {
                pendingAction = .print
                showWEEEDialog = true
            }
            return
        }
        await doActualPrint(product: product)
    }

    private func doActualPrint(product: Product) async {
        isPrinting = true
        printResult = nil
        let weee = WEEEPrefs.shared.get(for: product.code)
        let (ok, err) = await PrintService.shared.print(
            code: product.code, name: product.name, lengthMM: lengthMM, copies: copies, dpi600: dpi600, weee: weee
        )
        isPrinting = false
        printResult = ok ? .ok : .error(err ?? "Neznámá chyba")
    }

    private func runPendingAction(product: Product) {
        let action = pendingAction
        pendingAction = nil
        Task {
            switch action {
            case .generate: await doGenerate(product: product)
            case .print:    await doActualPrint(product: product)
            case nil:       break
            }
        }
    }

    private func savePNG(image: NSImage, code: String) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "stitek_\(code).png"
        panel.allowedContentTypes = [.png]
        panel.begin { resp in
            guard resp == .OK, let url = panel.url else { return }
            if let tiff = image.tiffRepresentation,
               let rep = NSBitmapImageRep(data: tiff),
               let data = rep.representation(using: .png, properties: [:]) {
                try? data.write(to: url)
                savedPath = url.lastPathComponent
            }
        }
    }
}

// ── Scan mód ─────────────────────────────────────────────────────
struct ScanView: View {
    @StateObject private var scan = ScanService.shared

    var body: some View {
        VStack(spacing: 0) {
            // Toolbar
            HStack(spacing: 12) {
                Circle()
                    .fill(scan.isRunning ? Color.green : Color.gray.opacity(0.4))
                    .frame(width: 10, height: 10)
                Text(scan.isRunning ? "Aktivní – skenuj produkt" : "Zastaven")
                    .foregroundColor(scan.isRunning ? .primary : .secondary)
                Spacer()
                Button {
                    if scan.isRunning { scan.stop() } else { scan.start() }
                } label: {
                    Label(scan.isRunning ? "Zastavit" : "Spustit",
                          systemImage: scan.isRunning ? "stop.circle" : "play.circle")
                }
                .buttonStyle(.bordered)
                .foregroundColor(scan.isRunning ? .red : .green)
            }
            .padding(16)
            .background(Color(NSColor.controlBackgroundColor))

            Divider()

            // Log událostí
            if scan.events.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "barcode.viewfinder")
                        .font(.system(size: 56)).foregroundColor(.secondary.opacity(0.3))
                    Text("Spusť scan mód a naskenuj produkt")
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color(NSColor.windowBackgroundColor))
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 2) {
                        ForEach(scan.events) { ev in
                            ScanEventRow(event: ev)
                        }
                    }
                    .padding(12)
                }
                .background(Color(NSColor.windowBackgroundColor))
            }
        }
    }
}

struct ScanEventRow: View {
    let event: ScanEvent

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
                .foregroundColor(color)
                .frame(width: 16)
            Text(event.msg)
                .font(.system(.body, design: .monospaced))
                .foregroundColor(.primary)
        }
        .padding(.vertical, 3)
    }

    var icon: String {
        switch event.status {
        case .ok:    return "checkmark.circle.fill"
        case .error: return "xmark.circle.fill"
        case .info:  return "info.circle"
        }
    }

    var color: Color {
        switch event.status {
        case .ok:    return .green
        case .error: return .red
        case .info:  return .secondary
        }
    }
}

// ── Řádek v seznamu ───────────────────────────────────────────────
struct ProductRow: View {
    let product: Product
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(product.code)
                    .font(.system(.body, design: .monospaced))
                    .fontWeight(.medium)
                Spacer()
                Text("\(product.defaultLength)mm")
                    .font(.caption2).foregroundColor(.secondary)
            }
            Text(product.name)
                .font(.caption).foregroundColor(.secondary).lineLimit(1)
        }
        .padding(.vertical, 2)
    }
}

// ── ViewModel ─────────────────────────────────────────────────────
class ProductsViewModel: ObservableObject {
    @Published var products: [Product] = []
    @Published var search = ""
    @Published var isLoading = false

    var filtered: [Product] {
        guard !search.isEmpty else { return products }
        let q = search.lowercased()
        return products.filter { $0.code.lowercased().contains(q) || $0.name.lowercased().contains(q) }
    }

    func load() async {
        await MainActor.run { isLoading = true }
        do {
            let result = try await SupabaseService.shared.fetchAll()
            await MainActor.run { self.products = result; self.isLoading = false }
        } catch {
            await MainActor.run { isLoading = false }
        }
    }
}
