//
//  ScheduleStore.swift
//  ShiftAlarmMobile
//
//  shift_alarm.py의 근무표/리마인더 로직을 그대로 포팅.
//

import Foundation

enum ShiftType: String, Codable, CaseIterable {
    case day = "Day"
    case swing = "Swing"
    case gy = "GY"
    case off = "휴무"
}

enum ReminderKey: String, CaseIterable, Codable {
    case gym
    case callMom
    case kakaoCleanup
    case outletShopping

    var label: String {
        switch self {
        case .gym: return "🏋️ 헬스장 가는 날"
        case .callMom: return "📞 엄마한테 전화하는 날"
        case .kakaoCleanup: return "🧹 카톡 정리하는 날"
        case .outletShopping: return "🛍️ 아울렛 쇼핑하는 날"
        }
    }
}

private let codeToShift: [String: ShiftType] = [
    "D": .day, "S": .swing, "G": .gy, "휴": .off
]

/// 근무표(JSON)를 읽어서 날짜별 근무/리마인더를 계산.
/// 근무표 코드 매핑과 "휴무 블록" 기준 리마인더 판단은 shift_alarm.py의
/// get_shift_for_date / _is_off_block_start / _is_first_off_block_start_of_month와 동일한 규칙을 따른다.
final class ScheduleStore {
    static let shared = ScheduleStore()

    private(set) var schedule: [String: String] = [:]  // "yyyy-MM-dd" -> "D"/"S"/"G"/"휴"

    static let koreaCalendar: Calendar = {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "Asia/Seoul") ?? .current
        return cal
    }()

    private let formatter: DateFormatter = {
        let f = DateFormatter()
        f.calendar = koreaCalendar
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = koreaCalendar.timeZone
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    private init() {
        load()
    }

    /// 근무표 JSON을 다시 읽는다 (근무표 파일 교체 후 갱신용).
    func load() {
        guard let url = Bundle.main.url(forResource: "d_team_schedule_2026", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let dict = try? JSONDecoder().decode([String: String].self, from: data) else {
            schedule = [:]
            return
        }
        schedule = dict
    }

    func dateString(_ date: Date) -> String {
        formatter.string(from: date)
    }

    func shift(for date: Date) -> ShiftType? {
        guard let code = schedule[dateString(date)] else { return nil }
        return codeToShift[code]
    }

    private func isOffBlockStart(_ date: Date) -> Bool {
        guard shift(for: date) == .off else { return false }
        guard let prev = Self.koreaCalendar.date(byAdding: .day, value: -1, to: date) else { return false }
        return shift(for: prev) != .off
    }

    private func isFirstOffBlockStartOfMonth(_ date: Date) -> Bool {
        guard isOffBlockStart(date) else { return false }
        let comps = Self.koreaCalendar.dateComponents([.year, .month], from: date)
        guard let monthStart = Self.koreaCalendar.date(from: comps) else { return false }

        var cursor = monthStart
        while cursor < date {
            if isOffBlockStart(cursor) { return false }
            guard let next = Self.koreaCalendar.date(byAdding: .day, value: 1, to: cursor) else { break }
            cursor = next
        }
        return true
    }

    /// 오늘(date) 기준으로 해당하는 리마인더 목록을 반환.
    func reminders(for date: Date, enabled: Set<ReminderKey>) -> [ReminderKey] {
        let cal = Self.koreaCalendar
        var result: [ReminderKey] = []

        if enabled.contains(.gym) {
            let twoDaysBefore = cal.date(byAdding: .day, value: -2, to: date) ?? date
            if isOffBlockStart(date) || isOffBlockStart(twoDaysBefore) {
                result.append(.gym)
            }
        }

        if shift(for: date) == .off {
            let yesterday = cal.date(byAdding: .day, value: -1, to: date) ?? date
            let tomorrow = cal.date(byAdding: .day, value: 1, to: date) ?? date
            let isBlockStart = shift(for: yesterday) != .off
            let isBlockEnd = shift(for: tomorrow) != .off
            if isBlockStart && enabled.contains(.callMom) { result.append(.callMom) }
            if isBlockEnd && enabled.contains(.kakaoCleanup) { result.append(.kakaoCleanup) }
        }

        if enabled.contains(.outletShopping) && isFirstOffBlockStartOfMonth(date) {
            result.append(.outletShopping)
        }

        return result
    }
}
