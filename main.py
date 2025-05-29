import asyncio
from typing import Any

import lxml.html
from httpx import AsyncClient

DEBUG = 1


def extract_unit_info(element: lxml.html.HtmlElement):
    ...



async def main():
    kwargs = {
        "proxy": "http://127.0.0.1:8080",
        "verify": False,
    } if DEBUG else {}


    units: list[Any] = []

    async with AsyncClient(**kwargs) as client:
        await client.get("https://www.newportrentals.com/apartments-jersey-city-for-rent/")

        page_num = 1
        while True:
            resp = await client.post(
                "https://www.newportrentals.com/ajax/getunitlist.asp",
                data={
                    "bedrooms": "",
                    "priceMin":	1000,
                    "isDefaultMinPrice": True,
                    "priceMax": 20000,
                    "isDefaultMaxPrice": True,
                    "buildings": "",
                    "moveInDate": "",
                    "availableNowOnly": 0,
                    "page": page_num,
                    "lastNum": "",
                    "sort": "",
                    "numberPerPage": "undefined"
                }
            )

            page_num += 1

            if not resp.text:
                break


            html = lxml.html.fromstring(resp.text)
            for ele in html.cssselect('div[class*=unit-list-item]'):
                units.append(extract_unit_info(ele))



        print(1)


if __name__ == "__main__":
    asyncio.run(main())
