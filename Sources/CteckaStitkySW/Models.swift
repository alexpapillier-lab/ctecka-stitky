import Foundation

struct Product: Identifiable, Codable, Equatable, Hashable {
    var id: String { code }
    let code: String
    let ean: String
    let name: String
    let pair_code: String?
    let show_weee: Bool?
    /// Kód dodavatele (MobileSentrix / Apple). Pole může nést více kódů oddělených mezerou.
    let part_number: String?
    /// Dovozce: "apple" | "iswap" | "dyson" | "mobilesentrix" | nil. Předává se Python skriptům.
    let dovozce: String?
    /// Příznaky z DB. nil = sloupec chybí nebo není vyplněný → rozhodne heuristika z názvu.
    let je_displej: Bool?
    let potrebuje_sn: Bool?
    /// false = produkt už není v Shoptetu (nastavuje denní sync). nil = sloupec chybí → aktivní.
    let aktivni: Bool?

    var isActive: Bool { aktivni ?? true }

    var isDisplay: Bool { je_displej ?? isDisplayByName }

    private var isDisplayByName: Bool {
        // Vezmi část před "|" jako typ produktu
        let typePart = (name.contains("|") ? String(name.split(separator: "|").first ?? "") : name)
            .trimmingCharacters(in: .whitespaces).lowercased()
        // Vyřaď věci "pod displej", "těsnění", "lepidlo", "kabel k displeji" apod.
        let excludeWords = ["pod displej", "pod display", "těsnění", "lepidlo", "sklíčko", "kabel k", "rámeček"]
        if excludeWords.contains(where: { typePart.contains($0) }) { return false }
        return typePart.hasPrefix("lcd") || typePart.hasPrefix("oled") ||
               typePart.hasPrefix("displej") || typePart.hasPrefix("originální lcd") ||
               typePart.hasPrefix("originální oled") || typePart.hasPrefix("originální displej") ||
               typePart.contains("lcd displej") || typePart.contains("oled displej")
    }

    var defaultLength: Int { isDisplay ? 125 : 62 }

    /// AirPods sluchátka/nabíjecí pouzdra se trackují podle sériového čísla jednotky
    /// (párování/záruka) – vyžadují ruční vepsání SN před tiskem. Musí odpovídat
    /// needs_serial_number v label_printer.py.
    var needsSerialNumber: Bool { potrebuje_sn ?? needsSerialNumberByName }

    private var needsSerialNumberByName: Bool {
        let n = name.lowercased().trimmingCharacters(in: .whitespaces)
        guard n.contains("airpod"), n.hasPrefix("náhradní") else { return false }
        return n.contains("sluchátko") || n.contains("pouzdr")
    }

    /// "Flex kabel – Sierra Blue | iPhone 13 Pro" → ("Flex kabel – Sierra Blue", "iPhone 13 Pro").
    /// Bez "|" → (celý název, nil).
    var nameParts: (detail: String, device: String?) {
        guard let i = name.firstIndex(of: "|") else {
            return (name.trimmingCharacters(in: .whitespaces), nil)
        }
        let detail = name[..<i].trimmingCharacters(in: .whitespaces)
        let device = name[name.index(after: i)...].trimmingCharacters(in: .whitespaces)
        return device.isEmpty ? (detail, nil) : (detail, device)
    }

    /// Čitelný název dovozce; nil = v DB nevyplněno (rozhodne se podle názvu při tisku).
    var importerLabel: String? {
        switch dovozce?.lowercased() {
        case "apple": return "Apple"
        case "iswap": return "iSwap.cz"
        case "dyson": return "Dyson"
        case "mobilesentrix": return "MobileSentrix"
        default: return nil
        }
    }
}
