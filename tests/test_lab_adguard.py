"""couch-tv-lab: the AdGuard check reads plain DNS answers (bridge/lab.py dns_query / dns_blocked)."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "bridge"))
import lab  # noqa: E402


def answer(qid, rcode=0, records=()):
    """A DNS reply to dns_query(name, qid), with (type, rdata) answers that point back at the question."""
    q = lab.dns_query("doubleclick.net", qid)[12:]
    body = b"".join(b"\xc0\x0c" + struct.pack(">HHIH", t, 1, 60, len(rd)) + rd for t, rd in records)
    return struct.pack(">HHHHHH", qid, 0x8180 | rcode, 1, len(records), 0, 0) + q + body


class DnsBlocked(unittest.TestCase):
    def test_query_shape(self):
        q = lab.dns_query("ad.example.com", 7)
        self.assertEqual(q[:2], b"\x00\x07")
        self.assertIn(b"\x02ad\x07example\x03com\x00", q)

    def test_null_ip_is_blocked(self):
        self.assertTrue(lab.dns_blocked(answer(5, records=[(1, bytes(4))]), 5))

    def test_nxdomain_and_refused_are_blocked(self):
        self.assertTrue(lab.dns_blocked(answer(5, rcode=3), 5))
        self.assertTrue(lab.dns_blocked(answer(5, rcode=5), 5))

    def test_empty_noerror_is_blocked(self):
        self.assertTrue(lab.dns_blocked(answer(5), 5))

    def test_real_address_is_not_blocked(self):
        self.assertFalse(lab.dns_blocked(answer(5, records=[(1, bytes([142, 251, 47, 110]))]), 5))

    def test_cname_then_address_is_not_blocked(self):
        self.assertFalse(lab.dns_blocked(answer(5, records=[(5, b"\xc0\x0c"), (1, bytes([1, 2, 3, 4]))]), 5))

    def test_wrong_id_or_garbage_is_unknown(self):
        self.assertIsNone(lab.dns_blocked(answer(5, records=[(1, bytes(4))]), 6))
        self.assertIsNone(lab.dns_blocked(b"\x00\x05", 5))
        self.assertIsNone(lab.dns_blocked(answer(5, records=[(1, bytes(4))])[:-3], 5))


if __name__ == "__main__":
    unittest.main()
