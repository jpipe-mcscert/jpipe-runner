"""Slides"""
from jpipe_runner.framework.decorators.jpipe_decorator import jpipe

@jpipe(consume=["signature"])
def nda_is_signed(signature: str):
    print("NDA signature is ", signature)
    return signature == 'jason'


@jpipe(consume=["available"])
def slides_are_available(available: bool):
    return available


@jpipe(produce=["x"])
def check_contents_wrt_nda(produce):
    x = "ok"
    produce("x", x)
    return x

@jpipe(produce=["y"])
def check_grammar_typos(produce):
    x = "loos good!"
    produce("y", x)
    return x

@jpipe(consume=["x", "y"])
def all_conditions_are_met(x: str, y: str):
    return all([
        x == "ok",
        y == "loos good!",
    ])
