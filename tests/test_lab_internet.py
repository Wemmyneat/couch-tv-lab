"""couch-tv-lab: the internet widget's source (bridge/lab.py lab.internet)."""
import asyncio
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


class InternetOnline(unittest.TestCase):
    """A missing reading must never show as online (security review: fail-open monitoring)."""
    def run_panel(self, internet, values, latency=None):
        async def promv(q, ttl=15):
            return values.get(q)

        async def nothing(*a):
            return None

        async def rtt(*a):
            return latency
        with mock.patch.object(lab, "INTERNET", conf(internet)), mock.patch.object(lab, "_promv", promv), \
                mock.patch.object(lab, "adguard_state", nothing), mock.patch.object(lab, "_latency_ms", rtt):
            return asyncio.run(lab.panel_internet())

    def test_online_query_without_answer_is_unknown(self):
        r = self.run_panel({"source": "prometheus", "queries": {"online": "up"}}, {})
        self.assertIsNone(r["online"])
        self.assertEqual(r["label"], "no data")

    def test_online_query_answering(self):
        self.assertTrue(self.run_panel({"source": "prometheus", "queries": {"online": "up"}}, {"up": 1})["online"])
        r = self.run_panel({"source": "prometheus", "queries": {"online": "up"}}, {"up": 0})
        self.assertFalse(r["online"])
        self.assertEqual(r["label"], "offline")

    def test_no_online_query_uses_a_real_connection(self):
        self.assertFalse(self.run_panel({"source": "prometheus", "queries": {"down": "d"}}, {}, latency=None)["online"])
        self.assertTrue(self.run_panel({"source": "prometheus", "queries": {"down": "d"}}, {}, latency=25)["online"])

    def test_signal_score_is_not_shown_as_healthy_when_offline(self):
        r = self.run_panel({"source": "prometheus", "queries": {"online": "up", "rsrp": "r", "sinr": "s"}},
                           {"r": -80, "s": 20, "up": 0})
        self.assertEqual(r["label"], "offline")


if __name__ == "__main__":
    unittest.main()
