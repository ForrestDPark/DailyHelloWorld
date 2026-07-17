//
//  SettingsView.swift
//  ShiftAlarmMobile
//

import SwiftUI

struct SettingsView: View {
    @ObservedObject private var settings = AppSettings.shared
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationView {
            Form {
                Section("근무별 알람 시간") {
                    timeRow(title: "Day", hour: $settings.dayAlarmHour, minute: $settings.dayAlarmMinute)
                    timeRow(title: "Swing", hour: $settings.swingAlarmHour, minute: $settings.swingAlarmMinute)
                    timeRow(title: "GY", hour: $settings.gyAlarmHour, minute: $settings.gyAlarmMinute)
                }

                Section {
                    ForEach(ReminderKey.allCases, id: \.self) { key in
                        Toggle(key.label, isOn: Binding(
                            get: { settings.remindersEnabled[key] ?? true },
                            set: { settings.remindersEnabled[key] = $0 }
                        ))
                    }
                } header: {
                    Text("리마인더")
                } footer: {
                    Text("헬스장은 주 2회(휴무 시작일 + 이틀 뒤), 엄마 전화는 휴무 시작일, 카톡 정리는 휴무 마지막날, 아울렛 쇼핑은 한 달에 한 번(그 달의 첫 번째 휴무 시작일)에 알림이 뜹니다.")
                }
            }
            .navigationTitle("설정")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("완료") {
                        NotificationScheduler.rescheduleAll()
                        dismiss()
                    }
                }
            }
        }
    }

    private func timeRow(title: String, hour: Binding<Int>, minute: Binding<Int>) -> some View {
        HStack {
            Text(title)
            Spacer()
            Picker("", selection: hour) {
                ForEach(0..<24, id: \.self) { h in
                    Text(String(format: "%02d", h)).tag(h)
                }
            }
            .pickerStyle(.menu)
            Text(":")
            Picker("", selection: minute) {
                ForEach(0..<60, id: \.self) { m in
                    Text(String(format: "%02d", m)).tag(m)
                }
            }
            .pickerStyle(.menu)
        }
    }
}

#Preview {
    SettingsView()
}
