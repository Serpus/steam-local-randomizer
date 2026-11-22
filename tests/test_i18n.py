from steam_randomizer.i18n import plural_ru


def test_plural_ru_one():
    for n in (1, 21, 31, 101, 1001):
        assert plural_ru(n, "игра", "игры", "игр") == "игра"


def test_plural_ru_few():
    for n in (2, 3, 4, 22, 24, 102, 1002):
        assert plural_ru(n, "игра", "игры", "игр") == "игры"


def test_plural_ru_many():
    for n in (0, 5, 11, 12, 13, 14, 20, 25, 100, 111):
        assert plural_ru(n, "игра", "игры", "игр") == "игр"