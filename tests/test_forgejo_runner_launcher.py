"""Harness checks without invoking Podman or touching the runner."""
import sys
import unittest
import run_forgejo_runner_launcher as harness


class LauncherHarnessTests(unittest.TestCase):
    def test_only_fixed_result_schema_is_accepted(self):
        self.assertEqual(harness.records('private log\nH81_RESULT {"case":"opt_in","result":"pass"}'),[{'case':'opt_in','result':'pass'}])
        for value in ['{"case":"opt_in","result":"SYNTHETIC_SECRET"}',
                      '{"case":"opt_in","result":"pass","secret":"SYNTHETIC_SECRET"}',
                      '{"case":"SYNTHETIC_SECRET","result":"pass"}']:
            with self.assertRaises(ValueError):harness.records('H81_RESULT '+value)
        self.assertEqual(harness.records('SYNTHETIC_SECRET'),[])

    def test_child_output_limit_stops_process(self):
        with self.assertRaises(ValueError):
            harness.launch([sys.executable,'-c','import sys;sys.stdout.write("x"*70000)'])

if __name__=='__main__':unittest.main()
