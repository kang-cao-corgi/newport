import asyncio
import csv
import datetime as dt
import logging
import re
import traceback
import zoneinfo
from typing import Any

import gspread
import lxml.html  # pyright: ignore[reportMissingTypeStubs]
from httpx import AsyncClient
from oauth2client.service_account import ServiceAccountCredentials  # pyright: ignore[reportMissingTypeStubs]
from pydantic import BaseModel, NonNegativeInt, PositiveInt, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("main")
logger.setLevel(logging.DEBUG)


class ProxyConfig(BaseModel):
    enabled: bool = False
    port: str = "__dummy"


class GoogleSheetsConfig(BaseModel):
    save: bool = False
    file_name: str = "__dummy"
    sheet_name: str = "__dummy"
    credentials_file: str = "bot.json"


class LocalCSVConfig(BaseModel):
    save: bool = False
    file_prefix: str = "output/NewportRentals"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
    )

    proxy: ProxyConfig = ProxyConfig()
    google_sheets: GoogleSheetsConfig = GoogleSheetsConfig()
    local_csv: LocalCSVConfig = LocalCSVConfig()



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
            value = dt.datetime.strptime(value, "%m/%d/%Y").strftime("%m/%d/%Y")
        return value


def extract_unit_info(ele: lxml.html.HtmlElement) -> Unit:

    # e.g. 2701 at Newport Rentals on 40 Newport Parkway, Studio, 1 Bathroom, 492 square feet, Available 6/6/2026

    pattern = r'(?P<unit>\d+) at Newport Rentals on (?P<address>[^,]+), (?P<bedroom>Studio|\d+ Bedroom(?:s)?), (?P<bathroom>\d+ Bathroom(?:s)?), (?P<sqft>[\d,]+) square feet, Available (?P<available>Now|\d{1,2}/\d{1,2}/\d{2,4})'

    match = re.search(pattern, str(ele.attrib['aria-label']))
    assert match
    return Unit(
        building_name=ele.cssselect('.availabilitylistings__building-name')[0].text.strip(),
        building_address=match.group("address"),
        apartment_number=ele.cssselect('.availabilitylistings__residence-name')[0].text.strip().replace('Residence ', ''),
        num_bedroom=match.group("bedroom"),
        num_bathroom=match.group("bathroom"),
        square_footage=match.group("sqft"),
        price=to_int(ele.cssselect('[class="availabilitylistings__column availabilitylistings__column--rent"] [data-total-price]')[0].text.strip()),
        availability=match.group("available"),
    )


def write_csv(units: list[Unit]):
    path = f'{SETTINGS.local_csv.file_prefix}_{date_of_today().strftime("%m%d%Y")}.csv'
    with open(path, "w+", newline="") as f:
        field_names = list(Unit.model_fields.keys())
        writer = csv.DictWriter(f, fieldnames=field_names)
        writer.writeheader()
        for unit in units:
            writer.writerow(unit.model_dump())

    logger.info(f"CSV file written at {path=}")


def write_gsheet(units: list[Unit]):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(SETTINGS.google_sheets.credentials_file, scope)  # pyright: ignore

    client = gspread.authorize(creds)  # pyright: ignore
    sheet = client.open(SETTINGS.google_sheets.file_name).worksheet(SETTINGS.google_sheets.sheet_name)

    timezone = zoneinfo.ZoneInfo("America/New_York")
    timestamp = dt.datetime.now(timezone).strftime("%Y-%m-%d %H:%M:%S")

    sheet.append_rows([
        [*list(unit.model_dump().values()), timestamp]
        for unit in units
    ])
    logger.info(f"Google sheet writen to {SETTINGS.google_sheets.sheet_name=} at {timestamp=}")


async def main():
    kwargs: dict[str, Any] = {
        "proxy": SETTINGS.proxy.port,
        "verify": False,
    } if SETTINGS.proxy.enabled else {}

    units: list[Unit] = []

    async with AsyncClient(
        headers={},  # TODO
        follow_redirects=True,
        timeout=20,
        **kwargs
    ) as client:
        resp = await client.get("https://www.newportrentals.com/apartments-jersey-city-for-rent")

        html = lxml.html.fromstring(resp.text)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        locator = (
            'div[class="availabilitylistings__row-container availabilitylistings__row-container--unit"][test] '
            'button[class="availabilitylistings__row availabilitylistings__row--unit availabilitylistings__unit"]'
        )
        for ele in html.cssselect(locator):
            try:
                units.append(extract_unit_info(ele))
            except Exception:
                logger.error(f"Failed to parse unit: {lxml.html.tostring(ele)}, {traceback.format_exc()=}")

        if SETTINGS.local_csv.save:
            write_csv(units)

        if SETTINGS.google_sheets.save:
            write_gsheet(units)


if __name__ == "__main__":
    asyncio.run(main())
