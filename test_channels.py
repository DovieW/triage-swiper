import unittest
from fetch_channels import avatar_url


class ChannelAvatarTest(unittest.TestCase):
    def test_finds_avatar_with_either_attribute_order_and_requests_small_image(self):
        for markup in ('<meta property="og:image" content="https://yt3.googleusercontent.com/example=s900-c-k-no-rj">', '<meta content="https://yt3.ggpht.com/example=s900-c-k-no-rj" property="og:image">'):
            self.assertIn('=s64-', avatar_url(markup))

    def test_rejects_non_youtube_image_hosts_and_missing_avatars(self):
        for markup in ('<html>No avatar</html>', '<meta property="og:image" content="https://example.com/avatar.jpg">', '<meta property="og:image" content="http://yt3.googleusercontent.com/avatar">'):
            with self.assertRaises(ValueError):
                avatar_url(markup)
