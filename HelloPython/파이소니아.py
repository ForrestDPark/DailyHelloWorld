import json
import os
from CommonFunc_05 import *
class Coder:
    def __init__(self, username):
        self.username = username
        self.level = 1
        self.experience = 0
        self.max_level = 100
        self.level_requirements = {level: 100 * level for level in range(1, self.max_level + 1)}
        self.save_file = f"{self.username}_data.json"

        # 저장 파일이 존재하면 이전 레벨과 경험치를 불러옵니다.
        self.load_data()

    def load_data(self):
        try:
            with open(self.save_file, 'r') as f:
                data = json.load(f)
                self.level = data.get('level', 1)
                self.experience = data.get('experience', 0)
        except FileNotFoundError:
            pass  # 파일이 없으면 새로 생성

    def save_data(self):
        data = {
            'level': self.level,
            'experience': self.experience
        }
        with open(self.save_file, 'w') as f:
            json.dump(data, f)

    def gain_experience(self, solved_problems):
        self.experience += solved_problems * 10
        self.check_level_up()
        self.save_data()

    def check_level_up(self):
        while self.experience >= self.level_requirements[self.level]:
            self.level += 1
            self.experience -= self.level_requirements[self.level - 1]
            print(f"{self.username}님, 레벨업! 현재 레벨: {self.level}")
            self.show_level_up_reward()

    def show_level_up_reward(self):
        if self.level <= 33:
            print("초급 단계 레벨업 보상: 기본적인 코딩 지식 습득")
        elif self.level <= 66:
            print("중급 단계 레벨업 보상: 다양한 프로그래밍 언어 및 라이브러리 사용 가능")
        elif self.level <= self.max_level:
            print("고급 단계 레벨업 보상: 알고리즘, 데이터 구조, 디자인 패턴에 대한 심층적인 이해")
        else:
            print("최고 레벨 달성! 코딩 마스터에게만 주어지는 특별한 칭호 및 권한 부여")

    def show_current_status(self):
        print(yellow(f"{self.username}님의 현재 상태:"))
        print(yellow(f"현재 레벨: {self.level}"))
        print(yellow(f"현재 경험치: {self.experience}"))
        print(red(f"다음 레벨까지 필요한 경험치: {self.level_requirements[self.level] - self.experience}"))

# 사용 예시
username = input("사용자 이름을 입력하세요: ")
coder = Coder(username)
coder.show_current_status()

while True:
    solved_problems = int(input("오늘 해결한 코딩 문제 수를 입력하세요: "))
    coder.gain_experience(solved_problems)
    coder.show_current_status()
    if coder.level == coder.max_level:
        print(f"{username}님, 축하합니다! 코딩의 최고봉에 도달했습니다!")
        break