import Foundation

@MainActor
final class ProductsViewModel: ObservableObject {
    enum Source: Equatable {
        case none
        case online(Date)
        case cache(Date)        // bez internetu – použit uložený seznam
        case failed(String)     // bez internetu a bez uloženého seznamu
    }

    @Published private(set) var products: [Product] = []
    @Published var search = ""
    @Published private(set) var isLoading = false
    @Published private(set) var source: Source = .none

    /// Předpočítaný vyhledávací text (bez diakritiky, malá písmena) – hledání je pak rychlé.
    private var index: [(product: Product, key: String)] = []

    static func fold(_ s: String) -> String {
        s.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil).lowercased()
    }

    /// Všechna slova hledání musí sedět (v libovolném pořadí): "13 pro flex".
    /// Vyřazené produkty (není v Shoptetu) až na konci.
    var filtered: [Product] {
        let words = Self.fold(search).split(separator: " ").map(String.init)
        let hits = words.isEmpty ? index : index.filter { item in words.allSatisfy { item.key.contains($0) } }
        let list = hits.map(\.product)
        return list.filter(\.isActive) + list.filter { !$0.isActive }
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let result = try await SupabaseService.shared.fetchAll()
            apply(result)
            source = .online(Date())
            ProductCache.save(result)
        } catch {
            if let cached = ProductCache.load() {
                apply(cached.products)
                source = .cache(cached.date)
            } else if products.isEmpty {
                source = .failed(error.localizedDescription)
            }
        }
    }

    private func apply(_ list: [Product]) {
        products = list
        index = list.map { p in
            (p, Self.fold([p.code, p.name, p.ean, p.part_number ?? ""].joined(separator: " ")))
        }
        WEEEPrefs.shared.populate(from: list.map { (code: $0.code, showWeee: $0.show_weee) })
    }
}
