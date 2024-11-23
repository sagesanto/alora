import unittest
from alora import Observatory

class TestObservatory(unittest.TestCase):

    def setUp(self):
        # setup code to run before each test
        self.observatory = Observatory()

    def tearDown(self):
        del self.observatory
        # cleanup code to run after each test

    def test_connect(self):
        self.observatory.connect()
        self.assertIsNotNone(self.observatory.telescope)
        self.assertIsNotNone(self.observatory.dome)
        self.assertIsNotNone(self.observatory.camera)

if __name__ == '__main__':
    unittest.main()