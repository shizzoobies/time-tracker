import SwiftUI

// MARK: - MonthSummaryView

struct MonthSummaryView: View {

    @State private var displayYear  : Int
    @State private var displayMonth : Int
    @State private var entries      : [TimeEntry] = []
    @State private var isLoading    = false
    @State private var errorMsg     : String?
    @State private var showError    = false

    @AppStorage("retainer_amount") private var retainerAmount: Double = 0

    init() {
        let now = Calendar.current
        _displayYear  = State(initialValue: now.component(.year,  from: Date()))
        _displayMonth = State(initialValue: now.component(.month, from: Date()))
    }

    // MARK: - Computed

    private var monthLabel: String {
        let f = DateFormatter()
        f.dateFormat = "MMMM yyyy"
        var comps       = DateComponents()
        comps.year      = displayYear
        comps.month     = displayMonth
        comps.day       = 1
        let date        = Calendar.current.date(from: comps) ?? Date()
        return f.string(from: date)
    }

    private var totalHours: Double {
        entries.reduce(0) { $0 + $1.hours }
    }

    /// Hours per week (Mon–Sun) for the current displayed month, padded to 4 values.
    private var weeklyHours: [Double] {
        var cal        = Calendar(identifier: .gregorian)
        cal.firstWeekday = 2
        var buckets    : [Int: Double] = [:]
        for entry in entries {
            let f    = DateFormatter()
            f.dateFormat = "yyyy-MM-dd"
            guard let date = f.date(from: entry.date) else { continue }
            let week = cal.component(.weekOfMonth, from: date)
            buckets[week, default: 0] += entry.hours
        }
        let sorted = buckets.sorted { $0.key < $1.key }.map(\.value)
        // Pad to at least 4 weeks
        var result = sorted
        while result.count < 4 { result.append(0) }
        return result
    }

    // MARK: - Body

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {

                    // ── Month navigation ──
                    HStack {
                        Button { changeMonth(-1) } label: {
                            Image(systemName: "chevron.left")
                                .font(.title3.weight(.semibold))
                                .foregroundColor(.brand)
                        }
                        Spacer()
                        Text(monthLabel)
                            .font(.title3.weight(.bold))
                            .foregroundColor(.brandDark)
                        Spacer()
                        Button { changeMonth(1) } label: {
                            Image(systemName: "chevron.right")
                                .font(.title3.weight(.semibold))
                                .foregroundColor(.brand)
                        }
                    }
                    .padding(.horizontal, 20)
                    .padding(.top, 8)

                    if isLoading {
                        ProgressView("Loading…").tint(.brand).padding(.top, 40)
                    } else {
                        // ── Stats cards ──
                        HStack(spacing: 12) {
                            StatCard(
                                title: "Total Hours",
                                value: String(format: "%.1f", totalHours),
                                unit: "hrs",
                                color: .brand
                            )
                            StatCard(
                                title: retainerAmount > 0 ? "Retainer" : "Est. Amount",
                                value: retainerAmount > 0
                                    ? String(format: "$%.0f", retainerAmount)
                                    : "—",
                                unit: retainerAmount > 0 ? "/mo" : "",
                                color: .brandGold
                            )
                        }
                        .padding(.horizontal)

                        // ── Bar chart ──
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Hours by Week")
                                .font(.headline)
                                .foregroundColor(.brandDark)
                                .padding(.horizontal)

                            WeeklyBarChart(weeklyHours: weeklyHours)
                                .frame(height: 160)
                                .padding(.horizontal)
                        }
                        .padding(.vertical, 16)
                        .background(Color.white)
                        .clipShape(RoundedRectangle(cornerRadius: 16))
                        .shadow(color: .black.opacity(0.05), radius: 6, y: 2)
                        .padding(.horizontal)

                        // ── Entry count ──
                        HStack {
                            Image(systemName: "list.bullet")
                                .foregroundColor(.brandMuted)
                            Text("\(entries.count) entries logged this month")
                                .font(.subheadline)
                                .foregroundColor(.brandMuted)
                            Spacer()
                        }
                        .padding(.horizontal, 24)
                    }

                    Spacer(minLength: 40)
                }
                .padding(.top, 8)
            }
            .background(Color.brandBg.ignoresSafeArea())
            .navigationTitle("Month")
            .navigationBarTitleDisplayMode(.inline)
            .task { await loadEntries() }
            .alert("Error", isPresented: $showError, presenting: errorMsg) { _ in
                Button("OK", role: .cancel) {}
            } message: { msg in Text(msg) }
        }
    }

    // MARK: - Data

    private func loadEntries() async {
        isLoading = true
        defer { isLoading = false }
        do {
            entries = try await SupabaseService.shared.fetchEntriesForMonth(
                year: displayYear, month: displayMonth
            )
        } catch {
            errorMsg  = error.localizedDescription
            showError = true
        }
    }

    private func changeMonth(_ delta: Int) {
        var comps       = DateComponents()
        comps.year      = displayYear
        comps.month     = displayMonth + delta
        comps.day       = 1
        let date        = Calendar.current.date(from: comps) ?? Date()
        let cal         = Calendar.current
        displayYear     = cal.component(.year,  from: date)
        displayMonth    = cal.component(.month, from: date)
        Task { await loadEntries() }
    }
}

// MARK: - StatCard

private struct StatCard: View {
    let title : String
    let value : String
    let unit  : String
    let color : Color

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title.uppercased())
                .font(.caption2)
                .fontWeight(.semibold)
                .foregroundColor(.brandMuted)
                .kerning(0.8)
            HStack(alignment: .lastTextBaseline, spacing: 2) {
                Text(value)
                    .font(.system(size: 28, weight: .bold, design: .rounded))
                    .foregroundColor(color)
                if !unit.isEmpty {
                    Text(unit)
                        .font(.caption)
                        .foregroundColor(.brandMuted)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(Color.white)
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .shadow(color: .black.opacity(0.05), radius: 6, y: 2)
    }
}

// MARK: - WeeklyBarChart (pure SwiftUI shapes, no external libs)

private struct WeeklyBarChart: View {
    let weeklyHours: [Double]

    private var maxHours: Double {
        max(weeklyHours.max() ?? 1, 1)
    }

    var body: some View {
        HStack(alignment: .bottom, spacing: 12) {
            ForEach(Array(weeklyHours.enumerated()), id: \.offset) { idx, hours in
                VStack(spacing: 6) {
                    Text(String(format: "%.1f", hours))
                        .font(.caption2)
                        .foregroundColor(.brandMuted)

                    GeometryReader { geo in
                        let barH = hours > 0
                            ? max((hours / maxHours) * geo.size.height, 4)
                            : 4
                        VStack {
                            Spacer()
                            RoundedRectangle(cornerRadius: 6)
                                .fill(hours > 0 ? Color.brand : Color.brandMuted.opacity(0.2))
                                .frame(height: barH)
                        }
                    }

                    Text("W\(idx + 1)")
                        .font(.caption2)
                        .foregroundColor(.brandMuted)
                }
            }
        }
        .animation(.easeOut(duration: 0.4), value: weeklyHours)
    }
}

#Preview {
    MonthSummaryView()
}
