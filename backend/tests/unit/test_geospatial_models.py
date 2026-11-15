import pytest
from app.domain.geospatial.models import BoundingBox, CoordinateError, GeoPoint, PixelBBox

pytestmark = pytest.mark.unit


def test_bbox_parse_valid():
    bbox = BoundingBox.parse("37.5,55.7,37.7,55.8")
    assert bbox.min_lon == 37.5
    assert bbox.max_lat == 55.8
    assert "POLYGON" in bbox.to_wkt_polygon()


@pytest.mark.parametrize("raw", ["", "1,2,3", "a,b,c,d", "37.7,55.8,37.5,55.7"])
def test_bbox_parse_invalid(raw):
    with pytest.raises(CoordinateError):
        BoundingBox.parse(raw)


def test_bbox_out_of_range():
    with pytest.raises(CoordinateError):
        BoundingBox(0, 0, 200, 50)


def test_pixel_bbox_validation():
    bbox = PixelBBox(10, 20, 100, 200)
    bbox.validate(640, 480)
    with pytest.raises(CoordinateError):
        bbox.validate(50, 50)
    with pytest.raises(CoordinateError):
        PixelBBox(100, 20, 10, 200).validate(640, 480)


def test_geopoint_extremes():
    GeoPoint(-180, -90)
    GeoPoint(180, 90)
    with pytest.raises(CoordinateError):
        GeoPoint(180.1, 0)
    with pytest.raises(CoordinateError):
        GeoPoint(0, -90.1)
