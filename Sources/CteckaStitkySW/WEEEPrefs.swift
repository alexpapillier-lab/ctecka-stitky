import Foundation

class WEEEPrefs {
    static let shared = WEEEPrefs()

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
        guard let encoded = code.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) else { return }
        var req = SupabaseConfig.request("/products?code=eq.\(encoded)")
        req.httpMethod = "PATCH"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["show_weee": value])
        do {
            let (_, response) = try await URLSession.shared.data(for: req)
            if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                NSLog("WEEEPrefs: uložení show_weee pro %@ selhalo (HTTP %d)", code, http.statusCode)
            }
        } catch {
            NSLog("WEEEPrefs: uložení show_weee pro %@ selhalo: %@", code, error.localizedDescription)
        }
    }
}
