import argparse


def get_issue_count(jql):
    return len(jql)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Return a stub issue count for a Jira JQL query."
    )
    parser.add_argument("jql", help="JQL query to inspect.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    print(get_issue_count(args.jql))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
