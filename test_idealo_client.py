import json
import unittest
from types import SimpleNamespace
from idealo_client import IdealoClient


class FakeSession:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return next(self.results)


def response(data, structured=True):
    return SimpleNamespace(isError=False, structuredContent=data if structured else None,
                           content=[SimpleNamespace(type='text', text=json.dumps(data))])


class IdealoTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_and_pagination(self):
        product = {'productRef': 'opaque', 'itemType': 'PRODUCT'}
        session = FakeSession([response({'results': [product]}),
                               response({'offers': [{'key': 'a'}], 'nextOffset': 5}),
                               response({'offers': [{'key': 'b'}], 'nextOffset': 0}, False)])
        client = IdealoClient(session)
        found = await client.search('GPU')
        result = await client.offers(found['results'][0])
        self.assertEqual([o['key'] for o in result['offers']], ['a', 'b'])
        self.assertEqual(session.calls[2], ('get_product_offers', {'offset': 5, 'productRef': 'opaque', 'country': 'DE', 'type': 'PRODUCT'}))
        self.assertEqual(result['nextOffset'], 0)

    async def test_tool_error(self):
        session = FakeSession([SimpleNamespace(isError=True, content=['unauthorized'])])
        with self.assertRaises(RuntimeError):
            await IdealoClient(session).search('GPU')

    async def test_page_limit(self):
        session = FakeSession([response({'offers': [], 'nextOffset': 5})])
        result = await IdealoClient(session).offers({'productRef': 'opaque'}, max_pages=1)
        self.assertEqual(result['nextOffset'], 5)


if __name__ == '__main__':
    unittest.main()
