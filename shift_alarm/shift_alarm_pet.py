"""Shift Alarm의 상태를 보여주는 가벼운 AppKit 플로팅 Pet."""

import os
import objc
from AppKit import (
    NSAnimationContext, NSBackingStoreBuffered, NSBezierPath, NSColor, NSFont,
    NSImage, NSMakeRect, NSFloatingWindowLevel, NSPanel, NSScreen, NSString, NSView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowStyleMaskBorderless, NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSMakePoint, NSTimer

PET_WIDTH = 210
PET_HEIGHT = 120

# ★ 2026-08-29: "펫그림을 누를때만 클릭이 되면 좋겠어, 글자들은 말풍선으로"
# 요청 — 기존엔 이미지+텍스트를 감싸는 반투명 사각형 하나가 클릭 영역 전체
# 였는데, 이제 이미지 자체와 말풍선을 분리해서 그린다. 이미지는 아래쪽에
# 배경 없이 그대로, 상태 텍스트는 그 위 말풍선(꼬리 달린 둥근 사각형) 안에
# 표시한다. IMAGE_RECT는 렌더링과 클릭 판정(mouseUp_) 양쪽이 공유하는
# 좌표라 여기 하나로 고정해둔다.
IMAGE_RECT = NSMakeRect(6, 4, 60, 60)
BUBBLE_RECT = NSMakeRect(2, 68, 206, 48)
BUBBLE_TAIL_POINTS = (NSMakePoint(26, 68), NSMakePoint(50, 68), NSMakePoint(36, 54))
DEFAULT_CARDS = (("Shift Alarm", ""),)
# ★ 2026-08-29: "저장용량이나 리마인더는 말풍선에 안 보인다, 30초 단위로
# 바꿔가며 표기해줘" 요청 — 말풍선 한 칸엔 두 줄만 들어가서 근무·저장공간·
# 리마인더·AI 사용량을 동시에 못 보여준다. shift_alarm이 (제목, 내용)
# 카드 여러 장을 넘겨주면 이 간격으로 자동으로 다음 카드로 넘어간다.
CARD_ROTATE_SECONDS = 30.0


def _point_in_rect(point, rect):
    return (
        rect.origin.x <= point.x <= rect.origin.x + rect.size.width
        and rect.origin.y <= point.y <= rect.origin.y + rect.size.height
    )


def clamp_pet_position(x, y, visible_frames, width=PET_WIDTH, height=PET_HEIGHT):
    """Pet 전체가 들어가는 화면 중 원래 좌표와 가장 가까운 위치를 반환한다.

    모니터가 분리되거나 해상도/배율이 바뀐 뒤 저장 좌표가 화면 밖에 남는 경우를
    처리하기 위한 순수 함수다. visible_frames는 (x, y, width, height) 튜플 목록이다.
    """
    if not visible_frames:
        return float(x), float(y)
    candidates = []
    for frame_x, frame_y, frame_width, frame_height in visible_frames:
        min_x, min_y = float(frame_x), float(frame_y)
        max_x = max(min_x, min_x + float(frame_width) - width)
        max_y = max(min_y, min_y + float(frame_height) - height)
        candidate_x = min(max(float(x), min_x), max_x)
        candidate_y = min(max(float(y), min_y), max_y)
        distance = (candidate_x - float(x)) ** 2 + (candidate_y - float(y)) ** 2
        candidates.append((distance, candidate_x, candidate_y))
    _, clamped_x, clamped_y = min(candidates, key=lambda item: item[0])
    return clamped_x, clamped_y


class ShiftAlarmPetView(NSView):
    owner = objc.ivar()
    cards = objc.ivar()
    card_index = objc.ivar()
    image = objc.ivar()
    dragged = objc.ivar()

    def initWithFrame_owner_image_(self, frame, owner, image):
        self = objc.super(ShiftAlarmPetView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.owner, self.image = owner, image
        self.cards, self.card_index, self.dragged = list(DEFAULT_CARDS), 0, False
        return self

    def isOpaque(self):
        return False

    def drawRect_(self, _dirty_rect):
        # ★ 2026-08-29: "배경 자체가 없어도 될거같아, 말은 말풍선에서" 요청 —
        # 이미지+텍스트를 통째로 감싸던 반투명 사각형을 없애고, 이미지는
        # 배경 없이 그대로, 상태 텍스트만 꼬리 달린 말풍선 안에 그린다.
        bubble = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(BUBBLE_RECT, 14, 14)
        tail = NSBezierPath.bezierPath()
        tail.moveToPoint_(BUBBLE_TAIL_POINTS[0])
        tail.lineToPoint_(BUBBLE_TAIL_POINTS[1])
        tail.lineToPoint_(BUBBLE_TAIL_POINTS[2])
        tail.closePath()
        NSColor.colorWithCalibratedWhite_alpha_(0.10, 0.55).setFill()
        bubble.fill()
        tail.fill()
        if self.image is not None:
            self.image.drawInRect_(IMAGE_RECT)
        else:
            NSString.stringWithString_("🤖").drawInRect_withAttributes_(
                NSMakeRect(
                    IMAGE_RECT.origin.x + 3, IMAGE_RECT.origin.y + 5,
                    IMAGE_RECT.size.width - 6, IMAGE_RECT.size.height - 6,
                ),
                {"NSFont": NSFont.systemFontOfSize_(38)},
            )
        cards = self.cards or list(DEFAULT_CARDS)
        headline, usage = cards[self.card_index % len(cards)]
        NSString.stringWithString_(headline).drawInRect_withAttributes_(
            NSMakeRect(BUBBLE_RECT.origin.x + 12, BUBBLE_RECT.origin.y + 26, BUBBLE_RECT.size.width - 24, 20),
            {"NSFont": NSFont.boldSystemFontOfSize_(14), "NSColor": NSColor.whiteColor()},
        )
        NSString.stringWithString_(usage).drawInRect_withAttributes_(
            NSMakeRect(BUBBLE_RECT.origin.x + 12, BUBBLE_RECT.origin.y + 6, BUBBLE_RECT.size.width - 24, 18),
            {"NSFont": NSFont.monospacedDigitSystemFontOfSize_weight_(12, 0.25),
             "NSColor": NSColor.colorWithCalibratedRed_green_blue_alpha_(0.73, 0.82, 1.0, 1.0)},
        )

    def updateCards_(self, cards):
        self.cards = list(cards) if cards else list(DEFAULT_CARDS)
        if self.card_index >= len(self.cards):
            self.card_index = 0
        self.setNeedsDisplay_(True)

    def rotateCard_(self, _timer):
        if len(self.cards) > 1:
            self.card_index = (self.card_index + 1) % len(self.cards)
            self.setNeedsDisplay_(True)

    def mouseDown_(self, _event):
        self.dragged = False

    def mouseDragged_(self, event):
        self.dragged = True
        frame = self.window().frame()
        self.window().setFrameOrigin_(NSMakePoint(
            frame.origin.x + event.deltaX(), frame.origin.y - event.deltaY()
        ))

    def mouseUp_(self, event):
        if self.dragged:
            self.owner.petDidMove()
            return
        # ★ 2026-08-29: "펫그림을 누를때만 클릭이 되면 좋겠어" 요청 — 말풍선이나
        # 빈 공간을 눌러도 메뉴가 안 뜨고, 이미지 위를 눌렀을 때만 반응한다.
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        if _point_in_rect(point, IMAGE_RECT):
            self.owner.petWasClicked()

    def rightMouseDown_(self, _event):
        self.owner.petWasRightClicked()


class ShiftAlarmPet:
    def __init__(self, app, config, save_callback, asset_path):
        self.app, self.config, self.save_callback = app, config, save_callback
        image = NSImage.alloc().initWithContentsOfFile_(asset_path) if os.path.exists(asset_path) else None
        x, y = self._initial_position()
        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, PET_WIDTH, PET_HEIGHT), style, NSBackingStoreBuffered, False
        )
        self.panel.setOpaque_(False)
        self.panel.setBackgroundColor_(NSColor.clearColor())
        self.panel.setHasShadow_(True)
        self.panel.setFloatingPanel_(True)
        self.panel.setLevel_(NSFloatingWindowLevel)
        self.panel.setHidesOnDeactivate_(False)
        # 일반 Space에는 따라가되 native 전체화면 위까지 덮지는 않는다.
        self.panel.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces)
        self.view = ShiftAlarmPetView.alloc().initWithFrame_owner_image_(
            NSMakeRect(0, 0, PET_WIDTH, PET_HEIGHT), self, image
        )
        self.panel.setContentView_(self.view)
        # 숨김은 실행 세션에만 유효하다. 메뉴바까지 가려진 상황에서도 앱을
        # 재시작하면 반드시 Pet이 복구되어야 하므로 영구 visible 상태는 쓰지 않는다.
        self.panel.orderFrontRegardless()
        # ★ 2026-08-29: "30초 단위로 말풍선을 바꿔가며 표기" 요청 — 근무·저장공간·
        # 리마인더·AI 사용량을 카드 여러 장으로 받아 이 타이머가 자동으로 넘긴다.
        # __init__이 메인 스레드에서 도니 스케줄된 타이머는 기본(Default) 런루프
        # 모드에 자동으로 걸려 rumps의 이벤트 루프 안에서 그대로 돈다.
        self.rotate_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            CARD_ROTATE_SECONDS, self.view, "rotateCard:", None, True
        )

    def _initial_position(self):
        screen = NSScreen.mainScreen()
        visible = screen.visibleFrame() if screen is not None else NSMakeRect(0, 0, 1440, 900)
        x = float(self.config.get("pet_x", visible.origin.x + visible.size.width - PET_WIDTH - 20))
        y = float(self.config.get("pet_y", visible.origin.y + 28))
        return clamp_pet_position(x, y, self._visible_frames())

    @staticmethod
    def _visible_frames():
        return [
            (frame.origin.x, frame.origin.y, frame.size.width, frame.size.height)
            for frame in (screen.visibleFrame() for screen in NSScreen.screens())
        ]

    def _clamp_to_visible_screen(self):
        origin = self.panel.frame().origin
        x, y = clamp_pet_position(origin.x, origin.y, self._visible_frames())
        self.panel.setFrameOrigin_(NSMakePoint(x, y))
        self.config["pet_x"], self.config["pet_y"] = round(x, 1), round(y, 1)

    def update(self, cards):
        """cards: [(headline, usage), ...] — 여러 장이면 30초 간격으로 자동으로
        다음 장으로 넘어간다(rotateCard_). 한 장뿐이면 그 카드만 계속 보여준다."""
        self.view.updateCards_(cards)

    def show(self):
        self._clamp_to_visible_screen()
        self.save_callback(self.config)
        self.panel.orderFrontRegardless()

    def hide(self):
        self.panel.orderOut_(None)

    def toggle(self):
        self.hide() if self.panel.isVisible() else self.show()

    def close(self):
        self.panel.close()

    def _bounce(self):
        """클릭했을 때 살짝 커졌다 원래 크기로 돌아오는 팝 애니메이션.
        "클릭하면 움직인다던가" 요청(2026-08-29) — 화면 좌표를 저장/복구하는
        petDidMove()와 안 얽히도록 panel.frame()만 잠깐 건드리고 위치는
        원래 origin 그대로 유지한다(중심을 기준으로 살짝 부풀렸다 줄어듦)."""
        original = self.panel.frame()
        grown = NSMakeRect(
            original.origin.x - 4, original.origin.y - 3,
            original.size.width + 8, original.size.height + 6,
        )

        def _shrink_back(completion=None):
            def shrink_changes(ctx):
                ctx.setDuration_(0.10)
                self.panel.animator().setFrame_display_(original, True)
            NSAnimationContext.runAnimationGroup_completionHandler_(shrink_changes, None)

        def grow_changes(ctx):
            ctx.setDuration_(0.08)
            self.panel.animator().setFrame_display_(grown, True)

        NSAnimationContext.runAnimationGroup_completionHandler_(grow_changes, _shrink_back)

    def petWasClicked(self):
        # ★ 2026-08-29: "클릭하면 shift alarm의 항목이 보여서 클릭이 가능했으면
        # 좋겠어" 요청 — 기존엔 "현재 설정" 상세 창만 떴는데, 이제 메뉴바와
        # 완전히 같은 NSMenu(rumps가 관리하는 실제 메뉴)를 Pet 바로 위에 그대로
        # 띄운다. "현재 설정 확인"은 그 메뉴의 기타 하위메뉴에 그대로 남아있어
        # 기존 기능이 없어지진 않는다.
        self._bounce()
        ns_menu = self.app.menu._menu
        location = NSMakePoint(0, PET_HEIGHT)
        ns_menu.popUpMenuPositioningItem_atLocation_inView_(None, location, self.view)

    def petWasRightClicked(self):
        self.hide()

    def petDidMove(self):
        origin = self.panel.frame().origin
        self.config["pet_x"], self.config["pet_y"] = round(origin.x, 1), round(origin.y, 1)
        self.save_callback(self.config)
