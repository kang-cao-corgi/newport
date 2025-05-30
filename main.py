import asyncio
import datetime as dt
import re
import csv

import lxml.html
from httpx import AsyncClient
from pydantic import (
    BaseModel,
    NonNegativeInt,
    PositiveInt,
    field_validator
)

DEBUG = 0


class Unit(BaseModel):
    building_name: str
    building_address: str
    apartment_number: int
    num_bedroom: NonNegativeInt
    num_bathroom: PositiveInt
    square_footage: PositiveInt
    price: PositiveInt
    availability: str

    @field_validator("num_bedroom", "num_bathroom", mode="before")
    @classmethod
    def room_numbers(cls, value: str):
        if value == "Studio":
            return 0
        return int(value.split(" ")[0])

    @field_validator("availability", mode="before")
    @classmethod
    def date(cls, value: str):
        if value != "Now":
            value = dt.datetime.strptime(value, "%m/%d/%y").strftime("%m/%d/%Y")
        return value

def to_int(value: str) -> int:
    return int(re.sub(r"[^\d]", "", value))


def extract_unit_info(raw: str) -> Unit:
    print(f"Processing: {raw}")
    pattern = (
        r'Residence (?P<unit>\d+) in '
        r'(?P<building>.+?) on '
        r'(?P<address>[^,]+), '
        r'(?P<bedroom>Studio|\d+ Bedroom(?:s)?) '
        r'(?P<bathroom>\d+ Bathroom(?:s)?), '
        r'(?P<sqft>[\d,]+) square feet, '
        r'\$(?P<price>[\d,]+), '
        r'Available (?P<available>Now|\d{1,2}/\d{1,2}/\d{2,4})')
    match = re.search(pattern, raw)
    assert match
    return Unit(
        building_name=match.group("building"),
        building_address=match.group("address"),
        apartment_number=match.group("unit"),
        num_bedroom=match.group("bedroom"),
        num_bathroom=match.group("bathroom"),
        square_footage=to_int(match.group("sqft")),
        price=to_int(match.group("price")),
        availability=match.group("available"),
    )


def write_csv(units: list[Unit]):
    with open("NewportRentals.csv", "w+", newline="") as f:
        field_names = list(Unit.model_fields.keys())
        writer = csv.DictWriter(f, fieldnames=field_names)
        writer.writeheader()
        for unit in units:
            writer.writerow(unit.model_dump())


async def main():
    kwargs = {
        "proxy": "http://127.0.0.1:8080",
        "verify": False,
    } if DEBUG else {}


    units: list[Unit] = []

    async with AsyncClient(**kwargs) as client:
        await client.get("https://www.newportrentals.com/apartments-jersey-city-for-rent/")

        page_num = 1
        while True:
            await asyncio.sleep(2)
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
            for raw_string in html.xpath('//div[contains(@class, "unit-list-item")]//button/@aria-label'):
                units.append(extract_unit_info(raw_string))

        write_csv(units)


if __name__ == "__main__":
    asyncio.run(main())
