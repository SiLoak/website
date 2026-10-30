from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from location.services import categorize, distance_km, opening_status, parse_hours

JAKARTA = ZoneInfo("Asia/Jakarta")


def at(weekday_date, hour, minute=0):
    """2026-10-26 is a Monday."""
    return datetime(2026, 10, 26 + weekday_date, hour, minute, tzinfo=JAKARTA)


class CategorizeTests(SimpleTestCase):
    def test_known_prefixes_map_to_service_types(self):
        self.assertEqual(categorize("UPS Merdeka 2")[0], "ups")
        self.assertEqual(categorize("Bank Sampah ASRI 20")[0], "bank_sampah")
        self.assertEqual(categorize("TPS3R Cimanggis")[0], "tps")
        self.assertEqual(categorize("TPST Bantargebang")[0], "tps")
        self.assertEqual(categorize("TPA Cipayung")[0], "tpa")
        self.assertEqual(categorize("Rumah Kompos Beji")[0], "kompos")

    def test_unknown_names_fall_back_to_other(self):
        self.assertEqual(categorize("Gudang Rongsok Pak Udin"), ("lainnya", "Lainnya"))


class ParseHoursTests(SimpleTestCase):
    def test_parses_day_range_and_time_range(self):
        hours = parse_hours("Senin - Sabtu, 08.30 - 17.00 WIB")

        self.assertEqual(hours.days, {0, 1, 2, 3, 4, 5})
        self.assertEqual(hours.opens, time(8, 30))
        self.assertEqual(hours.closes, time(17, 0))

    def test_parses_time_only_as_every_day(self):
        hours = parse_hours("07:00-15:00")

        self.assertEqual(hours.days, set(range(7)))
        self.assertEqual(hours.closes, time(15, 0))

    def test_parses_single_day(self):
        self.assertEqual(parse_hours("Minggu, 06.00 - 10.00").days, {6})

    def test_unparseable_or_empty_text_returns_none(self):
        self.assertIsNone(parse_hours(""))
        self.assertIsNone(parse_hours("Hubungi pengelola"))


class OpeningStatusTests(SimpleTestCase):
    hours = "Senin - Sabtu, 08.00 - 16.00 WIB"

    def test_open_during_hours(self):
        status = opening_status(self.hours, at(0, 10))
        self.assertTrue(status["is_open"])
        self.assertEqual(status["label"], "Buka sampai 16.00")

    def test_closed_before_opening_today(self):
        status = opening_status(self.hours, at(0, 7))
        self.assertFalse(status["is_open"])
        self.assertEqual(status["label"], "Tutup · buka hari ini 08.00")

    def test_closed_after_hours_points_to_next_open_day(self):
        self.assertEqual(opening_status(self.hours, at(0, 18))["label"], "Tutup · buka Selasa 08.00")
        self.assertEqual(opening_status(self.hours, at(5, 18))["label"], "Tutup · buka Senin 08.00")

    def test_unknown_hours(self):
        status = opening_status("", at(0, 10))
        self.assertIsNone(status["is_open"])
        self.assertEqual(status["label"], "Jam belum tersedia")


class DistanceTests(SimpleTestCase):
    def test_distance_between_two_known_points(self):
        # Monas to Bundaran HI is roughly 2.2 km.
        self.assertAlmostEqual(distance_km(-6.1754, 106.8272, -6.1950, 106.8231), 2.2, delta=0.15)

    def test_zero_distance(self):
        self.assertEqual(distance_km(-6.2, 106.8, -6.2, 106.8), 0)
