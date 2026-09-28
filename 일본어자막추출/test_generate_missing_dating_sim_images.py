import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import generate_missing_dating_sim_images as backlog  # noqa: E402


class BatchImagePresetTests(unittest.TestCase):
    def test_batch_generation_uses_quality_preset_without_changing_dimensions(self):
        command = backlog.generation_command(Path("/tmp/example-work"))

        self.assertEqual(command[-1], "0.28")
        self.assertIn("--steps", command)
        self.assertEqual(command[command.index("--steps") + 1], "30")
        self.assertEqual(command[command.index("--hires-scale") + 1], "1.5")
        self.assertEqual(command[command.index("--sampler") + 1], "dpmpp_2m")
        self.assertEqual(command[command.index("--scheduler") + 1], "karras")
        self.assertNotIn("--width", command)
        self.assertNotIn("--height", command)


if __name__ == "__main__":
    unittest.main()
