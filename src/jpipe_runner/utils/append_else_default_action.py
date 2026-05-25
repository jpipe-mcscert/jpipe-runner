from argparse import OPTIONAL, Action


class AppendElseDefaultAction(Action):
    """
    This works like 'append', but the ``default`` value is only used when
    the option is not present on the command line.  If the option is given
    at least once, the initial default is discarded and the provided values
    are appended to an initially empty list.
    """

    def __init__(
        self,
        option_strings,
        dest,
        nargs=None,
        const=None,
        default=None,
        type=None,
        choices=None,
        required=False,
        help=None,
        metavar=None,
    ):
        if nargs == 0:
            raise ValueError(
                "nargs for append_else_default actions must be != 0; if arg "
                "strings are not supplying the value to append, "
                "the append const action may be more appropriate"
            )
        if const is not None and nargs != OPTIONAL:
            raise ValueError("nargs must be %r to supply const" % OPTIONAL)
        if default is None:
            raise ValueError(
                "append_else_default action requires a default value "
                "(the fallback list to use when the option is not given) "
                "if you don't need a fallback, consider using 'append' instead"
            )
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            nargs=nargs,
            const=const,
            default=default,
            type=type,
            choices=choices,
            required=required,
            help=help,
            metavar=metavar,
        )

    def __call__(self, parser, namespace, values, option_string=None):
        items = getattr(namespace, self.dest)
        if items is self.default:
            items = []
        else:
            items = _copy_items(items)
        items.append(values)
        setattr(namespace, self.dest, items)


def _copy_items(items):
    """
    From argparse._copy_items, which is not public
    but we need similar logic to avoid mutating the default list.
    """
    if items is None:
        return []
    if type(items) is list:
        return items[:]
    import copy

    return copy.copy(items)
