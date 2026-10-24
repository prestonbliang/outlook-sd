import unittest

from api.values import coordinates, finite_number
from pipeline.security import official_link


class SourceValueTests(unittest.TestCase):
    def test_valid_source_numbers(self):
        self.assertEqual(finite_number("12.5"), 12.5)
        self.assertEqual(finite_number(0), 0)
        self.assertEqual(coordinates("32.7", "-117.1"), (32.7, -117.1))

    def test_missing_and_nonfinite_values_are_not_numbers(self):
        for value in [None, "unknown", "", True, float("nan"), float("inf"), "-inf"]:
            self.assertIsNone(finite_number(value))
        for lat, lon in [(91, 0), (0, -181), (None, 0), (0, "bad"), (float("nan"), 0)]:
            self.assertIsNone(coordinates(lat, lon))

    def test_incident_links_stay_on_the_official_host(self):
        fallback = "https://www.fire.ca.gov/incidents"
        self.assertEqual(official_link("/incidents/2026/test", fallback), "https://www.fire.ca.gov/incidents/2026/test")
        for value in ["javascript:alert(1)", "https://www.fire.ca.gov.evil.invalid/", "https://user@www.fire.ca.gov/",
                      "//evil.invalid/", "http://www.fire.ca.gov/", None]:
            self.assertEqual(official_link(value, fallback), fallback)


if __name__ == "__main__":
    unittest.main()
