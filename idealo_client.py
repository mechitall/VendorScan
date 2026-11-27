"""VendorScan's read-only idealo MCP integration (Python 3.10+)."""
import argparse
import asyncio
import json
import os
from contextlib import asynccontextmanager

URL = 'https://mcp.idealo.com/mcp'


class IdealoClient:
    def __init__(self, session, country='DE'):
        self.session = session
        self.country = country

    async def call(self, name, **args):
        result = await self.session.call_tool(name, arguments=args)
        if result.isError:
            raise RuntimeError(f'{name}: {result.content}')
        structured = getattr(result, 'structuredContent', None)
        if isinstance(structured, dict):
            return structured
        for block in result.content:
            if getattr(block, 'type', None) == 'text':
                try:
                    payload = json.loads(block.text)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    return payload
        raise ValueError(f'{name}: no JSON object returned')

    async def search(self, query):
        return await self.call('search_products', query=query, country=self.country)

    def product_args(self, product):
        return dict(productRef=product['productRef'], country=self.country,
                    type=product.get('itemType', 'PRODUCT'))

    async def details(self, product):
        return await self.call('get_product_details', **self.product_args(product))

    async def history(self, product):
        return await self.call('get_product_price_history', **self.product_args(product))

    async def offers(self, product, max_pages=2):
        if max_pages < 1:
            raise ValueError('max_pages must be positive')
        offers, seen, offset = [], set(), 0
        for _ in range(max_pages):
            if offset in seen:
                raise RuntimeError('idealo repeated a pagination offset')
            seen.add(offset)
            page = await self.call('get_product_offers', offset=offset,
                                   **self.product_args(product))
            offers.extend(page['offers'])
            offset = page.get('nextOffset') or 0
            if offset <= 0:  # idealo marks the last page with 0, -1 or no nextOffset
                offset = 0
                break
        return {'offers': offers, 'nextOffset': offset, 'message': page.get('message')}


@asynccontextmanager
async def connect(token=None, country='DE'):
    """Connect to idealo. Uses IDEALO_ACCESS_TOKEN if set, else browser OAuth (cached)."""
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    token = token or os.environ.get('IDEALO_ACCESS_TOKEN')
    if token:
        http = httpx.AsyncClient(headers={'Authorization': f'Bearer {token}'}, timeout=30)
    else:
        from vendorscan.idealo_auth import oauth_provider, refresh_if_expiring
        await asyncio.to_thread(refresh_if_expiring)  # idealo returns 403, not 401, on expiry
        http = httpx.AsyncClient(auth=oauth_provider(), timeout=30)
    async with http:
        async with streamable_http_client(URL, http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield IdealoClient(session, country)


async def smoke(query, index):
    async with connect() as client:
        tools = await client.session.list_tools()
        print('Tools:', ', '.join(tool.name for tool in tools.tools))
        result = await client.search(query)
        products = result['results']
        if not products:
            raise RuntimeError('No matching products')
        if not 0 <= index < len(products):
            raise ValueError('Product index out of range')
        product = products[index]
        print('Selected product:', product['name'])
        offers = await client.offers(product)
        history = await client.history(product)
        print(json.dumps({'product': product, 'offers': offers, 'history': history}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Live idealo MCP smoke test; no purchases')
    parser.add_argument('query', nargs='?', default='Apple MacBook Air M2')
    parser.add_argument('--index', type=int, default=0)
    args = parser.parse_args()
    asyncio.run(smoke(args.query, args.index))
