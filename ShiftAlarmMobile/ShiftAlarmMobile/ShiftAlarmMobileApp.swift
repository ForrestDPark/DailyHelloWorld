//
//  ShiftAlarmMobileApp.swift
//  ShiftAlarmMobile
//

import SwiftUI

@main
struct ShiftAlarmMobileApp: App {
    @Environment(\.scenePhase) private var scenePhase

    init() {
        NotificationScheduler.requestAuthorization()
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .onChange(of: scenePhase) { _, phase in
            // 앱이 포그라운드로 돌아올 때마다 알림 예약 창(앞으로 60일)을 다시 밀어준다.
            if phase == .active {
                NotificationScheduler.rescheduleAll()
            }
        }
    }
}
