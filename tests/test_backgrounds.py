from gf_ui_editor import backgrounds


def test_exact_resolution_is_used() -> None:
    assert backgrounds.pick((1600, 900)).stem == "1600x900"
    assert backgrounds.pick((2560, 1080)).stem == "2560x1080"


def test_closest_aspect_ratio_and_largest_image() -> None:
    assert backgrounds.pick((2560, 1440)).stem == "1920x1080"  # 16:9
    assert backgrounds.pick((1920, 1200)).stem == "1680x1050"  # 16:10
    assert backgrounds.pick((800, 600)).stem == "1024x768"  # 4:3
    assert backgrounds.pick((3440, 1440)).stem == "2560x1080"  # 21:9
