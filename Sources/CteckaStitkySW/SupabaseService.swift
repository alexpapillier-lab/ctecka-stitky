import Foundation

class SupabaseService {
    static let shared = SupabaseService()

    private let url = "https://osinlzagjimyrzjpdxai.supabase.co/rest/v1/products"
    private let key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9zaW5semFnamlteXJ6anBkeGFpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE2MDUzMDcsImV4cCI6MjA5NzE4MTMwN30.aWkcUv9jpwbqQ3fSHZ_damRGwSqxC_YtH3siySoMgq4"

    func fetchAll() async throws -> [Product] {
        var all: [Product] = []
        var offset = 0
        let batch = 1000
        while true {
            var req = URLRequest(url: URL(string: "\(url)?select=code,ean,name,pair_code,show_weee&order=code")!)
            req.setValue(key, forHTTPHeaderField: "apikey")
            req.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
            req.setValue("\(offset)-\(offset + batch - 1)", forHTTPHeaderField: "Range")
            let (data, _) = try await URLSession.shared.data(for: req)
            let batch_result = try JSONDecoder().decode([Product].self, from: data)
            all.append(contentsOf: batch_result)
            if batch_result.count < batch { break }
            offset += batch
        }
        WEEEPrefs.shared.populate(from: all.map { (code: $0.code, showWeee: $0.show_weee) })
        return all
    }
}
