"""1.0.1: the landing frames (site 1 drive 52) are placed at the S003D0000 waypoint and kept at Butler."""
from rpp import load_waypoints
from rpp.pipeline import load_settings
from rpp.sfm.project import select_best_products
from rpp.sfm.reconstruction import is_unsurveyed
from rpp.waypoints import waypoint_for_site_drive
from rpp.waypoints.table import has_station, station_alias


def test_alias_places_the_landing_station():
    wp = load_waypoints()
    assert not has_station(wp, 1, 52) and has_station(wp, 3, 0)
    assert station_alias(1, 52) == (3, 0) and station_alias(3, 0) is None
    a = waypoint_for_site_drive(wp, 1, 52, exact=True)
    b = waypoint_for_site_drive(wp, 3, 0, exact=True)
    assert a is b


def test_alias_prior_is_loose():
    assert is_unsurveyed({"position_source": "waypoint site 3 drive 0 (station alias of site 1 drive 52)"})
    assert not is_unsurveyed({"position_source": "waypoint site 3 drive 0 (exact)"})


def test_butler_keeps_aut_sequences(tmp_path):
    s = load_settings(site="butler_landing")
    assert "AUT_" in s.sequence_prefixes and "NCAM" in s.sequence_prefixes
    names = ["ZL0_0003_0667217146_000RAD_N0010052AUT_04096_034085A01.IMG",
             "ZL0_0011_0667933497_000RAD_N0030000ZCAM00100_0340LUJ01.IMG"]
    for n in names:
        (tmp_path / n).write_bytes(b"x" * 100)
    kept, rep = select_best_products([tmp_path / n for n in names], sequence_prefix=tuple(s.sequence_prefixes) + ("ZCAM",))
    assert len(kept) == 2 and rep["n_dropped_sequence"] == 0
    kept, rep = select_best_products([tmp_path / n for n in names], sequence_prefix=("NCAM", "ZCAM"))
    assert len(kept) == 1 and rep["n_dropped_sequence"] == 1
