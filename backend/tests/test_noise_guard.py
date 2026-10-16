import importlib.util, pathlib
_p = pathlib.Path(__file__).resolve().parents[1] / "agent" / "noise.py"
_s = importlib.util.spec_from_file_location("noise", _p); noise = importlib.util.module_from_spec(_s); _s.loader.exec_module(noise)


def test_gibberish_is_noise():
    for m in ["lasnnskjdsdsadfsadfsdfsdgsgsgsfgsdfsdfsafdas", "dfasfsdfsdfsdf0sdfasdf", "sdf", "!!!"]:
        assert noise.is_noise(m), m


def test_real_requests_are_not_noise():
    for m in ["hi", "dsa", "tcp", "bfs vs dfs", "add an exam for OS tomorrow", "what is paging"]:
        assert not noise.is_noise(m), m


def test_short_unknown():
    assert noise.is_short_unknown("hihu") and not noise.is_short_unknown("dsa")
