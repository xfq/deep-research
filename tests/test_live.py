import json
import os
import signal
import sys
import tempfile
import unittest
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deep_research_agent.cli import main


@unittest.skipUnless(
    os.environ.get("RUN_LIVE_RESEARCH_TEST") == "1"
    and bool(os.environ.get("OPENAI_API_KEY"))
    and bool(os.environ.get("TAVILY_API_KEY")),
    "set RUN_LIVE_RESEARCH_TEST=1 with provider credentials",
)
class LiveProviderSmokeTests(unittest.TestCase):
    def test_configured_cli_researches_one_live_public_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)

            def fail_on_timeout(signum, frame):
                raise TimeoutError("live smoke exceeded wall-clock guard")

            previous_handler = signal.getsignal(signal.SIGALRM)
            signal.signal(signal.SIGALRM, fail_on_timeout)
            signal.alarm(65)
            started_at = time.monotonic()
            try:
                exit_code = main(
                    [
                        "What is LangChain Deep Agents?",
                        "--max-searches",
                        "1",
                        "--max-source-reads",
                        "1",
                        "--max-elapsed-seconds",
                        "60",
                        "--output-dir",
                        str(output_directory),
                    ]
                )
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, previous_handler)
            self.assertLess(time.monotonic() - started_at, 65)

            self.assertIn(exit_code, {0, 3})
            sources = json.loads(
                (output_directory / "sources.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(sources), 1)
            self.assertIn(
                sources[0]["url"],
                (output_directory / "report.md").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
