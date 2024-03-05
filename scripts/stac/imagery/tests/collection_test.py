import json
import os
import tempfile
from datetime import datetime
from shutil import rmtree
from tempfile import mkdtemp
from typing import Generator

import pytest
import shapely.geometry

from scripts.files.fs import read
from scripts.stac.imagery.collection import ImageryCollection
from scripts.stac.imagery.item import ImageryItem
from scripts.stac.imagery.metadata_constants import CollectionMetadata
from scripts.stac.imagery.provider import Provider, ProviderRole
from scripts.stac.util.stac_extensions import StacExtensions


# pylint: disable=duplicate-code
@pytest.fixture(name="metadata", autouse=True)
def setup() -> Generator[CollectionMetadata, None, None]:
    metadata: CollectionMetadata = {
        "category": "urban-aerial-photos",
        "region": "auckland",
        "gsd": "0.3m",
        "start_datetime": datetime(2022, 2, 2),
        "end_datetime": datetime(2022, 2, 2),
        "lifecycle": "completed",
        "event_name": "Forest Assessment",
        "historic_survey_number": None,
        "geographic_description": "Auckland North Forest Assessment",
    }
    yield metadata


def test_title_description_id_created_on_init(metadata: CollectionMetadata) -> None:
    collection = ImageryCollection(metadata)
    assert collection.stac["title"] == "Auckland North Forest Assessment 0.3m Urban Aerial Photos (2022)"
    assert (
        collection.stac["description"]
        == "Orthophotography within the Auckland region captured in the 2022 flying season, published as a record of the Forest Assessment event."  # pylint: disable=line-too-long
    )
    assert collection.stac["id"]
    assert collection.stac["linz:region"] == "auckland"
    assert collection.stac["linz:geographic_description"] == "Auckland North Forest Assessment"
    assert collection.stac["linz:event_name"] == "Forest Assessment"
    assert collection.stac["linz:lifecycle"] == "completed"
    assert collection.stac["linz:geospatial_category"] == "urban-aerial-photos"


def test_id_parsed_on_init(metadata: CollectionMetadata) -> None:
    id_ = "Parsed-Ulid"
    collection = ImageryCollection(metadata, id_)
    assert collection.stac["id"] == "Parsed-Ulid"


def test_bbox_updated_from_none(metadata: CollectionMetadata) -> None:
    collection = ImageryCollection(metadata)
    bbox = [1799667.5, 5815977.0, 1800422.5, 5814986.0]
    collection.update_spatial_extent(bbox)
    assert collection.stac["extent"]["spatial"]["bbox"] == [bbox]


def test_bbox_updated_from_existing(metadata: CollectionMetadata) -> None:
    collection = ImageryCollection(metadata)
    # init bbox
    bbox = [174.889641, -41.217532, 174.902344, -41.203521]
    collection.update_spatial_extent(bbox)
    # update bbox
    bbox = [174.917643, -41.211157, 174.922965, -41.205490]
    collection.update_spatial_extent(bbox)

    assert collection.stac["extent"]["spatial"]["bbox"] == [[174.889641, -41.217532, 174.922965, -41.203521]]


def test_interval_updated_from_none(metadata: CollectionMetadata) -> None:
    collection = ImageryCollection(metadata)
    start_datetime = "2021-01-27T00:00:00Z"
    end_datetime = "2021-01-27T00:00:00Z"
    collection.update_temporal_extent(start_datetime, end_datetime)
    assert collection.stac["extent"]["temporal"]["interval"] == [[start_datetime, end_datetime]]


def test_interval_updated_from_existing(metadata: CollectionMetadata) -> None:
    collection = ImageryCollection(metadata)
    # init interval
    start_datetime = "2021-01-27T00:00:00Z"
    end_datetime = "2021-01-27T00:00:00Z"
    collection.update_temporal_extent(start_datetime, end_datetime)
    # update interval
    start_datetime = "2021-02-01T00:00:00Z"
    end_datetime = "2021-02-20T00:00:00Z"
    collection.update_temporal_extent(start_datetime, end_datetime)

    assert collection.stac["extent"]["temporal"]["interval"] == [["2021-01-27T00:00:00Z", "2021-02-20T00:00:00Z"]]


def test_add_item(mocker, metadata: CollectionMetadata) -> None:  # type: ignore
    collection = ImageryCollection(metadata)
    mocker.patch("scripts.files.fs.read", return_value=b"")
    item = ImageryItem("BR34_5000_0304", "./test/BR34_5000_0304.tiff")
    geometry = {
        "type": "Polygon",
        "coordinates": [[1799667.5, 5815977.0], [1800422.5, 5815977.0], [1800422.5, 5814986.0], [1799667.5, 5814986.0]],
    }
    bbox = (1799667.5, 5815977.0, 1800422.5, 5814986.0)
    start_datetime = "2021-01-27 00:00:00Z"
    end_datetime = "2021-01-27 00:00:00Z"
    item.update_spatial(geometry, bbox)
    item.update_datetime(start_datetime, end_datetime)

    collection.add_item(item.stac)

    assert {"rel": "item", "href": "./BR34_5000_0304.json", "type": "application/json"} in collection.stac["links"]
    assert collection.stac["extent"]["temporal"]["interval"] == [[start_datetime, end_datetime]]
    assert collection.stac["extent"]["spatial"]["bbox"] == [bbox]


def test_write_collection(metadata: CollectionMetadata) -> None:
    target = mkdtemp()
    collectionObj = ImageryCollection(metadata)
    collection_target = os.path.join(target, "collection.json")
    collectionObj.write_to(collection_target)
    collection = json.loads(read(collection_target))
    rmtree(target)

    assert collection["title"] == collectionObj.stac["title"]


def test_write_collection_special_chars(metadata: CollectionMetadata) -> None:
    target = mkdtemp()
    title = "Manawatū-Whanganui"
    collectionObj = ImageryCollection(metadata)
    collectionObj.stac["title"] = title
    collection_target = os.path.join(target, "collection.json")
    collectionObj.write_to(collection_target)
    collection = json.loads(read(collection_target))
    rmtree(target)

    assert collection["title"] == title


def test_add_providers(metadata: CollectionMetadata) -> None:
    collection = ImageryCollection(metadata)
    producer: Provider = {"name": "Maxar", "roles": [ProviderRole.PRODUCER]}
    collection.add_providers([producer])

    assert {"name": "Maxar", "roles": ["producer"]} in collection.stac["providers"]


def test_default_provider_roles_are_kept(metadata: CollectionMetadata) -> None:
    # given we are adding a non default role to the default provider
    licensor: Provider = {"name": "Toitū Te Whenua Land Information New Zealand", "roles": [ProviderRole.LICENSOR]}
    producer: Provider = {"name": "Maxar", "roles": [ProviderRole.PRODUCER]}
    collection = ImageryCollection(metadata, providers=[producer, licensor])

    # then it adds the non default role to the existing default role list
    assert {
        "name": "Toitū Te Whenua Land Information New Zealand",
        "roles": ["licensor", "host", "processor"],
    } in collection.stac["providers"]
    # then it does not duplicate the default provider
    assert {"name": "Toitū Te Whenua Land Information New Zealand", "roles": ["host", "processor"]} not in collection.stac[
        "providers"
    ]


def test_default_provider_is_present(metadata: CollectionMetadata) -> None:
    # given adding a provider
    producer: Provider = {"name": "Maxar", "roles": [ProviderRole.PRODUCER]}
    collection = ImageryCollection(metadata, providers=[producer])

    # then the default provider is still present
    assert {"name": "Toitū Te Whenua Land Information New Zealand", "roles": ["host", "processor"]} in collection.stac[
        "providers"
    ]
    # then the new provider is added
    assert {"name": "Maxar", "roles": ["producer"]} in collection.stac["providers"]


def test_capture_area_added(metadata: CollectionMetadata) -> None:
    collection = ImageryCollection(metadata)
    file_name = "capture-area.geojson"

    polygons = []
    polygons.append(
        shapely.geometry.shape(
            {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [178.259659571653, -38.40831927359251],
                            [178.26012930415902, -38.41478071250544],
                            [178.26560430668172, -38.41453416326152],
                            [178.26513409076952, -38.40807278109057],
                            [178.259659571653, -38.40831927359251],
                        ]
                    ]
                ],
            }
        )
    )
    polygons.append(
        shapely.geometry.shape(
            {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [178.25418498567294, -38.40856551170436],
                            [178.25465423474975, -38.41502700730107],
                            [178.26012930415902, -38.41478071250544],
                            [178.259659571653, -38.40831927359251],
                            [178.25418498567294, -38.40856551170436],
                        ]
                    ]
                ],
            }
        )
    )
    with tempfile.TemporaryDirectory() as tmp_path:
        artifact_path = os.path.join(tmp_path, "tmp")
        collection.add_capture_area(polygons, tmp_path, artifact_path)
        file_target = os.path.join(tmp_path, file_name)
        file_artifact = os.path.join(artifact_path, file_name)
        assert os.path.isfile(file_target)
        assert os.path.isfile(file_artifact)

    assert collection.stac["assets"]["capture_area"]["href"] == f"./{file_name}"
    assert collection.stac["assets"]["capture_area"]["title"] == "Capture area"
    assert collection.stac["assets"]["capture_area"]["type"] == "application/geo+json"
    assert collection.stac["assets"]["capture_area"]["roles"] == ["metadata"]
    assert StacExtensions.file.value in collection.stac["stac_extensions"]
    assert "file:checksum" in collection.stac["assets"]["capture_area"]
    assert (
        collection.stac["assets"]["capture_area"]["file:checksum"]
        == "1220b15694be7495af38e0f70af67cfdc4f19b8bc415a2eb77d780e7a32c6e5b42c2"
    )
    assert "file:size" in collection.stac["assets"]["capture_area"]
    assert collection.stac["assets"]["capture_area"]["file:size"] == 339


def test_event_name_is_present(metadata: CollectionMetadata) -> None:
    collection = ImageryCollection(metadata)
    assert "Forest Assessment" == collection.stac["linz:event_name"]


def test_geographic_description_is_present(metadata: CollectionMetadata) -> None:
    collection = ImageryCollection(metadata)
    assert "Auckland North Forest Assessment" == collection.stac["linz:geographic_description"]