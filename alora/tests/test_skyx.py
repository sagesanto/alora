import unittest
from alora.observatory import Telescope
import alora.observatory.skyx.components as components

class TestSkyX(unittest.TestCase):

    def setUp(self):
        # setup code to run before each test
        components.conn = components.SkyXClient(components.config["SKYX_PORT"])
        self.skyx_conn = components.conn
        self.telescope = Telescope()

    def tearDown(self):
        del self.telescope
        self.skyx_conn.disconnect()
        # cleanup code to run after each test

    def test_skyx_disconnect(self):
        self.skyx_conn.disconnect()
        self.assertFalse(self.skyx_conn.connected, "SkyX Client still reports connected status after disconnecting")
        self.assertTrue(components.is_socket_closed(self.skyx_conn.socket), "SkyX Client socket still open after disconnecting")

    def test_disconnected_status(self):
        self.telescope.conn.disconnect()
        self.assertFalse(self.telescope.connected, "Telescope still reports connected status after disconnecting")
    
    def test_disconnected_park_fails(self):
        self.skyx_conn.disconnect()
        with self.assertRaises(ConnectionError):
            self.telescope.park()
    
    def test_disconnected_pos_fails(self):
        self.skyx_conn.disconnect()
        with self.assertRaises(ConnectionError):
            self.telescope.pos
    
    def test_disconnected_mount_conn_fails(self):
        self.skyx_conn.disconnect()
        with self.assertRaises(ConnectionError):
            self.telescope.test_mount_conn()
        
    def test_disconnected_parked_fails(self):
        self.skyx_conn.disconnect()
        with self.assertRaises(ConnectionError):
            self.telescope.parked
        
    def test_disconnected_last_slew_error_fails(self):
        self.skyx_conn.disconnect()
        with self.assertRaises(ConnectionError):
            self.telescope.check_last_slew_error()

if __name__ == '__main__':
    unittest.main()