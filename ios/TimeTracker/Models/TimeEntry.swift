import Foundation

struct TimeEntry: Identifiable, Codable, Equatable {
    var id: String
    var localId: Int?
    var date: String        // YYYY-MM-DD
    var hours: Double
    var description: String
    var category: String
    var startTime: String?
    var endTime: String?
    var createdAt: String?
    var updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case localId    = "local_id"
        case date, hours, description, category
        case startTime  = "start_time"
        case endTime    = "end_time"
        case createdAt  = "created_at"
        case updatedAt  = "updated_at"
    }
}

struct ParsedEntry: Codable {
    var date: String
    var hours: Double
    var description: String
    var category: String
    var startTime: String?
    var endTime: String?

    enum CodingKeys: String, CodingKey {
        case date, hours, description, category
        case startTime = "start_time"
        case endTime   = "end_time"
    }
}
