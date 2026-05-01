import Foundation

// MARK: - Errors

enum SupabaseError: LocalizedError {
    case invalidURL
    case httpError(Int, String)
    case decodingError(Error)

    var errorDescription: String? {
        switch self {
        case .invalidURL:           return "Invalid Supabase URL"
        case .httpError(let c, let m): return "HTTP \(c): \(m)"
        case .decodingError(let e): return "Decoding error: \(e.localizedDescription)"
        }
    }
}

// MARK: - SupabaseService

final class SupabaseService {

    static let shared = SupabaseService()

    private let baseURL: String
    private let apiKey: String
    private let session: URLSession

    private init() {
        baseURL = Config.supabaseURL.trimmingCharacters(in: .init(charactersIn: "/"))
        apiKey  = Config.supabaseKey
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest  = 15
        config.timeoutIntervalForResource = 30
        session = URLSession(configuration: config)
    }

    // MARK: - Core request helper

    private func request(_ method: String, path: String, body: Data? = nil) async throws -> Data {
        guard let url = URL(string: "\(baseURL)/rest/v1/\(path)") else {
            throw SupabaseError.invalidURL
        }
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue(apiKey,          forHTTPHeaderField: "apikey")
        req.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            req.httpBody = body
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (data, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse else {
            throw SupabaseError.httpError(0, "No HTTP response")
        }
        guard (200..<300).contains(http.statusCode) else {
            let msg = String(data: data, encoding: .utf8) ?? "Unknown error"
            throw SupabaseError.httpError(http.statusCode, msg)
        }
        return data
    }

    // MARK: - Time Entries

    /// Fetch entries between two dates (inclusive), ordered by date ascending.
    func fetchEntries(from startDate: String, to endDate: String) async throws -> [TimeEntry] {
        let path = "time_entries?date=gte.\(startDate)&date=lte.\(endDate)&order=date.asc,created_at.asc"
        let data = try await request("GET", path: path)
        do {
            return try JSONDecoder().decode([TimeEntry].self, from: data)
        } catch {
            throw SupabaseError.decodingError(error)
        }
    }

    /// Fetch all entries for a calendar month.
    func fetchEntriesForMonth(year: Int, month: Int) async throws -> [TimeEntry] {
        let start = String(format: "%04d-%02d-01", year, month)
        let end   = lastDayOfMonth(year: year, month: month)
        return try await fetchEntries(from: start, to: end)
    }

    /// Insert a new entry; returns the created TimeEntry with its Supabase UUID.
    func insertEntry(_ entry: ParsedEntry) async throws -> TimeEntry {
        let now = ISO8601DateFormatter().string(from: Date())
        var payload: [String: Any] = [
            "date":        entry.date,
            "hours":       entry.hours,
            "description": entry.description,
            "category":    entry.category,
            "created_at":  now,
            "updated_at":  now,
        ]
        if let st = entry.startTime { payload["start_time"] = st }
        if let et = entry.endTime   { payload["end_time"]   = et }

        let body = try JSONSerialization.data(withJSONObject: payload)
        var req = URLRequest(url: URL(string: "\(baseURL)/rest/v1/time_entries")!)
        req.httpMethod = "POST"
        req.setValue(apiKey,              forHTTPHeaderField: "apikey")
        req.setValue("Bearer \(apiKey)",  forHTTPHeaderField: "Authorization")
        req.setValue("application/json",  forHTTPHeaderField: "Content-Type")
        req.setValue("application/json",  forHTTPHeaderField: "Accept")
        req.setValue("return=representation", forHTTPHeaderField: "Prefer")
        req.httpBody = body

        let (data, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse else {
            throw SupabaseError.httpError(0, "No HTTP response")
        }
        guard (200..<300).contains(http.statusCode) else {
            let msg = String(data: data, encoding: .utf8) ?? "Unknown"
            throw SupabaseError.httpError(http.statusCode, msg)
        }
        do {
            let entries = try JSONDecoder().decode([TimeEntry].self, from: data)
            guard let created = entries.first else {
                throw SupabaseError.httpError(200, "Empty response after insert")
            }
            return created
        } catch {
            throw SupabaseError.decodingError(error)
        }
    }

    /// Delete an entry by its Supabase UUID.
    func deleteEntry(id: String) async throws {
        _ = try await request("DELETE", path: "time_entries?id=eq.\(id)")
    }

    /// Sum hours for a calendar month.
    func totalHoursForMonth(year: Int, month: Int) async throws -> Double {
        let entries = try await fetchEntriesForMonth(year: year, month: month)
        return entries.reduce(0) { $0 + $1.hours }
    }

    // MARK: - Helpers

    private func lastDayOfMonth(year: Int, month: Int) -> String {
        var comps        = DateComponents()
        comps.year       = year
        comps.month      = month + 1
        comps.day        = 0   // last day of previous month
        let cal          = Calendar(identifier: .gregorian)
        let date         = cal.date(from: comps) ?? Date()
        let day          = cal.component(.day, from: date)
        return String(format: "%04d-%02d-%02d", year, month, day)
    }
}
