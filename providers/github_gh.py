import argparse


def get_search_result_count(search):
    return len(search)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Return a stub result count for a GitHub CLI search."
    )
    parser.add_argument(
        "searches",
        nargs="+",
        help="Search query or queries to inspect.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    print(sum(get_search_result_count(search) for search in args.searches))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
