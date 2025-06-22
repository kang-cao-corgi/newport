import asyncio
import csv
import datetime as dt
from typing import Any
import re

import gspread
import lxml.html  # pyright: ignore[reportMissingTypeStubs]
from httpx import AsyncClient
from oauth2client.service_account import ServiceAccountCredentials  # pyright: ignore[reportMissingTypeStubs]
from pydantic import BaseModel, NonNegativeInt, PositiveInt, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProxyConfig(BaseModel):
    enabled: bool = False
    port: str = ""


class GoogleSheetsConfig(BaseModel):
    save: bool = False
    file_name: str
    sheet_name: str = "raw"
    credentials_file: str = "bot.json"


class LocalCSVConfig(BaseModel):
    save: bool = False
    file_prefix: str = "output/NewportRentals"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
    )

    proxy: ProxyConfig
    google_sheets: GoogleSheetsConfig
    local_csv: LocalCSVConfig



SETTINGS = Settings()  # pyright: ignore[reportCallIssue]


def date_of_today():
    return dt.date.today()


def to_int(value: str) -> int:
    return int(re.sub(r"[^\d]", "", value))


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
        apartment_number=int(match.group("unit")),
        num_bedroom=match.group("bedroom"),  # pyright: ignore[reportArgumentType]
        num_bathroom=match.group("bathroom"),  # pyright: ignore[reportArgumentType]
        square_footage=to_int(match.group("sqft")),
        price=to_int(match.group("price")),
        availability=match.group("available"),
    )


def write_csv(units: list[Unit]):
    with open(
        f'{SETTINGS.local_csv.file_prefix}_{date_of_today().strftime("%m%d%Y")}.csv',
        "w+",
        newline="",
    ) as f:
        field_names = list(Unit.model_fields.keys())
        writer = csv.DictWriter(f, fieldnames=field_names)
        writer.writeheader()
        for unit in units:
            writer.writerow(unit.model_dump())


def write_gsheet(units: list[Unit]):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(SETTINGS.google_sheets.credentials_file, scope)  # pyright: ignore

    client = gspread.authorize(creds)  # pyright: ignore
    sheet = client.open(SETTINGS.google_sheets.file_name).worksheet(SETTINGS.google_sheets.sheet_name)

    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sheet.append_rows([
        [*list(unit.model_dump().values()), timestamp]
        for unit in units
    ])


async def main():
    kwargs: dict[str, Any] = {
        "proxy": SETTINGS.proxy.port,
        "verify": False,
    } if SETTINGS.proxy.enabled else {}

    units: list[Unit] = []

    async with AsyncClient(
        headers={},  # TODO
        **kwargs
    ) as client:
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

            html = lxml.html.fromstring(resp.text)  # pyright: ignore[reportUnknownMemberType]
            for raw_string in html.xpath('//div[contains(@class, "unit-list-item")]//button/@aria-label'):
                units.append(extract_unit_info(raw_string))

        if SETTINGS.local_csv.save:
            write_csv(units)

        if SETTINGS.google_sheets.save:
            write_gsheet(units)


if __name__ == "__main__":
    asyncio.run(main())
