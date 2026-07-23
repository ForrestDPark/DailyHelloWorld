//
//  NotificationScheduler.swift
//  ShiftAlarmMobile
//
//  Mac 메뉴바 앱의 launchd 알람(register_alarm) 대신, iOS는 로컬 알림으로
//  근무 알람 + 오늘의 리마인더를 예약한다.
//

import Foundation
import UserNotifications

enum NotificationScheduler {
    /// 앞으로 며칠치를 미리 예약할지. iOS는 앱당 최대 64개의 대기 중 로컬 알림만 허용하므로,
    /// 근무 알람 + 리마인더 알림을 합쳐 64개 이내로 유지하기 위해 60일로 제한한다.
    /// 앱을 열 때마다(포그라운드 진입 시) 다시 예약해서 창을 앞으로 밀어준다.
    static let daysAhead = 60

    /// 리마인더(헬스장/엄마전화/카톡정리/아울렛쇼핑) 알림을 띄울 시각.
    static let reminderHour = 9
    static let reminderMinute = 0

    static func requestAuthorization() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { _, _ in }
    }

    static func rescheduleAll() {
        let center = UNUserNotificationCenter.current()
        center.removeAllPendingNotificationRequests()

        let settings = AppSettings.shared
        let store = ScheduleStore.shared
        let enabledReminders = settings.enabledReminderKeys()
        let calendar = ScheduleStore.koreaCalendar
        let now = Date()
        let today = calendar.startOfDay(for: now)

        var requests: [UNNotificationRequest] = []

        for offset in 0..<daysAhead {
            guard let date = calendar.date(byAdding: .day, value: offset, to: today) else { continue }

            // 자동 모드일 때만 근무표를 따라간다. 수동 모드(연차 등)는 오늘 하루만 override하므로
            // 미래 날짜 알람은 항상 근무표 기준으로 예약한다.
            if let shift = store.shift(for: date), let time = settings.alarmTime(for: shift) {
                if let request = makeShiftRequest(date: date, shift: shift, hour: time.hour, minute: time.minute, calendar: calendar, now: now, dateKey: store.dateString(date)) {
                    requests.append(request)
                }
            }

            let todaysReminders = store.reminders(for: date, enabled: enabledReminders)
            if !todaysReminders.isEmpty,
               let request = makeReminderRequest(date: date, reminders: todaysReminders, calendar: calendar, now: now, dateKey: store.dateString(date)) {
                requests.append(request)
            }
        }

        for request in requests.prefix(64) {
            center.add(request)
        }
    }

    private static func makeShiftRequest(date: Date, shift: ShiftType, hour: Int, minute: Int, calendar: Calendar, now: Date, dateKey: String) -> UNNotificationRequest? {
        var comps = calendar.dateComponents([.year, .month, .day], from: date)
        comps.hour = hour
        comps.minute = minute
        guard let fireDate = calendar.date(from: comps), fireDate > now else { return nil }

        let content = UNMutableNotificationContent()
        content.title = "⏰ 교대근무 알람"
        content.body = String(format: "%@ 근무 — %02d:%02d", shift.rawValue, hour, minute)
        content.sound = .default

        let trigger = UNCalendarNotificationTrigger(dateMatching: comps, repeats: false)
        return UNNotificationRequest(identifier: "shift-\(dateKey)", content: content, trigger: trigger)
    }

    private static func makeReminderRequest(date: Date, reminders: [ReminderKey], calendar: Calendar, now: Date, dateKey: String) -> UNNotificationRequest? {
        var comps = calendar.dateComponents([.year, .month, .day], from: date)
        comps.hour = reminderHour
        comps.minute = reminderMinute
        guard let fireDate = calendar.date(from: comps), fireDate > now else { return nil }

        let content = UNMutableNotificationContent()
        content.title = "🔔 오늘의 리마인더"
        content.body = reminders.map { $0.label }.joined(separator: "\n")
        content.sound = .default

        let trigger = UNCalendarNotificationTrigger(dateMatching: comps, repeats: false)
        return UNNotificationRequest(identifier: "reminder-\(dateKey)", content: content, trigger: trigger)
    }
}
