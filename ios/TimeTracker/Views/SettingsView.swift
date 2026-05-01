import SwiftUI

struct SettingsView: View {

    @AppStorage("anthropic_api_key") private var anthropicKey  : String = ""
    @AppStorage("retainer_amount")   private var retainerAmount: Double = 0

    @State private var retainerText   = ""
    @State private var syncMessage    : String?
    @State private var isSyncing      = false
    @State private var showSaved      = false

    private var appVersion: String {
        let v = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        let b = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "1"
        return "v\(v) (\(b))"
    }

    var body: some View {
        NavigationStack {
            Form {
                // ── AI ──
                Section {
                    HStack {
                        SecureField("sk-ant-…", text: $anthropicKey)
                            .textContentType(.password)
                            .autocorrectionDisabled()
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

                // ── Billing ──
                Section {
                    HStack {
                        Text("$")
                            .foregroundColor(.brandMuted)
                        TextField("0", text: $retainerText)
                            .keyboardType(.decimalPad)
                    }
                } header: {
                    Label("Monthly Retainer", systemImage: "dollarsign.circle")
                } footer: {
                    Text("Shown on the Month summary screen.")
                        .font(.caption)
                }

                // ── Sync ──
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
                            Image(systemName: "info.circle")
                                .foregroundColor(.brandMuted)
                            Text(msg)
                                .font(.subheadline)
                                .foregroundColor(.brandMuted)
                        }
                    }
                } header: {
                    Label("Desktop Sync", systemImage: "desktopcomputer")
                } footer: {
                    Text("Entries you add here sync to Supabase automatically. To pull them into the desktop app, run "Sync from Cloud" there.")
                        .font(.caption)
                }

                // ── App info ──
                Section {
                    HStack {
                        Text("Version")
                        Spacer()
                        Text(appVersion)
                            .foregroundColor(.brandMuted)
                    }
                    HStack {
                        Text("App")
                        Spacer()
                        Text("PB&J Time Tracker")
                            .foregroundColor(.brandMuted)
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
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { save() }
                        .fontWeight(.semibold)
                        .foregroundColor(.brand)
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
        if let amount = Double(retainerText), amount >= 0 {
            retainerAmount = amount
        } else if retainerText.isEmpty {
            retainerAmount = 0
        }
        // anthropicKey is @AppStorage — already saved on every keystroke
        showSaved = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            showSaved = false
        }
    }

    private func showSyncInfo() {
        isSyncing   = true
        syncMessage = nil
        // The real sync happens on the desktop; this just shows guidance.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
            isSyncing   = false
            syncMessage = "Entries you log here are live in Supabase. Open the desktop app and click "Sync from Cloud" to import them."
        }
    }
}

#Preview {
    SettingsView()
}
