import SwiftUI

struct SettingsView: View {

    @AppStorage("anthropic_api_key") private var anthropicKey    : String = ""
    @AppStorage("retainer_amount")   private var retainerAmount  : Double = 0
    @AppStorage("your_name")         private var yourName        : String = ""
    @AppStorage("company_name")      private var companyName     : String = ""
    @AppStorage("client_email")      private var clientEmail     : String = ""

    @State  private var retainerText = ""
    @State  private var syncMessage  : String?
    @State  private var isSyncing    = false
    @State  private var showSaved    = false

    @FocusState private var focus: Field?
    private enum Field { case apiKey, retainer, yourName, companyName, clientEmail }

    private var appVersion: String {
        let v = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        let b = Bundle.main.infoDictionary?["CFBundleVersion"]            as? String ?? "1"
        return "v\(v) (\(b))"
    }

    var body: some View {
        NavigationStack {
            Form {
                // ── AI ──────────────────────────────────────────────────
                Section {
                    HStack {
                        SecureField("sk-ant-…", text: $anthropicKey)
                            .textContentType(.password)
                            .autocorrectionDisabled()
                            .focused($focus, equals: .apiKey)
                        if !anthropicKey.isEmpty {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundColor(.green)
                        }
                    }
                } header: {
                    Label("Anthropic API Key", systemImage: "key")
                } footer: {
                    Text("Used for AI-powered entry parsing. Get your key at console.anthropic.com.")
                        .font(.caption)
                }

                // ── Billing ─────────────────────────────────────────────
                Section {
                    HStack {
                        Text("$").foregroundColor(.brandMuted)
                        TextField("0", text: $retainerText)
                            .keyboardType(.decimalPad)
                            .focused($focus, equals: .retainer)
                    }
                } header: {
                    Label("Monthly Retainer", systemImage: "dollarsign.circle")
                } footer: {
                    Text("Shown on the Month summary and Invoice screens.")
                        .font(.caption)
                }

                // ── Invoice defaults ─────────────────────────────────────
                Section {
                    TextField("Your name", text: $yourName)
                        .focused($focus, equals: .yourName)
                    TextField("Client company name", text: $companyName)
                        .focused($focus, equals: .companyName)
                    TextField("Client email address", text: $clientEmail)
                        .keyboardType(.emailAddress)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                        .focused($focus, equals: .clientEmail)
                } header: {
                    Label("Invoice Defaults", systemImage: "doc.text")
                } footer: {
                    Text("Used when sending invoices from the Invoice tab.")
                        .font(.caption)
                }

                // ── Sync ─────────────────────────────────────────────────
                Section {
                    Button {
                        showSyncInfo()
                    } label: {
                        HStack {
                            if isSyncing {
                                ProgressView()
                                    .progressViewStyle(.circular)
                                    .tint(.brand)
                                    .scaleEffect(0.8)
                            } else {
                                Image(systemName: "arrow.triangle.2.circlepath")
                                    .foregroundColor(.brand)
                            }
                            Text("Sync from Cloud")
                                .foregroundColor(.brandDark)
                            Spacer()
                        }
                    }
                    .disabled(isSyncing)

                    if let msg = syncMessage {
                        HStack {
                            Image(systemName: "info.circle").foregroundColor(.brandMuted)
                            Text(msg).font(.subheadline).foregroundColor(.brandMuted)
                        }
                    }
                } header: {
                    Label("Desktop Sync", systemImage: "desktopcomputer")
                } footer: {
                    Text("Entries you add here sync to Supabase automatically. To pull them into the desktop app, run \u{201C}Sync from Cloud\u{201D} there.")
                        .font(.caption)
                }

                // ── About ─────────────────────────────────────────────────
                Section {
                    HStack {
                        Text("Version"); Spacer()
                        Text(appVersion).foregroundColor(.brandMuted)
                    }
                    HStack {
                        Text("App"); Spacer()
                        Text("K&A Time").foregroundColor(.brandMuted)
                    }
                } header: {
                    Label("About", systemImage: "info.circle")
                }
            }
            .scrollContentBackground(.hidden)
            .background(Color.brandBg.ignoresSafeArea())
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                // Save button (top-right)
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { save() }
                        .fontWeight(.semibold)
                        .foregroundColor(.brand)
                }
                // Done button above every keyboard type
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("Done") { focus = nil }
                        .foregroundColor(.brand)
                        .fontWeight(.semibold)
                }
            }
            .onAppear {
                retainerText = retainerAmount > 0 ? String(format: "%.0f", retainerAmount) : ""
            }
            .overlay(alignment: .bottom) {
                if showSaved {
                    HStack {
                        Image(systemName: "checkmark.circle.fill")
                        Text("Settings saved")
                    }
                    .padding(.horizontal, 20)
                    .padding(.vertical, 12)
                    .background(Color.brandDark)
                    .foregroundColor(.white)
                    .clipShape(Capsule())
                    .shadow(radius: 8)
                    .padding(.bottom, 32)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }
            .animation(.spring(duration: 0.3), value: showSaved)
        }
    }

    // MARK: - Actions

    private func save() {
        focus = nil
        if let amount = Double(retainerText), amount >= 0 {
            retainerAmount = amount
        } else if retainerText.isEmpty {
            retainerAmount = 0
        }
        showSaved = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { showSaved = false }
    }

    private func showSyncInfo() {
        isSyncing   = true
        syncMessage = nil
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
            isSyncing   = false
            syncMessage = "Entries you log here are live in Supabase. Open the desktop app and click \u{201C}Sync from Cloud\u{201D} to import them."
        }
    }
}

#Preview { SettingsView() }
