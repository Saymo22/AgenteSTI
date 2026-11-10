import socket
import unittest
from unittest.mock import Mock, patch

from sti.servidor.identificacao import HostnameResolver


class HostnameTests(unittest.TestCase):
    def test_dns_name_or_missing_ptr(self):
        callback = Mock()
        resolver = HostnameResolver(callback)
        with patch('socket.gethostbyaddr', return_value=('pc-204.empresa.local.', [], ['10.2.116.33'])):
            resolver.resolve('10.2.116.33')
        callback.assert_called_once_with('10.2.116.33', 'pc-204.empresa.local')
        callback.reset_mock()
        with patch('socket.gethostbyaddr', side_effect=socket.herror('Sem PTR')):
            resolver.resolve('10.2.116.33')
        callback.assert_not_called()

    def test_invalid_dns_names_are_ignored(self):
        callback = Mock()
        resolver = HostnameResolver(callback)
        for name in ('', '10.2.116.33', 'nome\ninvalido', 'a' * 254):
            with patch('socket.gethostbyaddr', return_value=(name, [], [])):
                resolver.resolve('10.2.116.33')
        callback.assert_not_called()

    def test_slow_dns_has_bounded_queue_and_no_duplicate_pending_lookup(self):
        resolver = HostnameResolver(Mock(), workers=0)
        for _ in range(1000):
            resolver.schedule('10.2.116.33')
        self.assertEqual(resolver.pending.qsize(), 1)
        for index in range(1000):
            resolver.schedule(f'10.2.{116 + index // 256}.{index % 256}')
        self.assertEqual(resolver.pending.qsize(), 128)
