import SwiftUI

// MARK: - Color helpers

extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3:
            (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6:
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8:
            (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (255, 0, 0, 0)
        }
        self.init(
            .sRGB,
            red:     Double(r) / 255,
            green:   Double(g) / 255,
            blue:    Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
}

// MARK: - Brand colours (app-wide constants)

extension Color {
    static let brand       = Color(hex: "c4006e")   // PB&J pink
    static let brandDark   = Color(hex: "1c1917")   // near-black
    static let brandGold   = Color(hex: "b8882a")   // warm gold
    static let brandBg     = Color(hex: "f6f2ef")   // warm off-white
    static let brandMuted  = Color(hex: "78716c")   // muted stone
}

// MARK: - ContentView

struct ContentView: View {
    var body: some View {
        TabView {
            LogEntryView()
                .tabItem {
                    Label("Log", systemImage: "pencil")
                }

            WeekView()
                .tabItem {
                    Label("Week", systemImage: "calendar")
                }

            MonthSummaryView()
                .tabItem {
                    Label("Month", systemImage: "chart.bar")
                }

            SettingsView()
                .tabItem {
                    Label("Settings", systemImage: "gear")
                }
        }
        .tint(.brand)
        .background(Color.brandBg)
    }
}

#Preview {
    ContentView()
}
