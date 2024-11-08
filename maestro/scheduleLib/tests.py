import sys, os
import unittest
import datetime
from astral import LocationInfo
from configparser import ConfigParser
from astropy.coordinates import Angle
import astropy.units as u


from candidateDatabase import Candidate, CandidateDatabase
from genUtils import overlapping_time_windows, get_current_sidereal_time, find_transit_time

genConfig = ConfigParser()
files_path = os.path.join(os.path.dirname(__file__),os.pardir,"files")
genConfig.read(os.path.join(files_path, "configs", "config.txt"))
genConfig = genConfig["DEFAULT"]

class TestGenUtils(unittest.TestCase):
    def setUp(self):
        self.location = LocationInfo(name=genConfig["obs_name"], region=genConfig["obs_region"], timezone=genConfig["obs_timezone"],
                        latitude=genConfig.getfloat("obs_lat"),
                        longitude=genConfig.getfloat("obs_lon"))

    def test_overlapping_time_windows(self):
        # test 1: time windows that do overlap
        start1, end1 = datetime.datetime(2024, 1, 1, 0, 0), datetime.datetime(2024, 1, 1, 1, 0)
        start2, end2 = datetime.datetime(2024, 1, 1, 0, 30), datetime.datetime(2024, 1, 1, 1, 30)
        overlap_start_1, overlap_end_1 = overlapping_time_windows(start1, end1, start2, end2)
        self.assertEqual(overlap_start_1, start2)
        self.assertEqual(overlap_end_1, end1)

        # test 2: reverse the order of the time windows, should get the same result
        overlap_start_2, overlap_end_2 = overlapping_time_windows(start2, end2, start1, end1)
        self.assertEqual(overlap_start_2, overlap_start_1)
        self.assertEqual(overlap_end_2, overlap_end_1)

        # test 3: time windows that do not overlap
        start3, end3 = datetime.datetime(2024, 1, 1, 2, 0), datetime.datetime(2024, 1, 1, 3, 0)
        overlap_start_3, overlap_end_3 = overlapping_time_windows(start1, end1, start3, end3)
        self.assertIsNone(overlap_start_3)
        self.assertIsNone(overlap_end_3)

        # test 4: time windows that are the same
        overlap_start_4, overlap_end_4 = overlapping_time_windows(start1, end1, start1, end1)
        self.assertEqual(overlap_start_4, start1)
        self.assertEqual(overlap_end_4, end1)

        # test 5: time windows that are adjacent
        start5, end5 = datetime.datetime(2024, 1, 1, 1, 0), datetime.datetime(2024, 1, 1, 2, 0)
        overlap_start_5, overlap_end_5 = overlapping_time_windows(start1, end1, start5, end5)
        self.assertIsNone(overlap_start_5)
        self.assertIsNone(overlap_end_5)

        # test 6: second time window is entirely within the first
        start6, end6 = datetime.datetime(2024, 1, 1, 0, 15), datetime.datetime(2024, 1, 1, 0, 45)
        overlap_start_6, overlap_end_6 = overlapping_time_windows(start1, end1, start6, end6)
        self.assertEqual(overlap_start_6, start6)
        self.assertEqual(overlap_end_6, end6)

        # test 7: first time window is entirely within the second
        overlap_start_7, overlap_end_7 = overlapping_time_windows(start6, end6, start1, end1)
        self.assertEqual(overlap_start_7, start6)
        self.assertEqual(overlap_end_7, end6)

        # test 8: one time window is None
        overlap_start_8, overlap_end_8 = overlapping_time_windows(start1, end1, None, None)
        self.assertIsNone(overlap_start_8)
        self.assertIsNone(overlap_end_8)

        

    def test_transit_time(self):
        # test 1: time of transit of an object with RA = LST is the current time
        lst = get_current_sidereal_time(self.location)
        t = find_transit_time(lst,self.location)
        self.assertEqual(t, datetime.datetime.utcnow().replace(second=0, microsecond=0))

        # test 2: time of transit of an object with RA = LST + 2 hours is 2 hours from now
        lst = get_current_sidereal_time(self.location)
        t = find_transit_time(lst+Angle("30d"), self.location)
        self.assertEqual(t, datetime.datetime.utcnow().replace(second=0, microsecond=0) + datetime.timedelta(hours=2))

        # test 3: time of transit of an object with RA = LST - 2 hours is 2 hours ago
        lst = get_current_sidereal_time(self.location)
        t = find_transit_time(lst-Angle("30d"), self.location)
        self.assertEqual(t, datetime.datetime.utcnow().replace(second=0, microsecond=0) - datetime.timedelta(hours=2))


if __name__ == '__main__':
    unittest.main()