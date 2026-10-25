import SwiftUI
import AppKit

/// Jediná výrazná akce na obrazovce (Tisknout). Vlastní styl, protože
/// .borderedProminent je až od macOS 12 a iMac běží na Big Sur.
struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 14, weight: .semibold))
            .foregroundColor(.white)
            .padding(.horizontal, 20)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color(NSColor.systemBlue).opacity(configuration.isPressed ? 0.75 : 1))
            )
            .contentShape(Rectangle())
    }
}

/// Menší ohraničené tlačítko (− / +, Zkusit znovu…).
struct QuietButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color.primary.opacity(configuration.isPressed ? 0.12 : 0.05))
            )
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.primary.opacity(0.12), lineWidth: 0.5))
            .contentShape(Rectangle())
    }
}

/// Malý štítek v seznamu / detailu ("Displej", "SN", "Apple"…).
struct Tag: View {
    let text: String
    var color: Color = .secondary
    var mono = false

    var body: some View {
        Text(text)
            .font(mono ? .system(size: 11, design: .monospaced) : .system(size: 11, weight: .medium))
            .lineLimit(1)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(RoundedRectangle(cornerRadius: 4).fill(color.opacity(0.14)))
            .foregroundColor(color)
    }
}

/// Indikátor stavu v horní liště: tečka + text v kapsli.
struct StatusPill: View {
    enum Level { case ok, warning, error, unknown }
    let label: String
    let level: Level
    var help: String = ""

    private var color: Color {
        switch level {
        case .ok: return Color(NSColor.systemGreen)
        case .warning: return Color(NSColor.systemOrange)
        case .error: return Color(NSColor.systemRed)
        case .unknown: return Color.secondary.opacity(0.5)
        }
    }

    var body: some View {
        HStack(spacing: 5) {
            Circle().fill(color).frame(width: 7, height: 7)
            Text(label).font(.system(size: 11, weight: .medium))
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 4)
        .overlay(Capsule().stroke(Color.primary.opacity(0.14), lineWidth: 0.5))
        .foregroundColor(level == .error ? color : .secondary)
        .help(help)
    }
}

struct ProductTag: Identifiable {
    let text: String
    let color: Color
    var id: String { text }
}

extension Product {
    /// Štítky pro řádek seznamu: jen to, co je výjimka (MobileSentrix je výchozí, nezobrazuje se).
    var tags: [ProductTag] {
        var t: [ProductTag] = []
        if needsSerialNumber { t.append(ProductTag(text: "SN", color: Color(NSColor.systemOrange))) }
        if isDisplay { t.append(ProductTag(text: "Displej", color: Color(NSColor.systemBlue))) }
        switch dovozce?.lowercased() {
        case "apple": t.append(ProductTag(text: "Apple", color: .secondary))
        case "iswap": t.append(ProductTag(text: "iSwap", color: Color(NSColor.systemGreen)))
        case "dyson": t.append(ProductTag(text: "Dyson", color: Color(NSColor.systemPurple)))
        default: break
        }
        return t
    }
}

let timeFormatter: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "H:mm"
    return f
}()

let timeSecFormatter: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "H:mm:ss"
    return f
}()

let dayTimeFormatter: DateFormatter = {
    let f = DateFormatter()
    f.locale = Locale(identifier: "cs_CZ")
    f.dateFormat = "d. M. H:mm"
    return f
}()
