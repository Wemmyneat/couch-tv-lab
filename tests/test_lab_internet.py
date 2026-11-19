"""couch-tv-lab: the internet widget's source (bridge/lab.py lab.internet)."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "bridge"))
import lab  # noqa: E402


def conf(internet):
    with mock.patch.object(lab, "LAB", {"internet": internet} if internet is not None else {}):
        return lab._internet_conf()


class InternetConf(unittest.TestCase):
    def test_default_is_ping_to_a_public_host(self):
        c = conf(None)
        self.assertEqual((c["source"], c["host"], c["port"], c["queries"]), ("ping", "1.1.1.1", 443, {}))

    def test_unknown_source_falls_back_to_ping(self):
        self.assertEqual(conf({"source": "rm -rf"})["source"], "ping")

    def test_mtn_preset_and_override(self):
        c = conf({"source": "mtn", "queries": {"devices": "max(my_devices)", "bogus": "x", "up": 5}})
        self.assertEqual(c["queries"]["devices"], "max(my_devices)")
        self.assertIn("$tech", c["queries"]["rsrp"])
        self.assertNotIn("bogus", c["queries"])
        self.assertEqual(c["network"], {"query": "mtn_network_info", "label": "network_type"})

    def test_prometheus_takes_only_known_keys(self):
        c = conf({"source": "prometheus", "queries": {"down": "rate(x[2m])", "online": "up{job='r'}", "evil": "y"},
                  "network": "Fibre"})
        self.assertEqual(set(c["queries"]), {"down", "online"})
        self.assertEqual(c["network"], "Fibre")

    def test_bad_host_and_port_are_ignored(self):
        c = conf({"source": "ping", "host": "a b;c", "port": 99999})
        self.assertEqual((c["host"], c["port"]), ("1.1.1.1", 443))

    def test_latency_score(self):
        self.assertEqual(lab.latency_score(10), 100)
        self.assertEqual(lab.latency_score(400), 0)
        self.assertIsNone(lab.latency_score(None))
        self.assertTrue(40 < lab.latency_score(200) < 60)


if __name__ == "__main__":
    unittest.main()
