import SwiftUI

struct InvoiceView: View {

    @AppStorage("retainer_amount") private var retainerAmount: Double = 0
    @AppStorage("your_name")       private var yourName      : String = ""
    @AppStorage("company_name")    private var companyName   : String = ""
    @AppStorage("client_email")    private var clientEmail   : String = ""

    @State private var displayDate   = Date()
    @State private var hoursInPeriod : Double = 0
    @State private var totalHours    : Double = 0
    @State private var isLoading     = false
    @State private var showCopied    = false

    // MARK: - Computed

    private var cal: Calendar { Calendar(identifier: .gregorian) }
    private var year : Int { cal.component(.year,  from: displayDate) }
    private var month: Int { cal.component(.month, from: displayDate) }

    private var periodLabel: String {
        let fmt = DateFormatter(); fmt.dateFormat = "MMMM yyyy"
        return fmt.string(from: displayDate)
    }

    private var invoiceNumber: String { String(format: "INV-%04d%02d", year, month) }

    private var invoiceDateStr: String {
        let fmt = DateFormatter(); fmt.dateStyle = .long; fmt.timeStyle = .none
        return fmt.string(from: Date())
    }

    private var emailBody: String {
        let name    = yourName.isEmpty    ? "Consultant"  : yourName
        let company = companyName.isEmpty ? "Client"      : companyName
        return """
Dear \(company),

Please find attached invoice \(invoiceNumber) covering all AI Integration & Web Development Services \u{2014} Monthly Retainer for the month of \(periodLabel).

Invoice Date:    \(invoiceDateStr)
Service Period:  \(periodLabel) (all work this month)
Amount Due:      $\(String(format: "%.2f", retainerAmount))

Hours worked as of \(invoiceDateStr) (informational):
  \(String(format: "%.1f", hoursInPeriod)) hrs in \(periodLabel)   |   \(String(format: "%.1f", totalHours)) hrs total on record

Please don\u{2019}t hesitate to reach out with any questions.

Best regards,
\(name)
"""
    }

    private var emailSubject: String {
        "Invoice \(invoiceNumber) \u{2014} AI Integration & Web Development Services \u{2014} \(periodLabel)"
    }

    // MARK: - Body

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    monthNavigator
                    invoiceCard
                    actionButtons
                }
                .padding()
            }
            .background(Color.brandBg.ignoresSafeArea())
            .navigationTitle("Invoice")
            .navigationBarTitleDisplayMode(.large)
            .onAppear { loadHours() }
            .onChange(of: displayDate) { _ in loadHours() }
            .overlay(alignment: .bottom) {
                if showCopied {
                    HStack {
                        Image(systemName: "doc.on.doc.fill")
                        Text("Body copied to clipboard")
                    }
                    .padding(.horizontal, 20).padding(.vertical, 12)
                    .background(Color.brandDark).foregroundColor(.white)
                    .clipShape(Capsule()).shadow(radius: 8).padding(.bottom, 32)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }
            .animation(.spring(duration: 0.3), value: showCopied)
        }
    }

    // MARK: - Subviews

    private var monthNavigator: some View {
        HStack {
            Button { shiftMonth(-1) } label: {
                Image(systemName: "chevron.left")
                    .font(.title2).foregroundColor(.brand)
            }
            Spacer()
            Text(periodLabel)
                .font(.title2.weight(.semibold))
                .foregroundColor(.brandDark)
            Spacer()
            Button { shiftMonth(1) } label: {
                Image(systemName: "chevron.right")
                    .font(.title2).foregroundColor(.brand)
            }
        }
        .padding(.horizontal, 8)
    }

    private var invoiceCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text(invoiceNumber).font(.headline).foregroundColor(.brand)
                Spacer()
                Text(invoiceDateStr).font(.subheadline).foregroundColor(.brandMuted)
            }
            Divider()
            infoRow("To",       companyName.isEmpty ? "—" : companyName)
            infoRow("Period",   periodLabel)
            infoRow("Service",  "Monthly Retainer")
            if isLoading {
                HStack { Spacer(); ProgressView().tint(.brand); Spacer() }
            } else {
                infoRow("Hours (info)", String(format: "%.1f hrs this month  |  %.1f hrs total",
                                               hoursInPeriod, totalHours))
            }
            Divider()
            HStack {
                Text("Amount Due").font(.headline).foregroundColor(.brandDark)
                Spacer()
                Text(String(format: "$%.2f", retainerAmount))
                    .font(.title3.weight(.bold)).foregroundColor(.brand)
            }
        }
        .padding(20)
        .background(Color.white)
        .cornerRadius(14)
        .shadow(color: .black.opacity(0.06), radius: 8, y: 3)
    }

    private var actionButtons: some View {
        VStack(spacing: 12) {
            // Send via Mail app
            Button {
                openMailApp()
            } label: {
                Label("Send Invoice Email", systemImage: "envelope.fill")
                    .fontWeight(.semibold)
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(clientEmail.isEmpty ? Color.gray : Color.brand)
                    .foregroundColor(.white)
                    .cornerRadius(12)
            }
            .disabled(clientEmail.isEmpty)

            if clientEmail.isEmpty {
                Text("Add client email in Settings to enable sending.")
                    .font(.caption)
                    .foregroundColor(.brandMuted)
                    .multilineTextAlignment(.center)
            }

            // Copy body to clipboard
            Button {
                UIPasteboard.general.string = emailBody
                showCopied = true
                DispatchQueue.main.asyncAfter(deadline: .now() + 2) { showCopied = false }
            } label: {
                Label("Copy Email Body", systemImage: "doc.on.doc")
                    .fontWeight(.medium)
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.white)
                    .foregroundColor(.brandDark)
                    .cornerRadius(12)
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(Color.brandMuted.opacity(0.3), lineWidth: 1)
                    )
            }
        }
    }

    @ViewBuilder
    private func infoRow(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top) {
            Text(label).foregroundColor(.brandMuted)
            Spacer()
            Text(value).foregroundColor(.brandDark).multilineTextAlignment(.trailing)
        }
        .font(.subheadline)
    }

    // MARK: - Actions

    private func openMailApp() {
        var comps = URLComponents(string: "mailto:\(clientEmail)")!
        comps.queryItems = [
            URLQueryItem(name: "subject", value: emailSubject),
            URLQueryItem(name: "body",    value: emailBody),
        ]
        if let url = comps.url {
            UIApplication.shared.open(url)
        }
    }

    private func loadHours() {
        isLoading = true
        Task {
            do {
                let monthEntries = try await SupabaseService.shared.fetchEntriesForMonth(year: year, month: month)
                let mHours = monthEntries.reduce(0.0) { $0 + $1.hours }

                let allEntries = try await SupabaseService.shared.fetchEntries(
                    from: "2020-01-01",
                    to: String(format: "%04d-%02d-31", year, month))
                let tHours = allEntries.reduce(0.0) { $0 + $1.hours }

                await MainActor.run {
                    hoursInPeriod = mHours
                    totalHours    = tHours
                    isLoading     = false
                }
            } catch {
                await MainActor.run { isLoading = false }
            }
        }
    }

    private func shiftMonth(_ delta: Int) {
        displayDate = cal.date(byAdding: .month, value: delta, to: displayDate) ?? displayDate
    }
}

#Preview { InvoiceView() }
