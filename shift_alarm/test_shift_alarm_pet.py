import unittest

from shift_alarm_pet import clamp_pet_position


class ClampPetPositionTests(unittest.TestCase):
    def test_keeps_fully_visible_position(self):
        self.assertEqual(clamp_pet_position(100, 100, [(0, 0, 1000, 800)], 300, 80), (100, 100))

    def test_clamps_entire_pet_inside_screen(self):
        self.assertEqual(clamp_pet_position(950, -20, [(0, 0, 1000, 800)], 300, 80), (700, 0))

    def test_uses_nearest_connected_screen(self):
        frames = [(0, 0, 1000, 800), (1000, 100, 1200, 900)]
        self.assertEqual(clamp_pet_position(2300, 400, frames, 300, 80), (1900, 400))

    def test_handles_screen_smaller_than_pet(self):
        self.assertEqual(clamp_pet_position(50, 50, [(10, 20, 100, 40)], 300, 80), (10, 20))


if __name__ == "__main__":
    unittest.main()
