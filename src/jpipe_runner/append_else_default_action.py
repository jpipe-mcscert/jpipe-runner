from argparse import _AppendAction, _copy_items


class _AppendElseDefaultAction(_AppendAction):
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
        deprecated=False,
    ):
        if default is None:
            raise ValueError(
                "append_else_default action requires a default value "
                "(the fallback list to use when the option is not given)"
            )
        super(_AppendElseDefaultAction, self).__init__(
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
            deprecated=deprecated,
        )

    def __call__(self, parser, namespace, values, option_string=None):
        items = getattr(namespace, self.dest)
        if items is self.default:
            items = []
        else:
            items = _copy_items(items)
        items.append(values)
        setattr(namespace, self.dest, items)
