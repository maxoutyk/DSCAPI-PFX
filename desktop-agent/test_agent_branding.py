import unittest

from agent_branding import load_agent_icon_image, resolve_agent_icon_path


class AgentBrandingTests(unittest.TestCase):
    def test_resolve_agent_icon_path(self):
        path = resolve_agent_icon_path()
        self.assertIsNotNone(path)
        self.assertTrue(path.is_file())
        self.assertEqual(path.name, 'agent_icon.png')

    def test_load_agent_icon_image(self):
        image = load_agent_icon_image()
        self.assertLessEqual(max(image.size), 64)
        self.assertGreater(min(image.size), 0)

    def test_load_agent_icon_image_alert_overlay(self):
        normal = load_agent_icon_image(alert=False)
        alert = load_agent_icon_image(alert=True)
        self.assertEqual(normal.size, alert.size)
        self.assertNotEqual(list(normal.getdata()), list(alert.getdata()))


if __name__ == '__main__':
    unittest.main()
