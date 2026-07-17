//
//  ContentView.swift
//  ShiftAlarmMobile
//

import SwiftUI

struct ContentView: View {
    @ObservedObject private var settings = AppSettings.shared
    @State private var showSettings = false

    private let store = ScheduleStore.shared

    private var today: Date { Date() }

    private var todayShift: ShiftType? {
        settings.autoMode ? store.shift(for: today) : settings.manualShift
    }

    private var todayReminders: [ReminderKey] {
        store.reminders(for: today, enabled: settings.enabledReminderKeys())
    }

    var body: some View {
        NavigationView {
            List {
                Section("오늘") {
                    HStack {
                        Text("근무")
                        Spacer()
                        Text(todayShift?.rawValue ?? "미설정")
                            .foregroundStyle(.secondary)
                    }
                    if let shift = todayShift, let time = settings.alarmTime(for: shift) {
                        HStack {
                            Text("알람")
                            Spacer()
                            Text(String(format: "%02d:%02d", time.hour, time.minute))
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                Section("오늘의 리마인더") {
                    if todayReminders.isEmpty {
                        Text("오늘 예정된 리마인더 없음")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(todayReminders, id: \.self) { reminder in
                            Text(reminder.label)
                        }
                    }
                }

                Section {
                    Toggle("근무표 자동 적용", isOn: $settings.autoMode)
                    if !settings.autoMode {
                        Picker("수동 근무 선택", selection: Binding(
                            get: { settings.manualShift ?? .off },
                            set: { settings.manualShift = $0 }
                        )) {
                            ForEach(ShiftType.allCases, id: \.self) { shift in
                                Text(shift.rawValue).tag(shift)
                            }
                        }
                    }
                } footer: {
                    Text("자동 모드면 근무표(d_team_schedule_2026.json) 기준으로 알람이 예약됩니다. 연차 등으로 오늘만 다르게 지정하려면 자동 적용을 끄고 수동으로 선택하세요.")
                }
            }
            .navigationTitle("교대근무 알람")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        showSettings = true
                    } label: {
                        Image(systemName: "gearshape")
                    }
                }
            }
            .sheet(isPresented: $showSettings) {
                SettingsView()
            }
            .onChange(of: settings.autoMode) { _, _ in NotificationScheduler.rescheduleAll() }
            .onChange(of: settings.manualShift) { _, _ in NotificationScheduler.rescheduleAll() }
        }
    }
}

#Preview {
    ContentView()
}
