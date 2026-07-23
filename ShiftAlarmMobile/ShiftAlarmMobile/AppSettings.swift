//
//  AppSettings.swift
//  ShiftAlarmMobile
//

import Foundation
import Combine

/// 메뉴바 앱의 CONFIG_FILE(~/.shift_alarm_config.json)에 해당하는
/// 사용자 설정(알람 시간 / 리마인더 on-off / 자동-수동 모드)을 UserDefaults에 저장.
final class AppSettings: ObservableObject {
    static let shared = AppSettings()

    @Published var dayAlarmHour: Int { didSet { save() } }
    @Published var dayAlarmMinute: Int { didSet { save() } }
    @Published var swingAlarmHour: Int { didSet { save() } }
    @Published var swingAlarmMinute: Int { didSet { save() } }
    @Published var gyAlarmHour: Int { didSet { save() } }
    @Published var gyAlarmMinute: Int { didSet { save() } }

    @Published var remindersEnabled: [ReminderKey: Bool] { didSet { save() } }

    /// true면 근무표를 그대로 따라간다. false면 manualShift를 오늘 근무로 사용 (연차 등 수동 지정).
    @Published var autoMode: Bool { didSet { save() } }
    @Published var manualShift: ShiftType? { didSet { save() } }

    private let defaults = UserDefaults.standard

    private enum Key {
        static let dayHour = "dayAlarmHour"
        static let dayMinute = "dayAlarmMinute"
        static let swingHour = "swingAlarmHour"
        static let swingMinute = "swingAlarmMinute"
        static let gyHour = "gyAlarmHour"
        static let gyMinute = "gyAlarmMinute"
        static let remindersEnabled = "remindersEnabled"
        static let autoMode = "autoMode"
        static let manualShift = "manualShift"
    }

    private init() {
        let d = UserDefaults.standard
        dayAlarmHour = d.object(forKey: Key.dayHour) as? Int ?? 2
        dayAlarmMinute = d.object(forKey: Key.dayMinute) as? Int ?? 55
        swingAlarmHour = d.object(forKey: Key.swingHour) as? Int ?? 8
        swingAlarmMinute = d.object(forKey: Key.swingMinute) as? Int ?? 30
        gyAlarmHour = d.object(forKey: Key.gyHour) as? Int ?? 16
        gyAlarmMinute = d.object(forKey: Key.gyMinute) as? Int ?? 30
        autoMode = d.object(forKey: Key.autoMode) as? Bool ?? true

        if let raw = d.string(forKey: Key.manualShift) {
            manualShift = ShiftType(rawValue: raw)
        } else {
            manualShift = nil
        }

        if let saved = d.dictionary(forKey: Key.remindersEnabled) as? [String: Bool] {
            var merged: [ReminderKey: Bool] = [:]
            for key in ReminderKey.allCases {
                merged[key] = saved[key.rawValue] ?? true
            }
            remindersEnabled = merged
        } else {
            var initial: [ReminderKey: Bool] = [:]
            for key in ReminderKey.allCases { initial[key] = true }
            remindersEnabled = initial
        }
    }

    private func save() {
        defaults.set(dayAlarmHour, forKey: Key.dayHour)
        defaults.set(dayAlarmMinute, forKey: Key.dayMinute)
        defaults.set(swingAlarmHour, forKey: Key.swingHour)
        defaults.set(swingAlarmMinute, forKey: Key.swingMinute)
        defaults.set(gyAlarmHour, forKey: Key.gyHour)
        defaults.set(gyAlarmMinute, forKey: Key.gyMinute)
        defaults.set(autoMode, forKey: Key.autoMode)
        defaults.set(manualShift?.rawValue, forKey: Key.manualShift)

        let dict = Dictionary(uniqueKeysWithValues: remindersEnabled.map { ($0.key.rawValue, $0.value) })
        defaults.set(dict, forKey: Key.remindersEnabled)
    }

    func alarmTime(for shift: ShiftType) -> (hour: Int, minute: Int)? {
        switch shift {
        case .day: return (dayAlarmHour, dayAlarmMinute)
        case .swing: return (swingAlarmHour, swingAlarmMinute)
        case .gy: return (gyAlarmHour, gyAlarmMinute)
        case .off: return nil
        }
    }

    func enabledReminderKeys() -> Set<ReminderKey> {
        Set(remindersEnabled.filter { $0.value }.map { $0.key })
    }
}
