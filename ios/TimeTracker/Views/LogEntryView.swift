import SwiftUI

// MARK: - EditEntrySheet

private struct EditEntrySheet: View {
    @Binding var entry: ParsedEntry
    @Environment(\.dismiss) private var dismiss

    private let categories = [
        "Administrative", "Bookkeeping", "Payroll", "Tax Preparation",
        "Financial Reporting", "Client Communication", "Research", "Training",
        "SEO Audit", "Web Development", "AI Integration", "General"
    ]

    var body: some View {
        NavigationStack {
            Form {
                Section("Date & Hours") {
                    TextField("Date (YYYY-MM-DD)", text: $entry.date)
                        .keyboardType(.numbersAndPunctuation)
                    HStack {
                        Text("Hours")
                        Spacer()
                        TextField("0.0", value: $entry.hours, format: .number)
                            .keyboardType(.decimalPad)
                            .multilineTextAlignment(.trailing)
                            .frame(width: 80)
                    }
                }
                Section("Description") {
                    TextEditor(text: $entry.description)
                        .frame(minHeight: 80)
                }
                Section("Category") {
                    Picker("Category", selection: $entry.category) {
                        ForEach(categories, id: \.self) { cat in
                            Text(cat).tag(cat)
                        }
                    }
                }
                Section("Times (optional)") {
                    TextField("Start time (HH:MM)", text: Binding(
                        get: { entry.startTime ?? "" },
                        set: { entry.startTime = $0.isEmpty ? nil : $0 }
                    ))
                    TextField("End time (HH:MM)", text: Binding(
                        get: { entry.endTime ?? "" },
                        set: { entry.endTime = $0.isEmpty ? nil : $0 }
                    ))
                }
            }
            .navigationTitle("Edit Entry")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                        .foregroundColor(.brand)
                }
            }
        }
    }
}

// MARK: - ParsedEntryRow

private struct ParsedEntryRow: View {
    let index: Int
    @Binding var entry: ParsedEntry
    @State private var showEdit = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(entry.description)
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundColor(.brandDark)
                        .lineLimit(2)
                    HStack(spacing: 8) {
                        Text(entry.date)
                            .font(.caption)
                            .foregroundColor(.brandMuted)
                        CategoryChip(text: entry.category)
                    }
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 4) {
                    Text(String(format: "%.1fh", entry.hours))
                        .font(.headline)
                        .foregroundColor(.brand)
                    Button {
                        showEdit = true
                    } label: {
                        Image(systemName: "pencil.circle")
                            .foregroundColor(.brandMuted)
                            .imageScale(.large)
                    }
                }
            }
        }
        .padding(.vertical, 6)
        .sheet(isPresented: $showEdit) {
            EditEntrySheet(entry: $entry)
        }
    }
}

// MARK: - CategoryChip

struct CategoryChip: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.caption2)
            .fontWeight(.medium)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(Color.brand.opacity(0.12))
            .foregroundColor(.brand)
            .clipShape(Capsule())
    }
}

// MARK: - LogEntryView

struct LogEntryView: View {
    @State private var inputText   = ""
    @State private var parsed      : [ParsedEntry] = []
    @State private var isLoading   = false
    @State private var isSaving    = false
    @State private var errorMsg    : String?
    @State private var showError   = false
    @State private var successMsg  : String?

    private let placeholder = "e.g. Spent 2 hours on payroll reconciliation this morning"

    private var todayFormatted: String {
        let f = DateFormatter()
        f.dateStyle = .full
        return f.string(from: Date())
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {

                    // ── Date header ──
                    Text(todayFormatted)
                        .font(.subheadline)
                        .foregroundColor(.brandMuted)
                        .padding(.horizontal)

                    // ── Input card ──
                    VStack(alignment: .leading, spacing: 12) {
                        ZStack(alignment: .topLeading) {
                            if inputText.isEmpty {
                                Text(placeholder)
                                    .foregroundColor(Color(.placeholderText))
                                    .padding(.horizontal, 4)
                                    .padding(.vertical, 8)
                            }
                            TextEditor(text: $inputText)
                                .frame(minHeight: 120)
                                .scrollContentBackground(.hidden)
                        }
                        .font(.body)
                        .padding(12)
                        .background(Color.white)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(Color.brandMuted.opacity(0.3), lineWidth: 1)
                        )

                        Button {
                            parseWithAI()
                        } label: {
                            HStack {
                                if isLoading {
                                    ProgressView()
                                        .progressViewStyle(.circular)
                                        .tint(.white)
                                        .scaleEffect(0.8)
                                } else {
                                    Image(systemName: "sparkles")
                                }
                                Text(isLoading ? "Parsing…" : "Parse with AI")
                                    .fontWeight(.semibold)
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 14)
                            .background(inputText.isEmpty ? Color.brand.opacity(0.4) : Color.brand)
                            .foregroundColor(.white)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                        }
                        .disabled(inputText.isEmpty || isLoading)
                    }
                    .padding(.horizontal)

                    // ── Parsed results ──
                    if !parsed.isEmpty {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Parsed Entries")
                                .font(.headline)
                                .foregroundColor(.brandDark)
                                .padding(.horizontal)

                            VStack(spacing: 0) {
                                ForEach(Array(parsed.indices), id: \.self) { i in
                                    ParsedEntryRow(index: i, entry: $parsed[i])
                                        .padding(.horizontal)
                                    if i < parsed.count - 1 {
                                        Divider().padding(.leading)
                                    }
                                }
                            }
                            .background(Color.white)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(Color.brandMuted.opacity(0.2), lineWidth: 1)
                            )
                            .padding(.horizontal)

                            if let msg = successMsg {
                                HStack {
                                    Image(systemName: "checkmark.circle.fill")
                                    Text(msg)
                                }
                                .font(.subheadline)
                                .foregroundColor(.green)
                                .padding(.horizontal)
                            }

                            Button {
                                saveAll()
                            } label: {
                                HStack {
                                    if isSaving {
                                        ProgressView()
                                            .progressViewStyle(.circular)
                                            .tint(.white)
                                            .scaleEffect(0.8)
                                    } else {
                                        Image(systemName: "checkmark.circle")
                                    }
                                    Text(isSaving ? "Saving…" : "Add All Entries")
                                        .fontWeight(.semibold)
                                }
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 14)
                                .background(Color.brandDark)
                                .foregroundColor(.white)
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                            }
                            .disabled(isSaving)
                            .padding(.horizontal)
                        }
                    }

                    Spacer(minLength: 40)
                }
                .padding(.top, 16)
            }
            .background(Color.brandBg.ignoresSafeArea())
            .navigationTitle("Log Time")
            .navigationBarTitleDisplayMode(.large)
            .alert("Error", isPresented: $showError, presenting: errorMsg) { _ in
                Button("OK", role: .cancel) {}
            } message: { msg in
                Text(msg)
            }
        }
    }

    // MARK: - Actions

    private func parseWithAI() {
        guard !inputText.isEmpty else { return }
        isLoading  = true
        successMsg = nil
        Task {
            defer { isLoading = false }
            do {
                parsed = try await ClaudeService.shared.parseEntries(text: inputText)
            } catch {
                errorMsg  = error.localizedDescription
                showError = true
            }
        }
    }

    private func saveAll() {
        isSaving   = true
        successMsg = nil
        Task {
            defer { isSaving = false }
            var saved = 0
            var failed = 0
            for entry in parsed {
                do {
                    _ = try await SupabaseService.shared.insertEntry(entry)
                    saved += 1
                } catch {
                    failed += 1
                    print("Failed to insert entry: \(error)")
                }
            }
            if failed == 0 {
                successMsg = "Saved \(saved) entr\(saved == 1 ? "y" : "ies") successfully!"
                inputText  = ""
                parsed     = []
            } else {
                errorMsg  = "Saved \(saved), failed \(failed). Check console."
                showError = true
            }
        }
    }
}

#Preview {
    LogEntryView()
}
