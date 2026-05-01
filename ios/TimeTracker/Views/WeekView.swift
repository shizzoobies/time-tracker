import SwiftUI

// MARK: - WeekView

struct WeekView: View {

    @State private var weekOffset  = 0          // 0 = current week
    @State private var entries     : [TimeEntry] = []
    @State private var isLoading   = false
    @State private var errorMsg    : String?
    @State private var showError   = false
    @State private var deleteTarget: TimeEntry?
    @State private var showDeleteConfirm = false

    // MARK: - Computed week bounds

    private var weekDates: (start: String, end: String) {
        var cal        = Calendar(identifier: .gregorian)
        cal.firstWeekday = 2  // Monday
        let today      = Date()
        let startOfWeek = cal.date(
            from: cal.dateComponents([.yearForWeekOfYear, .weekOfYear], from: today)
        )!
        let offset     = DateComponents(weekOfYear: weekOffset)
        let monday     = cal.date(byAdding: offset, to: startOfWeek)!
        let sunday     = cal.date(byAdding: .day, value: 6, to: monday)!
        return (fmt(monday), fmt(sunday))
    }

    private var weekLabel: String {
        let (s, e) = weekDates
        if weekOffset == 0 { return "This Week" }
        if weekOffset == -1 { return "Last Week" }
        return "\(s)  –  \(e)"
    }

    private var totalHours: Double {
        entries.reduce(0) { $0 + $1.hours }
    }

    private var groupedEntries: [(date: String, entries: [TimeEntry])] {
        let sorted = entries.sorted { $0.date < $1.date }
        var result: [(date: String, entries: [TimeEntry])] = []
        var current: (date: String, entries: [TimeEntry])?
        for e in sorted {
            if current?.date == e.date {
                current!.entries.append(e)
            } else {
                if let c = current { result.append(c) }
                current = (e.date, [e])
            }
        }
        if let c = current { result.append(c) }
        return result
    }

    // MARK: - Body

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {

                // ── Week navigation ──
                HStack {
                    Button {
                        weekOffset -= 1
                        Task { await loadEntries() }
                    } label: {
                        Image(systemName: "chevron.left")
                            .font(.title3.weight(.semibold))
                            .foregroundColor(.brand)
                    }
                    Spacer()
                    Text(weekLabel)
                        .font(.headline)
                        .foregroundColor(.brandDark)
                    Spacer()
                    Button {
                        weekOffset += 1
                        Task { await loadEntries() }
                    } label: {
                        Image(systemName: "chevron.right")
                            .font(.title3.weight(.semibold))
                            .foregroundColor(.brand)
                    }
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 14)
                .background(Color.white)

                // ── Total hours card ──
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("TOTAL HOURS")
                            .font(.caption)
                            .fontWeight(.semibold)
                            .foregroundColor(.brandMuted)
                            .kerning(1)
                        Text(String(format: "%.1f hrs", totalHours))
                            .font(.system(size: 34, weight: .bold, design: .rounded))
                            .foregroundColor(.brandDark)
                    }
                    Spacer()
                    Circle()
                        .fill(Color.brand.opacity(0.1))
                        .frame(width: 56, height: 56)
                        .overlay(
                            Image(systemName: "clock")
                                .foregroundColor(.brand)
                                .font(.title2)
                        )
                }
                .padding(20)
                .background(Color.white)
                .clipShape(RoundedRectangle(cornerRadius: 16))
                .shadow(color: .black.opacity(0.06), radius: 8, y: 2)
                .padding(.horizontal, 16)
                .padding(.top, 12)

                // ── Entry list ──
                if isLoading {
                    Spacer()
                    ProgressView("Loading…")
                        .tint(.brand)
                    Spacer()
                } else if entries.isEmpty {
                    Spacer()
                    VStack(spacing: 12) {
                        Image(systemName: "tray")
                            .font(.system(size: 44))
                            .foregroundColor(.brandMuted.opacity(0.5))
                        Text("No entries this week")
                            .font(.subheadline)
                            .foregroundColor(.brandMuted)
                    }
                    Spacer()
                } else {
                    List {
                        ForEach(groupedEntries, id: \.date) { group in
                            Section {
                                ForEach(group.entries) { entry in
                                    EntryRow(entry: entry)
                                        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                                            Button(role: .destructive) {
                                                deleteTarget = entry
                                                showDeleteConfirm = true
                                            } label: {
                                                Label("Delete", systemImage: "trash")
                                            }
                                        }
                                }
                            } header: {
                                Text(formatDateHeader(group.date))
                                    .font(.caption)
                                    .fontWeight(.semibold)
                                    .foregroundColor(.brandGold)
                                    .textCase(nil)
                            }
                        }
                    }
                    .listStyle(.insetGrouped)
                    .scrollContentBackground(.hidden)
                    .background(Color.brandBg)
                    .refreshable {
                        await loadEntries()
                    }
                }
            }
            .background(Color.brandBg.ignoresSafeArea())
            .navigationTitle("Week")
            .navigationBarTitleDisplayMode(.inline)
            .task { await loadEntries() }
            .alert("Error", isPresented: $showError, presenting: errorMsg) { _ in
                Button("OK", role: .cancel) {}
            } message: { msg in Text(msg) }
            .confirmationDialog(
                "Delete this entry?",
                isPresented: $showDeleteConfirm,
                titleVisibility: .visible
            ) {
                Button("Delete", role: .destructive) {
                    if let t = deleteTarget { Task { await deleteEntry(t) } }
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                if let t = deleteTarget {
                    Text("\(t.description) — \(String(format: "%.1f", t.hours))h")
                }
            }
        }
    }

    // MARK: - Data

    private func loadEntries() async {
        isLoading = true
        defer { isLoading = false }
        let (start, end) = weekDates
        do {
            entries = try await SupabaseService.shared.fetchEntries(from: start, to: end)
        } catch {
            errorMsg  = error.localizedDescription
            showError = true
        }
    }

    private func deleteEntry(_ entry: TimeEntry) async {
        do {
            try await SupabaseService.shared.deleteEntry(id: entry.id)
            entries.removeAll { $0.id == entry.id }
        } catch {
            errorMsg  = error.localizedDescription
            showError = true
        }
    }

    // MARK: - Helpers

    private func fmt(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: date)
    }

    private func formatDateHeader(_ dateStr: String) -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        guard let date = f.date(from: dateStr) else { return dateStr }
        let out = DateFormatter()
        out.dateFormat = "EEEE, MMM d"
        return out.string(from: date)
    }
}

// MARK: - EntryRow

private struct EntryRow: View {
    let entry: TimeEntry

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                if let st = entry.startTime, let et = entry.endTime {
                    Text("\(st) – \(et)")
                        .font(.caption)
                        .foregroundColor(.brandMuted)
                }
                Text(entry.description)
                    .font(.subheadline)
                    .foregroundColor(.brandDark)
                    .lineLimit(2)
                CategoryChip(text: entry.category)
            }
            Spacer()
            Text(String(format: "%.1fh", entry.hours))
                .font(.headline)
                .foregroundColor(.brand)
                .padding(.top, 2)
        }
        .padding(.vertical, 4)
    }
}

#Preview {
    WeekView()
}
