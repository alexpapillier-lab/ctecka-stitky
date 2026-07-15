import Foundation

struct Product: Identifiable, Decodable, Equatable, Hashable {
    var id: String { code }
    let code: String
    let ean: String
    let name: String
    let pair_code: String?
    let show_weee: Bool?
    /// Kód dodavatele (MobileSentrix / Apple). Pole může nést více kódů oddělených mezerou.
    let part_number: String?

    var isDisplay: Bool {
        // Vezmi část před "|" jako typ produktu
        let typePart = (name.contains("|") ? String(name.split(separator: "|").first ?? "") : name)
            .trimmingCharacters(in: .whitespaces).lowercased()
        // Vyřaď věci "pod displej", "těsnění", "lepidlo", "kabel k displeji" apod.
        let excludeWords = ["pod displej", "pod display", "těsnění", "lepidlo", "sklíčko", "kabel k", "rámeček"]
        if excludeWords.contains(where: { typePart.contains($0) }) { return false }
        // Skutečný displej začíná nebo obsahuje lcd/oled/displej jako hlavní slovo
        return typePart.hasPrefix("lcd") || typePart.hasPrefix("oled") ||
               typePart.hasPrefix("displej") || typePart.hasPrefix("originální lcd") ||
               typePart.hasPrefix("originální oled") || typePart.hasPrefix("originální displej") ||
               typePart.contains("lcd displej") || typePart.contains("oled displej")
    }

    var defaultLength: Int { isDisplay ? 125 : 62 }
}
