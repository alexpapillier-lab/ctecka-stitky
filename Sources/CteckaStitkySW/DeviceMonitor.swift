import Foundation
import IOKit

/// Hlídá, jestli je připojená tiskárna Brother (USB vendor 0x04F9) a čtečka
/// (sériový port /dev/tty.usb*). Kontrola každé 3 s – levné, čte jen IORegistry.
final class DeviceMonitor: ObservableObject {
    @Published private(set) var printerConnected: Bool?
    @Published private(set) var scannerConnected: Bool?
    private var timer: Timer?

    init() {
        check()
        timer = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in self?.check() }
    }

    deinit { timer?.invalidate() }

    func check() {
        let p = Self.brotherPresent()
        let s = Self.scannerPresent()
        if p != printerConnected { printerConnected = p }
        if s != scannerConnected { scannerConnected = s }
    }

    static func brotherPresent() -> Bool {
        // macOS 11 registruje USB zařízení jako IOUSBHostDevice; IOUSBDevice je starší jméno.
        for cls in ["IOUSBHostDevice", "IOUSBDevice"] {
            guard let dict = IOServiceMatching(cls) as NSMutableDictionary? else { continue }
            dict["idVendor"] = 0x04F9
            var iterator: io_iterator_t = 0
            guard IOServiceGetMatchingServices(kIOMasterPortDefault, dict as CFDictionary, &iterator) == KERN_SUCCESS
            else { continue }
            defer { IOObjectRelease(iterator) }
            let service = IOIteratorNext(iterator)
            if service != 0 {
                IOObjectRelease(service)
                return true
            }
        }
        return false
    }

    static func scannerPresent() -> Bool {
        let devs = (try? FileManager.default.contentsOfDirectory(atPath: "/dev")) ?? []
        return devs.contains { $0.hasPrefix("tty.usb") || $0.hasPrefix("cu.usb") || $0.hasPrefix("ttyUSB") }
    }
}
