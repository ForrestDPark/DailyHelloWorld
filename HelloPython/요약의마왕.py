import os

class Summarizer:
    def __init__(self):
        self.level = 1
        self.experience = 0
        self.level_requirements = {
            1: 5,
            2: 10,
            3: 20,
            4: 40,
            5: 80,
            6: 160,
            7: 320,
            8: 640,
            9: 1280,
            10: 2560,
            11: 5120,
            12: 5120,
            13: 5120,
            14: 5120,
            15: 5120,
            16: 5120,
            17: 5120,
            18: 5120,
            19: 5120,
            20: 5120,
            21: 10240,
            22: 10240,
            23: 10240,
            24: 10240,
            25: 10240,
            26: 10240,
            27: 10240,
            28: 10240,
            29: 10240,
            30: 10240,
            31: 20480,
            32: 20480,
            33: 20480,
            34: 20480,
            35: 20480,
            36: 20480,
            37: 20480,
            38: 20480,
            39: 20480,
            40: 20480,
            41: 40960,
            42: 40960,
            43: 40960,
            44: 40960,
            45: 40960,
            46: 40960,
            47: 40960,
            48: 40960,
            49: 40960,
            50: 40960,
            51: 81920,
            52: 81920,
            53: 81920,
            54: 81920,
            55: 81920,
            56: 81920,
            57: 81920,
            58: 81920,
            59: 81920,
            60: 81920,
            61: 163840,
            62: 163840,
            63: 163840,
            64: 163840,
            65: 163840,
            66: 163840,
            67: 163840,
            68: 163840,
            69: 163840,
            70: 163840,
            71: 327680,
            72: 327680,
            73: 327680,
            74: 327680,
            75: 327680,
            76: 327680,
            77: 327680,
            78: 327680,
            79: 327680,
            80: 327680,
            81: 655360,
            82: 655360,
            83: 655360,
            84: 655360,
            85: 655360,
            86: 655360,
            87: 655360,
            88: 655360,
            89: 655360,
            90: 655360,
            91: 1310720,
            92: 1310720,
            93: 1310720,
            94: 1310720,
            95: 1310720,
            96: 1310720,
            97: 1310720,
            98: 1310720,
            99: 1310720,
            100: 1310720
        }
        self.save_file = "summarizer_data.txt"

        # 저장 파일이 존재하면 이전 레벨과 경험치를 불러옵니다.
        if os.path.exists(self.save_file):
            with open(self.save_file, "r") as f:
                data = f.read().split(",")
                self.level = int(data[0])
                self.experience = int(data[1])

    def gain_experience(self, experience):
        self.experience += experience
        self.check_level_up()
        self.save_progress()

    def check_level_up(self):
        while self.experience >= self.level_requirements[self.level]:
            self.level += 1
            self.experience -= self.level_requirements[self.level - 1]
            print(f"레벨업! 현재 레벨: {self.level}")
            self.show_level_up_reward()

    def show_level_up_reward(self):
        if self.level <= 10:
            print("초급 단계 레벨업 보상: 기본적인 요약 기술 습득")
        elif self.level <= 60:
            print("중급 단계 레벨업 보상: 요약 능력 향상을 위한 툴 획득")
        elif self.level <= 100:
            print("고급 단계 레벨업 보상: 요약 관련 전문 지식 습득")
        else:
            print("최고 레벨 달성! 요약 챔피언에게만 주어지는 특별한 칭호 및 권한 부여")

    def show_current_status(self):
        print(f"현재 레벨: {self.level}")
        print(f"현재 경험치: {self.experience}")
        print(f"다음 레벨까지 필요한 경험치: {self.level_requirements[self.level] - self.experience}")

    def save_progress(self):
        with open(self.save_file, "w") as f:
            f.write(f"{self.level},{self.experience}")

# 사용 예시
summarizer = Summarizer()
summarizer.show_current_status()

while True:
    num_summaries = int(input("요약 문단 개수를 입력하세요: "))
    summarizer.gain_experience(num_summaries)
    summarizer.show_current_status()
    if summarizer.level == 100:
        print("축하합니다! 요약의 최고봉에 도달했습니다!")
        break