import Foundation

class WEEEPrefs {
    static let shared = WEEEPrefs()

    private let baseURL = "https://osinlzagjimyrzjpdxai.supabase.co/rest/v1/products"
    private let key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ0.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9zaW5semFnamlteXJ6anBkeGFpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE2MDUzMDcsImV4cCI6MjA5NzE4MTMwN30.aWkcUv9jpwbqQ3fSHZ_damRGwSqxC_YtH3siySoMgq4"

    // Lokální cache – načteno při startu z DB
    private var cache: [String: Bool?] = [:]

    // Naplní cache hodnotami ze všech produktů (voláno po fetchAll)
    func populate(from products: [(code: String, showWeee: Bool?)]) {
        for p in products { cache[p.code] = p.showWeee }
    }

    func hasChoice(for code: String) -> Bool {
        guard let entry = cache[code] else { return false }
        return entry != nil
    }

    func get(for code: String) -> Bool {
        cache[code].flatMap { $0 } ?? true
    }

    func set(_ value: Bool, for code: String) async {
        cache[code] = value
        await patch(code: code, value: value)
    }

    private func patch(code: String, value: Bool) async {
        guard let encoded = code.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
              let url = URL(string: "\(baseURL)?code=eq.\(encoded)") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "PATCH"
        req.setValue(key, forHTTPHeaderField: "apikey")
        req.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["show_weee": value])
        _ = try? await URLSession.shared.data(for: req)
    }
}
