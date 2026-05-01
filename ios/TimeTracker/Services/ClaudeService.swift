import Foundation

// MARK: - Errors

enum ClaudeError: LocalizedError {
    case missingAPIKey
    case httpError(Int, String)
    case noContent
    case decodingError(String)

    var errorDescription: String? {
        switch self {
        case .missingAPIKey:           return "Anthropic API key not set. Add it in Settings."
        case .httpError(let c, let m): return "Claude API error \(c): \(m)"
        case .noContent:               return "Claude returned an empty response."
        case .decodingError(let m):    return "Failed to parse Claude response: \(m)"
        }
    }
}

// MARK: - ClaudeService

final class ClaudeService {

    static let shared = ClaudeService()
    private init() {}

    private let endpoint = URL(string: "https://api.anthropic.com/v1/messages")!
    private let model    = "claude-haiku-4-5-20251001"
    private let maxTokens = 1024

    private let categories = [
        "Administrative", "Bookkeeping", "Payroll", "Tax Preparation",
        "Financial Reporting", "Client Communication", "Research", "Training",
        "SEO Audit", "Web Development", "AI Integration", "General"
    ]

    // MARK: - Public API

    func parseEntries(text: String) async throws -> [ParsedEntry] {
        guard let apiKey = UserDefaults.standard.string(forKey: "anthropic_api_key"),
              !apiKey.isEmpty else {
            throw ClaudeError.missingAPIKey
        }

        let today = Self.todayString()
        let categoryList = categories.joined(separator: ", ")

        let systemPrompt = """
        You are a time-tracking assistant for an accounting professional. \
        Parse the user's natural language input into structured time entries.

        Today's date is \(today). Use this as context when interpreting relative dates \
        like "today", "yesterday", "this morning", etc.

        Always return a JSON array of objects with these exact keys:
        - date: string in YYYY-MM-DD format
        - hours: number (decimal, e.g. 1.5 for 1 hour 30 min)
        - description: string (concise but descriptive)
        - category: string (must be one of: \(categoryList))
        - start_time: string or null (HH:MM 24h format if mentioned)
        - end_time: string or null (HH:MM 24h format if mentioned)

        Return ONLY the JSON array, no markdown fences, no explanation.
        """

        let userMessage = text

        let payload: [String: Any] = [
            "model":      model,
            "max_tokens": maxTokens,
            "system":     systemPrompt,
            "messages":   [["role": "user", "content": userMessage]],
        ]

        let body = try JSONSerialization.data(withJSONObject: payload)

        var req = URLRequest(url: endpoint)
        req.httpMethod = "POST"
        req.setValue(apiKey,             forHTTPHeaderField: "x-api-key")
        req.setValue("2023-06-01",       forHTTPHeaderField: "anthropic-version")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.httpBody = body
        req.timeoutInterval = 30

        let (data, response) = try await URLSession.shared.data(for: req)

        guard let http = response as? HTTPURLResponse else {
            throw ClaudeError.httpError(0, "No HTTP response")
        }
        guard (200..<300).contains(http.statusCode) else {
            let msg = String(data: data, encoding: .utf8) ?? "Unknown"
            throw ClaudeError.httpError(http.statusCode, msg)
        }

        // Extract text content from Anthropic response envelope
        guard
            let envelope = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let content  = envelope["content"] as? [[String: Any]],
            let first    = content.first,
            let rawText  = first["text"] as? String
        else {
            throw ClaudeError.noContent
        }

        return try decode(rawText)
    }

    // MARK: - Private helpers

    private func decode(_ rawText: String) throws -> [ParsedEntry] {
        // Strip markdown code fences if present
        var cleaned = rawText.trimmingCharacters(in: .whitespacesAndNewlines)
        if cleaned.hasPrefix("```") {
            cleaned = cleaned
                .replacingOccurrences(of: #"```[a-z]*\n?"#, with: "", options: .regularExpression)
                .replacingOccurrences(of: "```", with: "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
        }

        guard let jsonData = cleaned.data(using: .utf8) else {
            throw ClaudeError.decodingError("Could not encode response as UTF-8")
        }
        do {
            return try JSONDecoder().decode([ParsedEntry].self, from: jsonData)
        } catch {
            throw ClaudeError.decodingError(error.localizedDescription)
        }
    }

    private static func todayString() -> String {
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd"
        return fmt.string(from: Date())
    }
}
