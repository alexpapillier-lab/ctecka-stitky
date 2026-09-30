import Foundation

/// Jediné místo s adresou a klíčem Supabase. Používá SupabaseService i WEEEPrefs.
enum SupabaseConfig {
    static let baseURL = "https://osinlzagjimyrzjpdxai.supabase.co/rest/v1"
    static let anonKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9zaW5semFnamlteXJ6anBkeGFpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE2MDUzMDcsImV4cCI6MjA5NzE4MTMwN30.aWkcUv9jpwbqQ3fSHZ_damRGwSqxC_YtH3siySoMgq4"

    /// Request na `baseURL + path` s nastavenými apikey + Authorization headery.
    /// `path` začíná lomítkem, např. "/products?select=code".
    static func request(_ path: String) -> URLRequest {
        var req = URLRequest(url: URL(string: baseURL + path)!)
        req.setValue(anonKey, forHTTPHeaderField: "apikey")
        req.setValue("Bearer \(anonKey)", forHTTPHeaderField: "Authorization")
        return req
    }
}

class SupabaseService {
    static let shared = SupabaseService()

    /// Nové (nullable) sloupce dovozce / je_displej / potrebuje_sn. Pokud v DB ještě
    /// nejsou, dotaz vrátí 400 – pak se spadne na `legacySelect`.
    private let fullSelect = "code,ean,name,pair_code,show_weee,part_number,dovozce,je_displej,potrebuje_sn"
    private let legacySelect = "code,ean,name,pair_code,show_weee,part_number"

    func fetchAll() async throws -> [Product] {
        let all: [Product]
        do {
            all = try await fetchAll(select: fullSelect)
        } catch {
            // Sloupce ještě nemusí existovat – zkus starý select, nové property se dekódují jako nil.
            all = try await fetchAll(select: legacySelect)
        }
        WEEEPrefs.shared.populate(from: all.map { (code: $0.code, showWeee: $0.show_weee) })
        return all
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
