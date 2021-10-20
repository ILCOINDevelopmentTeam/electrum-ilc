import asyncio

from electrum.ecc import ECPrivkey
from electrum.lnutil import LNPeerAddr
from electrum.lntransport import LNResponderTransport, LNTransport

from . import ElectrumTestCase
from .test_bitcoin import needs_test_with_all_chacha20_implementations


class TestLNTransport(ElectrumTestCase):

    @needs_test_with_all_chacha20_implementations
    def test_responder(self):
        # local static
        ls_priv=bytes.fromhex('2121212121212121212121212121212121212121212121212121212121212121')
        # ephemeral
        e_priv=bytes.fromhex('2222222222222222222222222222222222222222222222222222222222222222')

        class Writer:
            def __init__(self):
                self.state = 0
            def write(self, data):
                assert self.state == 0
                self.state += 1
                assert len(data) == 50
        class Reader:
            def __init__(self):
                self.state = 0
            async def read(self, num_bytes):
                assert self.state in (0, 1)
                self.state += 1
                if self.state-1 == 0:
                    assert num_bytes == 50
                    return bytes.fromhex('00036360e856310ce5d294e8be33fc807077dc56ac80d95d9cd4ddbd21325eff73f70df6086551151f58b8afe6c195782c6a')
                elif self.state-1 == 1:
                    assert num_bytes == 66
                    return bytes.fromhex('00b9e3a702e93e3a9948c2ed6e5fd7590a6e1c3a0344cfc9d5b57357049aa22355361aa02e55a8fc28fef5bd6d71ad0c38228dc68b1c466263b47fdf31e560e139ba')
        transport = LNResponderTransport(ls_priv, Reader(), Writer())
        asyncio.get_event_loop().run_until_complete(transport.handshake(epriv=e_priv))

    @needs_test_with_all_chacha20_implementations
    def test_loop(self):
        loop = asyncio.get_event_loop()
        responder_shaked = asyncio.Event()
        server_shaked = asyncio.Event()
        responder_key = ECPrivkey.generate_random_key()
        initiator_key = ECPrivkey.generate_random_key()
        async def cb(reader, writer):
            t = LNResponderTransport(responder_key.get_secret_bytes(), reader, writer)
            self.assertEqual(await t.handshake(), initiator_key.get_public_key_bytes())
            t.send_bytes(b'hello from server')
            self.assertEqual(await t.read_messages().__anext__(), b'hello from client')
            responder_shaked.set()
        server_future = asyncio.ensure_future(asyncio.start_server(cb, '127.0.0.1', 42898))
        loop.run_until_complete(server_future)
        server = server_future.result()  # type: asyncio.Server
        async def connect():
            peer_addr = LNPeerAddr('127.0.0.1', 42898, responder_key.get_public_key_bytes())
            t = LNTransport(initiator_key.get_secret_bytes(), peer_addr, proxy=None)
            await t.handshake()
            t.send_bytes(b'hello from client')
            self.assertEqual(await t.read_messages().__anext__(), b'hello from server')
            server_shaked.set()

        try:
            connect_future = asyncio.ensure_future(connect())
            loop.run_until_complete(responder_shaked.wait())
            loop.run_until_complete(server_shaked.wait())
        finally:
            server.close()
            loop.run_until_complete(server.wait_closed())
