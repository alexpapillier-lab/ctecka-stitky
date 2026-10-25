import Foundation

/// Jediné místo s adresou a klíčem Supabase. Používá SupabaseService i WEEEPrefs.
enum SupabaseConfig {
    static let baseURL = "https://osinlzagjimyrzjpdxai.supabase.co/rest/v1"
    static let anonKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9zaW5semFnamlteXJ6anBkeGFpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE2MDUzMDcsImV4cCI6MjA5NzE4MTMwN30.aWkcUv9jpwbqQ3fSHZ_damRGwSqxC_YtH3siySoMgq4"

    /// Request na `baseURL + path` s nastavenými apikey + Authorization headery.
    /// Krátký timeout: bez internetu se má rychle přejít na uložený seznam.
    static func request(_ path: String) -> URLRequest {
        var req = URLRequest(url: URL(string: baseURL + path)!, timeoutInterval: 12)
        req.setValue(anonKey, forHTTPHeaderField: "apikey")
        req.setValue("Bearer \(anonKey)", forHTTPHeaderField: "Authorization")
        return req
    }
}

class SupabaseService {
    static let shared = SupabaseService()

    /// Od nejnovějšího: když sloupec v DB ještě není, PostgREST vrátí 400 → zkusí se starší select.
    private let selects = [
        "code,ean,name,pair_code,show_weee,part_number,dovozce,je_displej,potrebuje_sn,aktivni",
        "code,ean,name,pair_code,show_weee,part_number,dovozce,je_displej,potrebuje_sn",
        "code,ean,name,pair_code,show_weee,part_number",
    ]

    func fetchAll() async throws -> [Product] {
        #if DEBUG
        if ProcessInfo.processInfo.environment["STITKY_DEMO_OFFLINE"] == "1" {
            throw URLError(.notConnectedToInternet)
        }
        #endif
        var lastError: Error = URLError(.unknown)
        for select in selects {
            do {
                return try await fetchAll(select: select)
            } catch let e as URLError where e.code == .badServerResponse {
                lastError = e          // 400 – sloupec chybí, zkus starší select
            }
            // Síťová chyba (offline) se propaguje hned – další selecty by dopadly stejně.
        }
        throw lastError
    }

    private func fetchAll(select: String) async throws -> [Product] {
        var all: [Product] = []
        var offset = 0
        let batch = 1000
        while true {
            var req = SupabaseConfig.request("/products?select=\(select)&order=code")
            req.setValue("\(offset)-\(offset + batch - 1)", forHTTPHeaderField: "Range")
            let (data, response) = try await URLSession.shared.data(for: req)
            if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                throw URLError(.badServerResponse)
            }
            let batchResult = try JSONDecoder().decode([Product].self, from: data)
            all.append(contentsOf: batchResult)
            if batchResult.count < batch { break }
            offset += batch
        }
        return all
    }
}

/// Lokální kopie seznamu produktů vedle binárky (products_cache.json). Ukládá se po
/// každém úspěšném načtení; bez internetu ji použije appka i scan mód (scan_print.py).
enum ProductCache {
    static var url: URL { Paths.appDir.appendingPathComponent("products_cache.json") }

    /// Místní čas bez zóny – scan_print.py ho jen zobrazuje.
    private static let formatter: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return f
    }()

    private struct File: Codable {
        let saved_at: String
        let products: [Product]
    }

    static func save(_ products: [Product]) {
        let file = File(saved_at: formatter.string(from: Date()), products: products)
        do {
            let data = try JSONEncoder().encode(file)
            try data.write(to: url, options: .atomic)
        } catch {
            NSLog("ProductCache: uložení selhalo: %@", error.localizedDescription)
        }
    }

    static func load() -> (date: Date, products: [Product])? {
        guard let data = try? Data(contentsOf: url),
              let file = try? JSONDecoder().decode(File.self, from: data),
              !file.products.isEmpty else { return nil }
        return (formatter.date(from: file.saved_at) ?? Date.distantPast, file.products)
    }
}
