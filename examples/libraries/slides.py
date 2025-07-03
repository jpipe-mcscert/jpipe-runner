"""Slides"""
from jpipe_runner import Consume, Produce

@Consume("signature")
def nda_is_signed(signature: str):
    print("NDA signature is ", signature)
    return signature == 'jason'


@Consume("available")
def slides_are_available(available):
    return available


@Produce("x")
def check_contents_wrt_nda(produce):
    x = "ok"
    produce("x", x)
    return x

@Produce("y")
def check_grammar_typos(produce):
    x = "loos good!"
    produce("y", x)
    return x

@Consume("x", "y")
def all_conditions_are_met(x: str, y: str):
    return all([
        x == "ok",
        y == "loos good!",
    ])
